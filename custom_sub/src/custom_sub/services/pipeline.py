"""Pipeline orchestration: coordinates the full article → video workflow."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import zipfile
from pathlib import Path

from custom_sub.api.models import SessionStatus, StepName
from custom_sub.config import settings
from custom_sub.services.session import session_manager

logger = logging.getLogger(__name__)

# Track running pipelines so we can cancel them
_running_tasks: dict[str, asyncio.Task] = {}


async def start_pipeline(session_id: str) -> None:
    """Start the full pipeline in a background task."""
    if session_id in _running_tasks and not _running_tasks[session_id].done():
        logger.warning("Pipeline already running for session %s", session_id)
        return

    task = asyncio.create_task(_run_pipeline(session_id))
    _running_tasks[session_id] = task

    # Cleanup on completion
    def _cleanup(t: asyncio.Task) -> None:
        _running_tasks.pop(session_id, None)

    task.add_done_callback(_cleanup)


async def stop_pipeline(session_id: str) -> None:
    """Stop a running pipeline."""
    task = _running_tasks.get(session_id)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await session_manager.stop_session(session_id)


async def resume_pipeline(session_id: str, prompt: str) -> None:
    """Resume a completed/stopped session with modification prompt."""
    session_dir = session_manager.session_dir(session_id)

    # Load current subtitles
    subtitles_path = session_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise RuntimeError("No subtitles.json found for this session")

    with open(subtitles_path) as f:
        scenes = json.load(f)

    # Update status
    await session_manager.update_status(session_id, status=SessionStatus.GENERATING_ANIMATION)
    version = await session_manager.increment_version(session_id)

    # Run modification in background
    task = asyncio.create_task(
        _run_resume(session_id, prompt, scenes, version)
    )
    _running_tasks[session_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        _running_tasks.pop(session_id, None)

    task.add_done_callback(_cleanup)


def is_running(session_id: str) -> bool:
    task = _running_tasks.get(session_id)
    return task is not None and not task.done()


# --- Internal pipeline steps ---


async def _run_pipeline(session_id: str) -> None:
    """Execute the full pipeline."""
    session_dir = session_manager.session_dir(session_id)

    try:
        # Step 1: Generate script
        await session_manager.update_status(session_id, status=SessionStatus.GENERATING_SCRIPT)
        await session_manager.update_step(session_id, StepName.SCRIPT, "in_progress")

        from custom_sub.services.scriptwriter import generate_script

        article = await session_manager.get_article(session_id)
        requirements = await session_manager.get_requirements(session_id)
        scenes = await generate_script(session_dir, article, requirements)

        await session_manager.update_step(
            session_id, StepName.SCRIPT, "completed",
            message=f"Generated {len(scenes)} scenes",
        )

        # Step 2: TTS
        await session_manager.update_status(session_id, status=SessionStatus.GENERATING_TTS)
        await session_manager.update_step(session_id, StepName.TTS, "in_progress")

        from custom_sub.services.tts import generate_tts_for_session

        scenes = await generate_tts_for_session(session_dir)

        total_segs = sum(len(s.get("subtitles", [])) for s in scenes)
        await session_manager.update_step(
            session_id, StepName.TTS, "completed",
            message=f"Generated {total_segs} audio segments",
        )

        # Step 3: Generate animations
        await session_manager.update_status(session_id, status=SessionStatus.GENERATING_ANIMATION)
        await session_manager.update_step(session_id, StepName.ANIMATION, "in_progress")

        from custom_sub.services.animator import generate_animations

        await generate_animations(session_dir, scenes)

        await session_manager.update_step(
            session_id, StepName.ANIMATION, "completed",
            message=f"Generated animations for {len(scenes)} scenes",
        )

        # Step 4: Render video
        await session_manager.update_status(session_id, status=SessionStatus.RENDERING)
        await session_manager.update_step(session_id, StepName.RENDER, "in_progress")

        from custom_sub.services.renderer import render_all_scenes

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await render_all_scenes(session_dir, scenes)
                break
            except Exception as render_err:
                logger.error(
                    "Render attempt %d failed: %s", attempt + 1, render_err
                )
                if attempt < max_retries - 1:
                    # Use Claude Agent SDK to fix render errors
                    await _fix_render_error(session_dir, scenes, str(render_err))
                else:
                    raise

        await session_manager.update_step(
            session_id, StepName.RENDER, "completed",
            message="Video rendered successfully",
        )

        # Step 5: Package
        await session_manager.update_step(session_id, StepName.PACKAGE, "in_progress")
        await _package_project(session_dir)
        await session_manager.update_step(
            session_id, StepName.PACKAGE, "completed",
            message="Project packaged",
        )

        # Done
        await session_manager.update_status(session_id, status=SessionStatus.COMPLETED)
        logger.info("Pipeline completed for session %s", session_id)

    except asyncio.CancelledError:
        await session_manager.update_status(session_id, status=SessionStatus.STOPPED)
        logger.info("Pipeline cancelled for session %s", session_id)
        raise

    except Exception as e:
        logger.exception("Pipeline failed for session %s", session_id)
        await session_manager.update_status(
            session_id,
            status=SessionStatus.FAILED,
            error=str(e),
        )
        # Mark current step as failed
        for step in StepName:
            data = await session_manager.get_status_data(session_id)
            step_data = data["steps"][step.value]
            if step_data["status"] == "in_progress":
                await session_manager.update_step(
                    session_id, step, "failed", message=str(e)
                )


async def _run_resume(
    session_id: str,
    prompt: str,
    scenes: list[dict],
    version: int,
) -> None:
    """Execute the resume/modify pipeline."""
    session_dir = session_manager.session_dir(session_id)

    try:
        await session_manager.update_step(session_id, StepName.ANIMATION, "in_progress")

        from custom_sub.services.animator import resume_and_modify

        await resume_and_modify(session_dir, prompt, scenes)

        await session_manager.update_step(
            session_id, StepName.ANIMATION, "completed",
            message=f"Modifications applied (v{version})",
        )

        # Re-render
        await session_manager.update_status(session_id, status=SessionStatus.RENDERING)
        await session_manager.update_step(session_id, StepName.RENDER, "in_progress")

        from custom_sub.services.renderer import render_all_scenes

        await render_all_scenes(session_dir, scenes)

        await session_manager.update_step(
            session_id, StepName.RENDER, "completed",
            message=f"Re-rendered (v{version})",
        )

        # Re-package
        await session_manager.update_step(session_id, StepName.PACKAGE, "in_progress")
        await _package_project(session_dir)
        await session_manager.update_step(
            session_id, StepName.PACKAGE, "completed",
        )

        await session_manager.update_status(session_id, status=SessionStatus.COMPLETED)

    except asyncio.CancelledError:
        await session_manager.update_status(session_id, status=SessionStatus.STOPPED)
        raise
    except Exception as e:
        logger.exception("Resume pipeline failed for session %s", session_id)
        await session_manager.update_status(
            session_id, status=SessionStatus.FAILED, error=str(e)
        )


async def _fix_render_error(
    session_dir: Path,
    scenes: list[dict],
    error_msg: str,
) -> None:
    """Use Claude Agent SDK to fix render errors in scene code."""
    from claude_code_sdk import ClaudeCodeOptions, query

    for scene_data in scenes:
        scene_dir_path = session_dir / "scenes" / f"scene{scene_data['scene']}"
        if not scene_dir_path.exists():
            continue

        prompt = f"""视频渲染过程中出现了错误，请修复代码：

错误信息：
{error_msg}

请检查 src/SceneContent.tsx 和相关文件，修复导致渲染失败的问题。
常见问题包括：
1. 导入路径错误
2. TypeScript 类型错误
3. 运行时错误（undefined 访问等）

请直接修改文件修复问题。
"""
        async for _ in query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                model=settings.openrouter_model,
                cwd=str(scene_dir_path),
                allowed_tools=["Write", "Edit", "Read", "Bash"],
                max_turns=10,
                permission_mode="bypassPermissions",
                env={
                    "ANTHROPIC_AUTH_TOKEN": settings.openrouter_api_key,
                    "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
                    "ANTHROPIC_API_KEY": "",
                },
            ),
        ):
            pass


async def _package_project(session_dir: Path) -> None:
    """Package scene projects into a zip file."""
    scenes_dir = session_dir / "scenes"
    zip_path = session_dir / "project.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in scenes_dir.walk():
            # Skip node_modules
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for file in files:
                file_path = root / file
                arcname = file_path.relative_to(session_dir)
                zf.write(file_path, arcname)

    logger.info("Project packaged: %s", zip_path)
