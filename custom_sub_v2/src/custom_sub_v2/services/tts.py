"""TTS service using Alibaba DashScope CosyVoice streaming API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mutagen.mp3 import MP3

from custom_sub_v2.config import settings
from custom_sub_v2.services.logger import get_project_logger


async def generate_tts_for_session(
    session_dir: Path,
    project_id: str = "",
) -> list[dict]:
    """Generate TTS audio for all subtitles in a session.

    Reads subtitles.json, generates audio files, updates duration info,
    and writes back the enriched subtitles.json.

    Returns the updated scene data with duration_ms, start_frame, end_frame.
    """
    log = get_project_logger(project_id) if project_id else None

    subtitles_path = session_dir / "subtitles.json"
    with open(subtitles_path, "r") as f:
        scenes = json.load(f)

    audio_dir = session_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    # Generate audio for each subtitle segment
    for scene in scenes:
        for seg in scene.get("subtitles", []):
            text = seg["text"]
            filename = seg["file"]
            output_path = audio_dir / filename

            if log:
                log.info("Generating TTS: %s -> %s", text[:30], filename)
            await _synthesize(text, output_path)

            # Get audio duration
            duration_ms = _get_audio_duration_ms(output_path)
            seg["duration_ms"] = duration_ms
            if log:
                log.info("  duration: %dms", duration_ms)

    # Calculate frame timing
    fps = settings.video_fps
    current_frame = 0
    for scene in scenes:
        scene_start = current_frame
        for seg in scene.get("subtitles", []):
            duration_ms = seg.get("duration_ms", 2000)
            duration_frames = max(1, round(duration_ms / 1000 * fps))
            seg["start_frame"] = current_frame
            seg["end_frame"] = current_frame + duration_frames
            current_frame += duration_frames
        scene["total_frames"] = current_frame - scene_start

    # Write back enriched subtitles.json
    with open(subtitles_path, "w") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)

    if log:
        log.info("TTS complete. Total frames: %d", current_frame)
    return scenes


async def _synthesize(text: str, output_path: Path) -> None:
    """Synthesize text to audio file using DashScope CosyVoice."""
    import dashscope
    from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

    dashscope.api_key = settings.dashscope_api_key

    model = "cosyvoice-v1"
    voice = settings.tts_voice

    # Map sample rate to AudioFormat enum
    audio_format = AudioFormat.MP3_16000HZ_MONO_128KBPS
    sr = settings.tts_sample_rate
    if sr == 22050:
        audio_format = AudioFormat.MP3_22050HZ_MONO_256KBPS
    elif sr == 24000:
        audio_format = AudioFormat.MP3_24000HZ_MONO_256KBPS
    elif sr == 44100:
        audio_format = AudioFormat.MP3_44100HZ_MONO_256KBPS
    elif sr == 48000:
        audio_format = AudioFormat.MP3_48000HZ_MONO_256KBPS

    # speech_rate: 0.5~2.0 (1.0 = normal). User config is 0-100, map to 0.5-2.0
    speech_rate = 0.5 + (settings.tts_rate / 100) * 1.5
    # pitch_rate: 0.5~2.0 (1.0 = normal). User config is 0-100, map to 0.5-2.0
    pitch_rate = 0.5 + (settings.tts_pitch / 100) * 1.5
    # volume: 0-100
    volume = settings.tts_volume

    def _do_synthesize():
        synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            format=audio_format,
            speech_rate=speech_rate,
            pitch_rate=pitch_rate,
            volume=volume,
        )

        audio = synthesizer.call(text)
        if audio is not None:
            with open(output_path, "wb") as f:
                f.write(audio)
        else:
            raise RuntimeError(f"TTS synthesis failed for: {text[:50]}")

    await asyncio.get_event_loop().run_in_executor(None, _do_synthesize)


def _get_audio_duration_ms(path: Path) -> int:
    """Get audio file duration in milliseconds."""
    try:
        audio = MP3(str(path))
        return int(audio.info.length * 1000)
    except Exception:
        # Fallback: estimate from file size
        size = path.stat().st_size
        return max(500, int(size / 2))
