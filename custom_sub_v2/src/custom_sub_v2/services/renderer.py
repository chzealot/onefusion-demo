"""Renderer service: Playwright + ffmpeg -> video files.

V2: Renders from a single multi-entry Vite project with scene-specific HTML entries.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from custom_sub_v2.config import settings
from custom_sub_v2.services.logger import get_project_logger


async def render_scene_video(
    project_dir: Path,
    scene_num: int,
    output_path: Path,
    audio_dir: Path,
    scene_data: dict,
    vite_port: int,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    log=None,
) -> None:
    """Render a single scene to video using Playwright frame capture + ffmpeg.

    Uses a shared Vite dev server with scene-specific HTML entry.
    """
    w = width or settings.video_width
    h = height or settings.video_height
    scene_fps = fps or settings.video_fps
    total_frames = scene_data.get("total_frames", 150)

    with tempfile.TemporaryDirectory() as frames_dir:
        frames_path = Path(frames_dir)

        # Capture frames from the scene entry
        await _capture_frames(
            url=f"http://localhost:{vite_port}/scene{scene_num:02d}.html",
            frames_dir=frames_path,
            total_frames=total_frames,
            width=w,
            height=h,
            fps=scene_fps,
            log=log,
        )

        # Merge audio for this scene
        audio_path = frames_path / "scene_audio.mp3"
        await _merge_scene_audio(audio_dir, scene_data, audio_path)

        # Combine frames + audio with ffmpeg
        await _ffmpeg_combine(
            frames_dir=frames_path,
            audio_path=audio_path,
            output_path=output_path,
            fps=scene_fps,
        )

    if log:
        log.info("Scene %d video rendered: %s", scene_num, output_path)


async def render_all_scenes(
    session_dir: Path,
    scenes: list[dict],
    project_id: str = "",
) -> Path:
    """Render all scenes and merge into output.mp4.

    Starts a single Vite dev server for the multi-entry project.
    """
    log = get_project_logger(project_id) if project_id else None
    videos_dir = session_dir / "videos"
    videos_dir.mkdir(exist_ok=True)
    audio_dir = session_dir / "audio"
    project_dir = session_dir / "project"

    # Start Vite dev server once
    vite_port = await _find_free_port()
    vite_proc = await _start_vite(project_dir, vite_port)

    try:
        await _wait_for_server(f"http://localhost:{vite_port}", timeout=30)
        if log:
            log.info("Vite server ready on port %d", vite_port)

        scene_videos = []
        for scene_data in scenes:
            scene_num = scene_data["scene"]
            video_path = videos_dir / f"scene{scene_num}.mp4"

            if log:
                log.info("Rendering scene %d...", scene_num)

            await render_scene_video(
                project_dir=project_dir,
                scene_num=scene_num,
                output_path=video_path,
                audio_dir=audio_dir,
                scene_data=scene_data,
                vite_port=vite_port,
                log=log,
            )
            scene_videos.append(video_path)

    finally:
        vite_proc.terminate()
        try:
            await asyncio.wait_for(vite_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            vite_proc.kill()

    # Merge all scene videos
    output_path = session_dir / "output.mp4"
    if len(scene_videos) == 1:
        shutil.copy2(scene_videos[0], output_path)
    elif len(scene_videos) > 1:
        await _ffmpeg_concat(scene_videos, output_path)

    if log:
        log.info("Full video rendered: %s", output_path)
    return output_path


async def render_single_scene(
    session_dir: Path,
    scene_data: dict,
    project_id: str = "",
) -> Path:
    """Render a single scene to video."""
    log = get_project_logger(project_id) if project_id else None
    scene_num = scene_data["scene"]
    project_dir = session_dir / "project"
    videos_dir = session_dir / "videos"
    videos_dir.mkdir(exist_ok=True)
    video_path = videos_dir / f"scene{scene_num}.mp4"
    audio_dir = session_dir / "audio"

    vite_port = await _find_free_port()
    vite_proc = await _start_vite(project_dir, vite_port)

    try:
        await _wait_for_server(f"http://localhost:{vite_port}", timeout=30)
        await render_scene_video(
            project_dir=project_dir,
            scene_num=scene_num,
            output_path=video_path,
            audio_dir=audio_dir,
            scene_data=scene_data,
            vite_port=vite_port,
            log=log,
        )
    finally:
        vite_proc.terminate()
        try:
            await asyncio.wait_for(vite_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            vite_proc.kill()

    return video_path


# --- Internal helpers ---


async def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


async def _start_vite(project_dir: Path, port: int) -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        "npx", "vite", "--port", str(port), "--host", "127.0.0.1",
        cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def _wait_for_server(url: str, timeout: float = 30) -> None:
    """Wait for a server to become available."""
    import httpx

    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(url, timeout=2)
                if resp.status_code < 500:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
    raise TimeoutError(f"Server at {url} did not start within {timeout}s")


async def _capture_frames(
    url: str,
    frames_dir: Path,
    total_frames: int,
    width: int,
    height: int,
    fps: int,
    log=None,
) -> None:
    """Capture frames using Playwright."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})

        for frame_num in range(total_frames):
            render_url = f"{url}?mode=render&frame={frame_num}&fps={fps}"
            await page.goto(render_url, wait_until="networkidle")

            # Wait for React to signal readiness
            try:
                await page.wait_for_function(
                    "window.__SCENE_READY__ === true",
                    timeout=5000,
                )
            except Exception:
                await page.wait_for_timeout(100)

            # Reset ready flag for next frame
            await page.evaluate("window.__SCENE_READY__ = false")

            frame_path = frames_dir / f"frame_{frame_num:06d}.png"
            await page.screenshot(path=str(frame_path))

            if log and frame_num % 30 == 0:
                log.info("Captured frame %d/%d", frame_num, total_frames)

        await browser.close()


