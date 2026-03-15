"""Remotion video renderer: renders scenes and full video via Remotion CLI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from remotion_sub.config import settings

logger = logging.getLogger(__name__)


async def _ensure_deps(remotion_dir: Path) -> None:
    """Install npm dependencies if node_modules doesn't exist."""
    if (remotion_dir / "node_modules").exists():
        return
    logger.info("Installing npm dependencies in %s", remotion_dir)
    proc = await asyncio.create_subprocess_exec(
        "npm", "install",
        cwd=str(remotion_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"npm install failed: {stderr.decode()}")


async def render_scene(
    session_dir: Path,
    scene_num: int,
    video_config: dict | None = None,
    on_progress=None,
) -> Path:
    """Render a single scene composition. Returns path to rendered video."""
    remotion_dir = session_dir / "remotion"
    videos_dir = session_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    output_path = videos_dir / f"scene{scene_num}.mp4"

    await _ensure_deps(remotion_dir)

    width = (video_config or {}).get("width", settings.video_width)
    height = (video_config or {}).get("height", settings.video_height)
    fps = (video_config or {}).get("fps", settings.video_fps)

    composition_id = f"scene-{scene_num}"

    cmd = [
        "npx", "remotion", "render",
        "src/index.ts", composition_id,
        str(output_path),
        f"--width={width}",
        f"--height={height}",
        f"--fps={fps}",
        "--overwrite",
    ]

    logger.info("Rendering scene %d: %s", scene_num, " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(remotion_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_text = stderr.decode() + "\n" + stdout.decode()
        raise RuntimeError(f"Remotion render scene-{scene_num} failed:\n{error_text}")

    if on_progress:
        await on_progress(f"Scene {scene_num} rendered: {output_path.name}")

    logger.info("Scene %d rendered: %s", scene_num, output_path)
    return output_path


async def render_full(
    session_dir: Path,
    video_config: dict | None = None,
    on_progress=None,
) -> Path:
    """Render the full-video composition. Returns path to rendered video."""
    remotion_dir = session_dir / "remotion"
    videos_dir = session_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    output_path = videos_dir / "full.mp4"

    await _ensure_deps(remotion_dir)

    width = (video_config or {}).get("width", settings.video_width)
    height = (video_config or {}).get("height", settings.video_height)
    fps = (video_config or {}).get("fps", settings.video_fps)

    cmd = [
        "npx", "remotion", "render",
        "src/index.ts", "full-video",
        str(output_path),
        f"--width={width}",
        f"--height={height}",
        f"--fps={fps}",
        "--overwrite",
    ]

    logger.info("Rendering full video: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(remotion_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_text = stderr.decode() + "\n" + stdout.decode()
        raise RuntimeError(f"Remotion render full-video failed:\n{error_text}")

    if on_progress:
        await on_progress(f"Full video rendered: {output_path.name}")

    logger.info("Full video rendered: %s", output_path)
    return output_path


async def render_all_scenes(
    session_dir: Path,
    scene_count: int,
    video_config: dict | None = None,
    on_progress=None,
) -> list[Path]:
    """Render all individual scene compositions."""
    paths = []
    for i in range(1, scene_count + 1):
        path = await render_scene(session_dir, i, video_config, on_progress)
        paths.append(path)
    return paths
