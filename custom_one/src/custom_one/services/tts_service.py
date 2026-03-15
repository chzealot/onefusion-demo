from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import websockets

from custom_one.config import settings

logger = logging.getLogger(__name__)

WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"


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
    """Synthesize a single text segment to mp3. Returns duration in seconds."""
    logger.info("TTS: synthesizing '%s' -> %s", text[:30], output_path)

    task_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []

    headers = {"Authorization": f"Bearer {settings.dashscope_api_key}"}

    async with websockets.connect(WS_URL, additional_headers=headers) as ws:
        # run-task
        await ws.send(json.dumps({
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "tts",
                "function": "SpeechSynthesizer",
                "model": "cosyvoice-v1",
                "parameters": {
                    "text_type": "PlainText",
                    "voice": settings.tts_voice,
                    "format": settings.tts_format,
                    "sample_rate": settings.tts_sample_rate,
                },
                "input": {},
            },
        }))

        # Event loop: wait for task-started, send text, collect audio
        async for message in ws:
            if isinstance(message, bytes):
                audio_chunks.append(message)
                continue

            event = json.loads(message)
            action = (
                event.get("header", {}).get("event")
                or event.get("header", {}).get("action")
            )

            if action == "task-started":
                # Send text
                await ws.send(json.dumps({
                    "header": {
                        "action": "continue-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {"text": text}},
                }))
                # Finish
                await ws.send(json.dumps({
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {}},
                }))

            elif action == "task-finished":
                break

            elif action == "task-failed":
                code = event.get("header", {}).get("error_code", "unknown")
                msg = event.get("header", {}).get("error_message", "unknown")
                raise RuntimeError(f"TTS failed: [{code}] {msg}")

    # Write audio file
    audio_data = b"".join(audio_chunks)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(audio_data)

    # Get duration
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

    scene_buffer = 0.5  # seconds before/after each scene
    segment_gap = 0.3   # seconds between segments within a scene

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

            # Gap between segments (not after last)
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
