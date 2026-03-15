"""FastAPI routes for the REST API."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from ..config import settings
from ..models import (
    ResumeRequest,
    SessionProgress,
    SessionStatus,
    SubmitRequest,
    SubmitResponse,
)
from ..pipeline import run_pipeline, run_resume
from ..session import session_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Track running background tasks
_running_tasks: dict[str, asyncio.Task] = {}


@router.post("/sessions", response_model=SubmitResponse)
async def submit_article(req: SubmitRequest) -> SubmitResponse:
    """Submit an article to convert to video. Returns session_id."""
    state = session_manager.create(
        article=req.article,
        requirements=req.requirements,
        video_width=req.video_width,
        video_height=req.video_height,
        video_fps=req.video_fps,
        tts_voice=req.tts_voice,
    )

    # Start pipeline in background
    task = asyncio.create_task(run_pipeline(state.session_id))
    _running_tasks[state.session_id] = task
    task.add_done_callback(lambda t: _running_tasks.pop(state.session_id, None))

    return SubmitResponse(
        session_id=state.session_id,
        status=state.status,
        message="Pipeline started",
    )


@router.get("/sessions", response_model=list[SessionProgress])
async def list_sessions() -> list[SessionProgress]:
    """List all sessions."""
    states = session_manager.list_sessions()
    return [
        SessionProgress(
            session_id=s.session_id,
            status=s.status,
            current_step=s.current_step,
            progress=s.progress,
            logs=s.logs[-20:],
            error=s.error,
            created_at=s.created_at,
            updated_at=s.updated_at,
            artifacts=s.artifacts,
        )
        for s in states
    ]


@router.get("/sessions/{session_id}", response_model=SessionProgress)
async def get_session(session_id: str) -> SessionProgress:
    """Get session progress and status."""
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionProgress(
        session_id=state.session_id,
        status=state.status,
        current_step=state.current_step,
        progress=state.progress,
        logs=state.logs,
        error=state.error,
        created_at=state.created_at,
        updated_at=state.updated_at,
        artifacts=state.artifacts,
    )


@router.post("/sessions/{session_id}/resume", response_model=SubmitResponse)
async def resume_session(session_id: str, req: ResumeRequest) -> SubmitResponse:
    """Resume a session with new prompt to modify the video."""
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if state.status not in (SessionStatus.COMPLETED, SessionStatus.ERROR):
        raise HTTPException(status_code=400, detail=f"Cannot resume session in {state.status} state")

    # Save uploaded images to workspace
    image_paths: list[str] = []
    workspace = settings.workspace_dir / session_id
    images_dir = workspace / "resume_images"
    if req.images:
        images_dir.mkdir(parents=True, exist_ok=True)
        for i, img_b64 in enumerate(req.images):
            img_data = base64.b64decode(img_b64)
            img_path = images_dir / f"image_{i}.png"
            img_path.write_bytes(img_data)
            image_paths.append(str(img_path))

    # Start resume pipeline in background
    task = asyncio.create_task(run_resume(session_id, req.prompt, image_paths))
    _running_tasks[session_id] = task
    task.add_done_callback(lambda t: _running_tasks.pop(session_id, None))

    return SubmitResponse(
        session_id=session_id,
        status=SessionStatus.CODING,
        message="Resume pipeline started",
    )


@router.get("/sessions/{session_id}/video")
async def get_video(session_id: str) -> FileResponse:
    """Download the rendered video."""
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    video_path = state.artifacts.get("video")
    if not video_path or not Path(video_path).exists():
        raise HTTPException(status_code=404, detail="Video not available")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"{session_id}_output.mp4",
    )


@router.get("/sessions/{session_id}/subtitles")
async def get_subtitles(session_id: str) -> FileResponse:
    """Download subtitles.json."""
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    subtitles_path = state.artifacts.get("subtitles")
    if not subtitles_path or not Path(subtitles_path).exists():
        raise HTTPException(status_code=404, detail="Subtitles not available")

    return FileResponse(
        subtitles_path,
        media_type="application/json",
        filename="subtitles.json",
    )


@router.get("/sessions/{session_id}/project")
async def get_project(session_id: str) -> FileResponse:
    """Download the Remotion project zip."""
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    zip_path = state.artifacts.get("project_zip")
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Project zip not available")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{session_id}_project.zip",
    )
