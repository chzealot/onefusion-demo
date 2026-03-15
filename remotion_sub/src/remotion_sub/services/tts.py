"""TTS service: Alibaba Cloud CosyVoice via WebSocket streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import websockets

from remotion_sub.config import settings

logger = logging.getLogger(__name__)


async def _get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "json",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    data = json.loads(stdout)
    return float(data["format"]["duration"])


async def synthesize_segment(text: str, output_path: str) -> float:
    """Synthesize a single text segment to mp3 via CosyVoice WSS. Returns duration in seconds."""
    logger.info("TTS: synthesizing '%s' -> %s", text[:30], output_path)

    audio_data = bytearray()
    ws_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"
    task_id = uuid.uuid4().hex

    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "X-DashScope-DataInspection": "enable",
    }

    async with websockets.connect(ws_url, additional_headers=headers) as ws:
        # Send run-task
        run_task_msg = {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "tts",
                "function": "SpeechSynthesizer",
                "model": "cosyvoice-v2-0.5b",
                "parameters": {
                    "voice": settings.tts_voice,
                    "format": settings.tts_format,
                    "sample_rate": settings.tts_sample_rate,
                    "rate": settings.tts_speed / 50.0,
                    "pitch": settings.tts_pitch / 50.0,
                    "volume": settings.tts_volume,
                },
                "input": {},
            },
        }
        await ws.send(json.dumps(run_task_msg))

        # Wait for task-started
        while True:
            resp = await ws.recv()
            if isinstance(resp, str):
                msg = json.loads(resp)
                action = msg.get("header", {}).get("action", "")
                if action == "task-started":
                    break
                if action == "error" or msg.get("header", {}).get("code"):
                    raise RuntimeError(f"TTS task failed to start: {msg}")

        # Send text
        continue_msg = {
            "header": {
                "action": "continue-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "input": {"text": text},
            },
        }
        await ws.send(json.dumps(continue_msg))

        # Send finish
        finish_msg = {
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {"input": {}},
        }
        await ws.send(json.dumps(finish_msg))

        # Collect audio data
        while True:
            resp = await ws.recv()
            if isinstance(resp, bytes):
                audio_data.extend(resp)
            elif isinstance(resp, str):
                msg = json.loads(resp)
                action = msg.get("header", {}).get("action", "")
                if action == "result-generated":
                    event = msg.get("header", {}).get("event", "")
                    if event == "task-finished":
                        break
                elif action == "error" or msg.get("header", {}).get("code"):
                    raise RuntimeError(f"TTS error: {msg}")

    # Write audio file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(audio_data)

    duration = await _get_audio_duration(output_path)
    logger.info("TTS: synthesized %s (%.2fs)", output_path, duration)
    return duration


async def generate_all(session_dir: Path, subtitles: list[dict]) -> dict:
    """Generate TTS audio for all subtitle segments. Returns durations dict."""
    audio_dir = session_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    durations: dict[str, float] = {}

    for scene in subtitles:
        for seg in scene.get("subtitles", []):
            filename = seg["file"]
            text = seg["text"]
            output_path = str(audio_dir / filename)
            duration = await synthesize_segment(text, output_path)
            durations[filename] = duration

    return durations


async def combine_audio(session_dir: Path, subtitles: list[dict], durations: dict) -> float:
    """Combine all audio segments with gaps into a single file. Returns total duration."""
    audio_dir = session_dir / "audio"
    concat_list_path = audio_dir / "concat.txt"

    scene_buffer = 0.5
    segment_gap = 0.3

    total_duration = 0.0
    entries: list[str] = []

    for i, scene in enumerate(subtitles):
        subs = scene.get("subtitles", [])
        if not subs:
            continue

        # Buffer before scene
        silence_file = audio_dir / f"silence_{i}_start.mp3"
        await _generate_silence(str(silence_file), scene_buffer)
        entries.append(f"file '{silence_file.name}'")
        total_duration += scene_buffer

        for j, seg in enumerate(subs):
            filename = seg["file"]
            entries.append(f"file '{filename}'")
            total_duration += durations.get(filename, 0)

            if j < len(subs) - 1:
                gap_file = audio_dir / f"silence_{i}_{j}_gap.mp3"
                await _generate_silence(str(gap_file), segment_gap)
                entries.append(f"file '{gap_file.name}'")
                total_duration += segment_gap

        # Buffer after scene
        silence_file = audio_dir / f"silence_{i}_end.mp3"
        await _generate_silence(str(silence_file), scene_buffer)
        entries.append(f"file '{silence_file.name}'")
        total_duration += scene_buffer

    concat_list_path.write_text("\n".join(entries), encoding="utf-8")

    combined_path = audio_dir / "combined.mp3"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        str(combined_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError("ffmpeg concat failed")

    actual_duration = await _get_audio_duration(str(combined_path))
    logger.info("Combined audio: %.2fs", actual_duration)
    return actual_duration


async def _generate_silence(output_path: str, duration: float) -> None:
    """Generate a silent mp3 file of specified duration."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={settings.tts_sample_rate}:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-b:a", "128k",
        output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
