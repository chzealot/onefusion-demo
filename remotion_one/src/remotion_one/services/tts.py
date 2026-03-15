"""TTS generation using edge-tts."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunyang": "zh-CN-YunyangNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
}


async def generate_single(
    text: str,
    output_path: str,
    voice: str = "yunxi",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> None:
    """Generate a single TTS audio file."""
    voice_name = VOICES.get(voice, VOICES["yunxi"])
    communicate = edge_tts.Communicate(text=text, voice=voice_name, rate=rate, pitch=pitch)
    await communicate.save(output_path)
    logger.info(f"Generated: {output_path}")


async def generate_all(
    subtitles_path: Path,
    output_dir: Path,
    voice: str = "yunxi",
) -> int:
    """Generate all TTS audio files from subtitles.json.

    Returns:
        Number of audio files generated.
    """
    with open(subtitles_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for scene in data:
        for subtitle in scene.get("subtitles", []):
            text = subtitle["text"]
            file_name = subtitle["file"]
            rate = subtitle.get("rate", "+40%")
            pitch = subtitle.get("pitch", "+0Hz")
            out_path = str(output_dir / file_name)
            tasks.append(generate_single(text, out_path, voice, rate, pitch))

    # Run with concurrency limit to avoid overwhelming the TTS service
    sem = asyncio.Semaphore(5)

    async def limited(task):
        async with sem:
            return await task

    await asyncio.gather(*[limited(t) for t in tasks])
    logger.info(f"Generated {len(tasks)} audio files")
    return len(tasks)
