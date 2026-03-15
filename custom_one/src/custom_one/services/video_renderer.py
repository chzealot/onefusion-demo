from __future__ import annotations

import asyncio
import logging
import shutil
import signal
from pathlib import Path

from custom_one.config import settings

logger = logging.getLogger(__name__)


async def _find_free_port() -> int:
    """Find a free port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def _install_deps(animation_dir: Path) -> None:
    """Install npm dependencies for the animation project."""
    proc = await asyncio.create_subprocess_exec(
        "npm", "install",
        cwd=str(animation_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"npm install failed: {stderr.decode()}")


async def _start_vite_server(animation_dir: Path, port: int) -> asyncio.subprocess.Process:
    """Start Vite dev server and wait for it to be ready."""
    proc = await asyncio.create_subprocess_exec(
        "npx", "vite", "--port", str(port), "--host", "0.0.0.0",
        cwd=str(animation_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Wait for server to be ready by polling
    import httpx

    for _ in range(60):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:{port}/", timeout=2.0)
                if resp.status_code == 200:
                    logger.info("Vite server ready on port %d", port)
                    return proc
        except Exception:
            if proc.returncode is not None:
                stdout_data = await proc.stdout.read() if proc.stdout else b""
                stderr_data = await proc.stderr.read() if proc.stderr else b""
                raise RuntimeError(
                    f"Vite server exited unexpectedly: {stderr_data.decode()}"
                )
            continue

    raise RuntimeError("Vite server failed to start within 60 seconds")


async def _stop_vite_server(proc: asyncio.subprocess.Process) -> None:
    """Stop Vite dev server."""
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
    except Exception:
        pass


async def render_video(
    session_dir: Path,
    total_frames: int,
    on_progress=None,
) -> None:
    """Render the animation project to MP4 using headless browser + ffmpeg."""
    animation_dir = session_dir / "animation"
    frames_dir = session_dir / "frames"
    output_dir = session_dir / "output"
    frames_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Install dependencies
    if on_progress:
        await on_progress("Installing npm dependencies...")
    await _install_deps(animation_dir)

    # Start Vite server
    port = await _find_free_port()
    if on_progress:
        await on_progress(f"Starting dev server on port {port}...")
    vite_proc = await _start_vite_server(animation_dir, port)

    try:
        # Capture frames using Playwright
        if on_progress:
            await on_progress("Capturing frames...")

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={
                    "width": settings.video_width,
                    "height": settings.video_height,
                }
            )

            await page.goto(f"http://localhost:{port}/")
            # Wait for app to load
            await page.wait_for_function(
                "typeof window.__FRAME_READY__ !== 'undefined'",
                timeout=30000,
            )

            for frame in range(total_frames):
                # Set current frame
                await page.evaluate(f"""() => {{
                    window.__CURRENT_FRAME__ = {frame};
                    window.__FRAME_READY__ = false;
                }}""")

                # Wait for frame to be ready
                try:
                    await page.wait_for_function(
                        "window.__FRAME_READY__ === true",
                        timeout=5000,
                    )
                except Exception:
                    # If frame ready signal times out, take screenshot anyway
                    logger.warning("Frame %d ready timeout, capturing anyway", frame)

                # Screenshot
                frame_path = frames_dir / f"frame_{frame:06d}.png"
                await page.screenshot(path=str(frame_path), type="png")

                if on_progress and frame % 30 == 0:
                    pct = int(frame / total_frames * 100)
                    await on_progress(f"Rendering frame {frame}/{total_frames} ({pct}%)")

            await browser.close()

        # Compose video with ffmpeg
        if on_progress:
            await on_progress("Composing video with ffmpeg...")

        combined_audio = session_dir / "audio" / "combined.mp3"
        output_path = output_dir / "output.mp4"

        ffmpeg_args = [
            "ffmpeg", "-y",
            "-framerate", str(settings.video_fps),
            "-i", str(frames_dir / "frame_%06d.png"),
        ]

        if combined_audio.exists():
            ffmpeg_args.extend(["-i", str(combined_audio)])

        ffmpeg_args.extend([
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "23",
        ])

        if combined_audio.exists():
            ffmpeg_args.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ])

        ffmpeg_args.append(str(output_path))

        proc = await asyncio.create_subprocess_exec(
            *ffmpeg_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode()}")

        logger.info("Video rendered: %s", output_path)

        if on_progress:
            await on_progress("Video rendering complete!")

    finally:
        await _stop_vite_server(vite_proc)

    # Clean up frames directory to save disk space
    shutil.rmtree(frames_dir, ignore_errors=True)


async def start_preview_server(animation_dir: Path) -> tuple[asyncio.subprocess.Process, int]:
    """Start a Vite dev server for preview and return (process, port)."""
    await _install_deps(animation_dir)
    port = await _find_free_port()
    proc = await _start_vite_server(animation_dir, port)
    return proc, port
