"""FastAPI REST API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse

from custom_sub_v2.api.models import (
    ResumeSessionRequest,
    SceneVideoInfo,
    SessionListResponse,
    SessionStatus,
    SubmitArticleRequest,
    SubmitArticleResponse,
)
from custom_sub_v2.services.logger import get_project_logger
from custom_sub_v2.services.pipeline import is_running, resume_pipeline, start_pipeline, stop_pipeline
from custom_sub_v2.services.session import session_manager

router = APIRouter(prefix="/api")


# --- 1. Submit article ---

@router.post("/sessions", response_model=SubmitArticleResponse)
async def submit_article(req: SubmitArticleRequest):
    """Submit an article and start the video generation pipeline."""
    project_id = await session_manager.create_session(
        article=req.article,
        requirements=req.requirements,
        video_width=req.video_width,
        video_height=req.video_height,
        video_fps=req.video_fps,
    )

    agent_id = await session_manager.get_agent_id(project_id) or ""

    # Start pipeline asynchronously
    await start_pipeline(project_id)

    return SubmitArticleResponse(
        project_id=project_id,
        agent_id=agent_id,
        status=SessionStatus.PENDING,
        message="Pipeline started",
    )


# --- 2. Query progress ---

@router.get("/sessions/{project_id}")
async def get_session_progress(project_id: str):
    """Get the progress of a session."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")
    progress = await session_manager.get_progress(project_id)
    return progress


# --- 3. Resume with modifications ---

@router.post("/sessions/{project_id}/resume")
async def resume_session(project_id: str, req: ResumeSessionRequest):
    """Resume a completed/stopped session with new modification prompt."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    progress = await session_manager.get_progress(project_id)
    if progress.status not in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.STOPPED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume session in {progress.status} state",
        )

    await resume_pipeline(project_id, req.prompt)

    return {"project_id": project_id, "message": "Resume started"}


# --- 4. Get full video ---

@router.get("/sessions/{project_id}/video")
async def get_video(project_id: str):
    """Download the rendered full video."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    video_path = session_manager.session_dir(project_id) / "output.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not ready yet")

    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"custom_sub_v2_{project_id}.mp4",
    )


# --- 5. Get scene videos ---

@router.get("/sessions/{project_id}/scenes")
async def list_scenes(project_id: str):
    """List all scenes with their video/preview status."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    session_dir = session_manager.session_dir(project_id)
    subtitles_path = session_dir / "subtitles.json"

    if not subtitles_path.exists():
        return {"scenes": []}

    with open(subtitles_path) as f:
        scenes_data = json.load(f)

    scenes = []
    for s in scenes_data:
        scene_num = s["scene"]
        video_path = session_dir / "videos" / f"scene{scene_num}.mp4"
        scene_dir_path = session_dir / "project" / "src" / "scenes" / f"Scene{scene_num:02d}"

        scenes.append(SceneVideoInfo(
            scene=scene_num,
            name=s.get("name", f"Scene {scene_num}"),
            video_url=f"/api/sessions/{project_id}/scenes/{scene_num}/video" if video_path.exists() else None,
            preview_url=f"/api/sessions/{project_id}/scenes/{scene_num}/preview" if scene_dir_path.exists() else None,
            ready=video_path.exists(),
        ))

    return {"scenes": scenes}


@router.get("/sessions/{project_id}/scenes/{scene_num}/video")
async def get_scene_video(project_id: str, scene_num: int):
    """Download a single scene's video."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    video_path = session_manager.session_dir(project_id) / "videos" / f"scene{scene_num}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Scene video not ready")

    return FileResponse(str(video_path), media_type="video/mp4")


# --- 6. Render full video ---

@router.post("/sessions/{project_id}/render")
async def render_full_video(project_id: str):
    """Trigger rendering of full video from individual scene videos."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    session_dir = session_manager.session_dir(project_id)
    subtitles_path = session_dir / "subtitles.json"
    if not subtitles_path.exists():
        raise HTTPException(status_code=400, detail="No subtitles.json found")

    with open(subtitles_path) as f:
        scenes = json.load(f)

    from custom_sub_v2.services.renderer import render_all_scenes

    await render_all_scenes(session_dir, scenes, project_id=project_id)
    return {"message": "Video rendered", "url": f"/api/sessions/{project_id}/video"}


# --- Session management ---

@router.get("/sessions")
async def list_sessions():
    """List all sessions."""
    items = await session_manager.list_sessions()
    return SessionListResponse(sessions=items)


@router.post("/sessions/{project_id}/stop")
async def stop_session(project_id: str):
    """Stop a running session."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if is_running(project_id):
        await stop_pipeline(project_id)
    else:
        await session_manager.stop_session(project_id)

    return {"message": "Session stopped"}


@router.delete("/sessions/{project_id}")
async def delete_session(project_id: str):
    """Delete a session. Stops it first if running."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    if is_running(project_id):
        await stop_pipeline(project_id)

    await session_manager.delete_session(project_id)
    return {"message": "Session deleted"}


# --- Subtitles ---

@router.get("/sessions/{project_id}/subtitles")
async def get_subtitles(project_id: str):
    """Get the subtitles.json content."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    path = session_manager.session_dir(project_id) / "subtitles.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Subtitles not ready")

    with open(path) as f:
        return json.load(f)


# --- Download project zip ---

@router.get("/sessions/{project_id}/download")
async def download_project(project_id: str):
    """Download the project source code as a zip file."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    zip_path = session_manager.session_dir(project_id) / "project.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Project zip not ready")

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"custom_sub_v2_{project_id}_project.zip",
    )


# --- Log streaming (SSE) ---

@router.get("/sessions/{project_id}/logs")
async def stream_logs(project_id: str):
    """Stream project logs via Server-Sent Events."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    log = get_project_logger(project_id)

    async def _generate():
        async for line in log.stream():
            yield f"data: {line}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# --- Scene preview info ---

@router.get("/sessions/{project_id}/scenes/{scene_num}/preview")
async def get_scene_preview_info(project_id: str, scene_num: int):
    """Get the preview URL for a scene."""
    if not session_manager.session_exists(project_id):
        raise HTTPException(status_code=404, detail="Session not found")

    project_dir = session_manager.session_dir(project_id) / "project"
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "scene": scene_num,
        "project_dir": str(project_dir),
        "entry": f"scene{scene_num:02d}.html",
        "message": f"Start vite dev server and open /scene{scene_num:02d}.html",
    }
