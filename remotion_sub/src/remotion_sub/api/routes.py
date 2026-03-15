"""FastAPI REST API routes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from remotion_sub.models.schemas import (
    SessionCreate,
    SessionDetail,
    SessionResumeRequest,
    SessionStage,
    SessionSummary,
)
from remotion_sub.services.pipeline import Pipeline
from remotion_sub.services.session import SessionManager

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
    session_id = await sm.create(
        req.article, req.requirements,
        req.video_width, req.video_height, req.video_fps,
    )

    task = asyncio.create_task(_pl().run(session_id))
    sm.register_task(session_id, task)

    return await sm.get_detail(session_id)


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
            "scenes": [s.model_dump() for s in detail.scenes],
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
        detail = await sm.get_detail(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")

    if sm.is_running(session_id):
        raise HTTPException(409, "Session is still running")

    if detail.status not in (SessionStage.COMPLETED, SessionStage.ERROR, SessionStage.STOPPED):
        raise HTTPException(
            400,
            f"Cannot resume session in state {detail.status}. Must be COMPLETED, ERROR, or STOPPED.",
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


@router.post("/sessions/{session_id}/render")
async def render_full_video(session_id: str):
    """Trigger rendering of the full video from existing Remotion project."""
    sm = _sm()
    try:
        detail = await sm.get_detail(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Session {session_id} not found")

    if sm.is_running(session_id):
        raise HTTPException(409, "Session is still running")

    task = asyncio.create_task(_pl().render_full_video(session_id))
    sm.register_task(session_id, task)

    return {"status": "rendering"}


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


@router.get("/sessions/{session_id}/scenes/{scene_num}/video")
async def get_scene_video(session_id: str, scene_num: int):
    sm = _sm()
    video_path = sm.get_scene_video_path(session_id, scene_num)
    if not video_path:
        raise HTTPException(404, f"Scene {scene_num} video not found")
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"{session_id}_scene{scene_num}.mp4",
    )


@router.get("/sessions/{session_id}/subtitles")
async def get_subtitles(session_id: str):
    sm = _sm()
    try:
        return await sm.load_subtitles(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Subtitles not found")