async def _merge_scene_audio(
    audio_dir: Path,
    scene_data: dict,
    output_path: Path,
) -> None:
    """Merge subtitle audio segments into a single audio file for the scene."""
    subtitles = scene_data.get("subtitles", [])
    if not subtitles:
        duration = scene_data.get("total_frames", 150) / settings.video_fps
        await _create_silent_audio(output_path, duration)
        return

    if len(subtitles) == 1:
        src = audio_dir / subtitles[0]["file"]
        if src.exists():
            shutil.copy2(src, output_path)
            return

    # Use ffmpeg to concatenate audio files with correct timing
    fps = settings.video_fps
    filter_parts = []
    inputs = []

    for i, seg in enumerate(subtitles):
        src = audio_dir / seg["file"]
        if not src.exists():
            continue
        inputs.extend(["-i", str(src)])
        start_sec = seg.get("start_frame", 0) / fps
        filter_parts.append(f"[{i}]adelay={int(start_sec * 1000)}|{int(start_sec * 1000)}[a{i}]")

    if not inputs:
        duration = scene_data.get("total_frames", 150) / fps
        await _create_silent_audio(output_path, duration)
        return

    n = len(filter_parts)
    mix_inputs = "".join(f"[a{i}]" for i in range(n))
    filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={n}:duration=longest[out]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ac", "1",
        "-ar", str(settings.tts_sample_rate),
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Fallback: just copy first audio
        for seg in subtitles:
            src = audio_dir / seg["file"]
            if src.exists():
                shutil.copy2(src, output_path)
                break


async def _create_silent_audio(output_path: Path, duration: float) -> None:
    """Create a silent audio file of specified duration."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={settings.tts_sample_rate}:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame",
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


async def _ffmpeg_combine(
    frames_dir: Path,
    audio_path: Path,
    output_path: Path,
    fps: int,
) -> None:
    """Combine PNG frames and audio into an MP4 video."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed: {stderr.decode()[:1000]}")


async def _ffmpeg_concat(video_paths: list[Path], output_path: Path) -> None:
    """Concatenate multiple video files into one using ffmpeg."""
    concat_file = output_path.parent / "concat_list.txt"
    with open(concat_file, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    concat_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {stderr.decode()[:1000]}")
