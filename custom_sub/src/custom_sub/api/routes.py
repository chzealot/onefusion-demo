"""FastAPI REST API routes."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from custom_sub.api.models import (
    ResumeSessionRequest,
    SceneVideoInfo,
    SessionListResponse,
    SessionStatus,
    SubmitArticleRequest,
    SubmitArticleResponse,
)
from custom_sub.services.pipeline import is_running, resume_pipeline, start_pipeline, stop_pipeline
from custom_sub.services.session import session_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# --- 1. Submit article ---

@router.post("/sessions", response_model=SubmitArticleResponse)
async def submit_article(req: SubmitArticleRequest):
    """Submit an article and start the video generation pipeline."""
    session_id = await session_manager.create_session(
        article=req.article,
        requirements=req.requirements,
        video_width=req.video_width,
        video_height=req.video_height,
        video_fps=req.video_fps,
    )

    # Start pipeline asynchronously
    await start_pipeline(session_id)

    return SubmitArticleResponse(
        session_id=session_id,
        status=SessionStatus.PENDING,
        message="Pipeline started",
    )


# --- 2. Query progress ---

@router.get("/sessions/{session_id}")
async def get_session_progress(session_id: str):
    """Get the progress of a session."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    progress = await session_manager.get_progress(session_id)
    return progress


# --- 3. Resume with modifications ---

@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, req: ResumeSessionRequest):
    """Resume a completed/stopped session with new modification prompt."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    progress = await session_manager.get_progress(session_id)
    if progress.status not in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume session in {progress.status} state",
        )

    await resume_pipeline(session_id, req.prompt)

    return {"session_id": session_id, "message": "Resume started"}


# --- 4. Get full video ---

@router.get("/sessions/{session_id}/video")
async def get_video(session_id: str):
    """Download the rendered full video."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    video_path = session_manager.session_dir(session_id) / "output.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not ready yet")

    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"custom_sub_{session_id}.mp4",
    )


# --- 5. Get scene videos ---

@router.get("/sessions/{session_id}/scenes")
async def list_scenes(session_id: str):
    """List all scenes with their video/preview status."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    session_dir = session_manager.session_dir(session_id)
    subtitles_path = session_dir / "subtitles.json"

    if not subtitles_path.exists():
        return {"scenes": []}

    with open(subtitles_path) as f:
        scenes_data = json.load(f)

    scenes = []
    for s in scenes_data:
        scene_num = s["scene"]
        video_path = session_dir / "videos" / f"scene{scene_num}.mp4"
        scene_dir = session_dir / "scenes" / f"scene{scene_num}"

        scenes.append(SceneVideoInfo(
            scene=scene_num,
            name=s.get("name", f"Scene {scene_num}"),
            video_url=f"/api/sessions/{session_id}/scenes/{scene_num}/video" if video_path.exists() else None,
            preview_url=f"/api/sessions/{session_id}/scenes/{scene_num}/preview" if scene_dir.exists() else None,
            ready=video_path.exists(),
        ))

    return {"scenes": scenes}


@router.get("/sessions/{session_id}/scenes/{scene_num}/video")
async def get_scene_video(session_id: str, scene_num: int):
    """Download a single scene's video."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    video_path = session_manager.session_dir(session_id) / "videos" / f"scene{scene_num}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Scene video not ready")

    return FileResponse(str(video_path), media_type="video/mp4")


# --- 6. Render and download full video ---

@router.post("/sessions/{session_id}/render")
async def render_full_video(session_id: str):
    """Trigger rendering of full video from individual scene videos."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    session_dir = session_manager.session_dir(session_id)
    subtitles_path = session_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise HTTPException(status_code=400, detail="No subtitles.json found")

    with open(subtitles_path) as f:
        scenes = json.load(f)

    from custom_sub.services.renderer import render_all_scenes

    await render_all_scenes(session_dir, scenes)
    return {"message": "Video rendered", "url": f"/api/sessions/{session_id}/video"}


# --- Session management ---

@router.get("/sessions")
async def list_sessions():
    """List all sessions."""
    items = await session_manager.list_sessions()
    return SessionListResponse(sessions=items)


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    """Stop a running session (does not delete)."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if is_running(session_id):
        await stop_pipeline(session_id)
    else:
        await session_manager.stop_session(session_id)

    return {"message": "Session stopped"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session. Stops it first if running."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if is_running(session_id):
        await stop_pipeline(session_id)

    await session_manager.delete_session(session_id)
    return {"message": "Session deleted"}


# --- Scene preview proxy ---

@router.get("/sessions/{session_id}/scenes/{scene_num}/preview")
async def get_scene_preview_info(session_id: str, scene_num: int):
    """Get the preview URL for a scene (Vite dev server must be started separately)."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    scene_dir = session_manager.session_dir(session_id) / "scenes" / f"scene{scene_num}"
    if not scene_dir.exists():
        raise HTTPException(status_code=404, detail="Scene not found")

    return {
        "scene": scene_num,
        "scene_dir": str(scene_dir),
        "message": "Start vite dev server with: cd <scene_dir> && npm run dev",
    }


# --- Download project zip ---

@router.get("/sessions/{session_id}/download")
async def download_project(session_id: str):
    """Download the project source code as a zip file."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    zip_path = session_manager.session_dir(session_id) / "project.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Project zip not ready")

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"custom_sub_{session_id}_project.zip",
    )


# --- Subtitles ---

@router.get("/sessions/{session_id}/subtitles")
async def get_subtitles(session_id: str):
    """Get the subtitles.json content."""
    if not session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    path = session_manager.session_dir(session_id) / "subtitles.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Subtitles not ready")

    with open(path) as f:
        return json.load(f)
