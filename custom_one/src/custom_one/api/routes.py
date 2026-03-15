from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from custom_one.models.schemas import (
    SessionCreate,
    SessionDetail,
    SessionResumeRequest,
    SessionStage,
    SessionSummary,
)
from custom_one.services.pipeline import Pipeline
from custom_one.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Shared instances (initialized in main.py lifespan)
session_manager: SessionManager | None = None
pipeline: Pipeline | None = None


def _sm() -> SessionManager:
    assert session_manager is not None
    return session_manager


def _pl() -> Pipeline:
    assert pipeline is not None
    return pipeline


@router.post("/sessions", response_model=SessionDetail)
async def create_session(req: SessionCreate):
    sm = _sm()
    session = await sm.create(req.article, req.requirements)

    # Launch pipeline as background task
    task = asyncio.create_task(_pl().run(session.id))
    sm.register_task(session.id, task)

    return await sm.get_detail(session.id)


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions():
    return await _sm().list_sessions()


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str):
    try:
        return await _sm().get_detail(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")


@router.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    try:
        detail = await _sm().get_detail(session_id)
        return {
            "id": detail.id,
            "status": detail.status,
            "progress": detail.progress.model_dump(),
            "error": detail.error,
            "has_video": detail.has_video,
        }
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")


@router.get("/sessions/{session_id}/stream")
async def stream_session_status(session_id: str):
    """SSE endpoint for real-time status updates."""
    sm = _sm()

    async def event_generator():
        last_status = None
        while True:
            try:
                detail = await sm.get_detail(session_id)
                current = detail.model_dump_json()
                if current != last_status:
                    last_status = current
                    yield {"event": "status", "data": current}

                if detail.status in (
                    SessionStage.COMPLETED,
                    SessionStage.ERROR,
                    SessionStage.STOPPED,
                ):
                    yield {"event": "done", "data": current}
                    break
            except FileNotFoundError:
                yield {"event": "error", "data": '{"error": "Session not found"}'}
                break

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


@router.post("/sessions/{session_id}/resume", response_model=SessionDetail)
async def resume_session(session_id: str, req: SessionResumeRequest):
    sm = _sm()
    try:
        session = await sm.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")

    if sm.is_running(session_id):
        raise HTTPException(409, "Session is still running")

    if session.status not in (SessionStage.COMPLETED, SessionStage.ERROR, SessionStage.STOPPED):
        raise HTTPException(
            400,
            f"Cannot resume session in state {session.status}. Must be COMPLETED, ERROR, or STOPPED.",
        )

    task = asyncio.create_task(_pl().resume(session_id, req.prompt, req.images))
    sm.register_task(session_id, task)

    return await sm.get_detail(session_id)


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    sm = _sm()
    try:
        await sm.stop_task(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")
    return {"status": "stopped"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    sm = _sm()
    try:
        await sm.delete(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")
    return {"status": "deleted"}


@router.get("/sessions/{session_id}/video")
async def get_video(session_id: str):
    sm = _sm()
    video_path = sm.get_video_path(session_id)
    if not video_path:
        raise HTTPException(404, "Video not found")
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"{session_id}_output.mp4",
    )


@router.get("/sessions/{session_id}/subtitles")
async def get_subtitles(session_id: str):
    sm = _sm()
    try:
        subtitles = await sm.load_subtitles(session_id)
        return subtitles
    except FileNotFoundError:
        raise HTTPException(404, "Subtitles not found")


@router.get("/sessions/{session_id}/preview-url")
async def get_preview_url(session_id: str):
    """Get the Vite dev server URL for iframe preview."""
    sm = _sm()
    try:
        session = await sm.load(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")

    if session.vite_port:
        return {"url": f"http://localhost:{session.vite_port}/"}

    # Start preview server if animation exists
    animation_dir = sm._session_dir(session_id) / "animation"
    if not animation_dir.exists() or not (animation_dir / "package.json").exists():
        raise HTTPException(404, "Animation project not found")

    from custom_one.services.video_renderer import start_preview_server

    proc, port = await start_preview_server(animation_dir)
    await sm.update_status(session_id, session.status, vite_port=port)

    return {"url": f"http://localhost:{port}/"}
