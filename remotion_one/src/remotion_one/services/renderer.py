"""Remotion video rendering."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 3


async def render_video(
    workspace_dir: Path,
    output_name: str = "output.mp4",
    composition_id: str = "MainVideo",
) -> Path:
    """Render video using Remotion CLI.

    Args:
        workspace_dir: Remotion project directory.
        output_name: Output video filename.
        composition_id: Remotion composition ID to render.

    Returns:
        Path to the rendered video file.
    """
    output_path = workspace_dir / output_name

    cmd = (
        f"cd {workspace_dir} && "
        f"npx remotion render {composition_id} {output_name} "
        f"--log=verbose"
    )

    logger.info(f"Rendering: {cmd}")
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        error_output = f"STDOUT:\n{stdout_text}\n\nSTDERR:\n{stderr_text}"
        raise RenderError(error_output)

    if not output_path.exists():
        raise RenderError(f"Render completed but output file not found: {output_path}")

    logger.info(f"Video rendered: {output_path}")
    return output_path


async def render_with_auto_fix(
    workspace_dir: Path,
    video_width: int,
    video_height: int,
    video_fps: int,
    claude_session_id: str,
    output_name: str = "output.mp4",
    composition_id: str = "MainVideo",
) -> tuple[Path, str]:
    """Render video, auto-fix errors using Claude Code SDK.

    Returns:
        Tuple of (video_path, updated_claude_session_id).
    """
    from .remotion_gen import fix_render_error

    current_session_id = claude_session_id

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        try:
            video_path = await render_video(workspace_dir, output_name, composition_id)
            return video_path, current_session_id
        except RenderError as e:
            if attempt >= MAX_FIX_ATTEMPTS:
                raise
            logger.warning(f"Render attempt {attempt} failed, auto-fixing...")
            current_session_id = await fix_render_error(
                workspace_dir=workspace_dir,
                error_output=str(e),
                claude_session_id=current_session_id,
                video_width=video_width,
                video_height=video_height,
                video_fps=video_fps,
            )

    raise RenderError("Max fix attempts reached")


class RenderError(Exception):
    pass
