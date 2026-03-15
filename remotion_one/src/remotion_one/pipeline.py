"""Main pipeline orchestration - ties all services together."""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path

from .config import settings
from .models import SessionStatus
from .services import remotion_gen, renderer, scriptwriter, tts
from .session import session_manager

logger = logging.getLogger(__name__)


def _workspace_dir(session_id: str) -> Path:
    return settings.workspace_dir / session_id


async def run_pipeline(session_id: str) -> None:
    """Run the full article-to-video pipeline."""
    state = session_manager.get(session_id)
    if state is None:
        raise ValueError(f"Session {session_id} not found")

    workspace = _workspace_dir(session_id)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        settings.validate()
        # Step 1: Generate subtitles script
        session_manager.update(
            session_id, status=SessionStatus.SCRIPTING,
            current_step="Generating video script", progress=10,
            log="Starting script generation from article...",
        )
        subtitles_path = workspace / "subtitles.json"
        await scriptwriter.generate_subtitles(
            article=state.article,
            requirements=state.requirements,
            output_path=subtitles_path,
        )
        session_manager.update(
            session_id, progress=25,
            log="Script generation completed",
            artifacts={"subtitles": str(subtitles_path)},
        )

        # Step 2: TTS generation
        session_manager.update(
            session_id, status=SessionStatus.TTS_GENERATING,
            current_step="Generating TTS audio", progress=30,
            log="Starting TTS audio generation...",
        )
        audio_dir = workspace / "public" / "audio"
        count = await tts.generate_all(subtitles_path, audio_dir, state.tts_voice)
        session_manager.update(
            session_id, progress=45,
            log=f"TTS completed: {count} audio files generated",
        )

        # Step 3: Generate Remotion project code
        session_manager.update(
            session_id, status=SessionStatus.CODING,
            current_step="Generating Remotion project", progress=50,
            log="Starting Remotion code generation via Claude Code SDK...",
        )
        claude_session_id = await remotion_gen.generate_remotion_project(
            workspace_dir=workspace,
            video_width=state.video_width,
            video_height=state.video_height,
            video_fps=state.video_fps,
        )
        session_manager.update(
            session_id, progress=70,
            log="Remotion project code generated",
            claude_session_id=claude_session_id,
        )

        # Step 4: Render video (with auto-fix)
        session_manager.update(
            session_id, status=SessionStatus.RENDERING,
            current_step="Rendering video", progress=75,
            log="Starting video rendering...",
        )
        video_path, claude_session_id = await renderer.render_with_auto_fix(
            workspace_dir=workspace,
            video_width=state.video_width,
            video_height=state.video_height,
            video_fps=state.video_fps,
            claude_session_id=claude_session_id,
        )
        session_manager.update(
            session_id, claude_session_id=claude_session_id,
        )

        # Step 5: Package artifacts
        zip_path = _package_project(workspace, session_id)
        session_manager.update(
            session_id, status=SessionStatus.COMPLETED,
            current_step="Completed", progress=100,
            log="Pipeline completed successfully",
            artifacts={
                "subtitles": str(subtitles_path),
                "video": str(video_path),
                "project_zip": str(zip_path),
            },
        )

    except Exception as e:
        logger.exception(f"Pipeline error for session {session_id}")
        session_manager.update(
            session_id, status=SessionStatus.ERROR,
            error=str(e), log=f"Error: {e}",
        )


async def run_resume(session_id: str, prompt: str, image_paths: list[str] | None = None) -> None:
    """Resume a session with a new prompt to modify the video."""
    state = session_manager.get(session_id)
    if state is None:
        raise ValueError(f"Session {session_id} not found")

    workspace = _workspace_dir(session_id)

    # Restore project from zip if needed
    zip_path = state.artifacts.get("project_zip")
    if zip_path and Path(zip_path).exists():
        _restore_project(Path(zip_path), workspace)

    try:
        # Build prompt with image references
        full_prompt = prompt
        if image_paths:
            full_prompt += "\n\n请查看以下参考图片：\n"
            for img_path in image_paths:
                full_prompt += f"- {img_path}\n"

        # Use Claude Code SDK to modify the project
        session_manager.update(
            session_id, status=SessionStatus.CODING,
            current_step="Modifying Remotion project", progress=30,
            log=f"Resuming with prompt: {prompt[:100]}...",
            error=None,
        )
        claude_session_id = await remotion_gen.generate_remotion_project(
            workspace_dir=workspace,
            video_width=state.video_width,
            video_height=state.video_height,
            video_fps=state.video_fps,
            resume_session_id=state.claude_session_id,
            extra_prompt=full_prompt,
        )
        session_manager.update(
            session_id, progress=60,
            log="Project modification completed",
            claude_session_id=claude_session_id,
        )

        # Re-render
        session_manager.update(
            session_id, status=SessionStatus.RENDERING,
            current_step="Re-rendering video", progress=70,
            log="Starting video re-rendering...",
        )
        video_path, claude_session_id = await renderer.render_with_auto_fix(
            workspace_dir=workspace,
            video_width=state.video_width,
            video_height=state.video_height,
            video_fps=state.video_fps,
            claude_session_id=claude_session_id,
        )

        # Re-package
        zip_path_new = _package_project(workspace, session_id)
        session_manager.update(
            session_id, status=SessionStatus.COMPLETED,
            current_step="Completed", progress=100,
            log="Resume completed successfully",
            claude_session_id=claude_session_id,
            artifacts={
                "subtitles": str(workspace / "subtitles.json"),
                "video": str(video_path),
                "project_zip": str(zip_path_new),
            },
        )

    except Exception as e:
        logger.exception(f"Resume error for session {session_id}")
        session_manager.update(
            session_id, status=SessionStatus.ERROR,
            error=str(e), log=f"Resume error: {e}",
        )


def _package_project(workspace: Path, session_id: str) -> Path:
    """Package the Remotion project into a zip file."""
    zip_path = workspace / "project.zip"
    if zip_path.exists():
        zip_path.unlink()

    skip_dirs = {"node_modules", ".git", "__pycache__"}
    skip_files = {"output.mp4", "project.zip", "session.json"}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(workspace)
                # Skip large/unnecessary files
                if any(part in skip_dirs for part in rel.parts):
                    continue
                if rel.name in skip_files:
                    continue
                zf.write(file_path, rel)

    logger.info(f"Project packaged: {zip_path}")
    return zip_path


def _restore_project(zip_path: Path, workspace: Path) -> None:
    """Restore project from zip, preserving session.json."""
    session_json = workspace / "session.json"
    session_backup = None
    if session_json.exists():
        session_backup = session_json.read_text(encoding="utf-8")

    # Extract zip
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(workspace)

    # Restore session.json
    if session_backup:
        session_json.write_text(session_backup, encoding="utf-8")
