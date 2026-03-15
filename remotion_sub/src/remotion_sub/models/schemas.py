"""Pydantic models for API request/response and internal data."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class SessionStage(str, enum.Enum):
    CREATED = "CREATED"
    GENERATING_SCRIPT = "GENERATING_SCRIPT"
    GENERATING_TTS = "GENERATING_TTS"
    GENERATING_REMOTION = "GENERATING_REMOTION"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class SessionProgress(BaseModel):
    stage: SessionStage = SessionStage.CREATED
    percent: int = 0
    message: str = ""


# --- API Request Models ---

class SessionCreate(BaseModel):
    article: str = Field(..., min_length=1, description="Article content")
    requirements: str = Field(default="", description="Specific requirements for the video")
    video_width: int = Field(default=1920, description="Video width in pixels")
    video_height: int = Field(default=1080, description="Video height in pixels")
    video_fps: int = Field(default=30, description="Frames per second")


class SessionResumeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Modification instructions")
    images: list[str] = Field(default_factory=list, description="Base64-encoded images")


# --- Internal Data Models ---

class SubtitleSegment(BaseModel):
    file: str
    text: str
    rate: str = "+40%"
    pitch: str = "+0Hz"


class SubtitleScene(BaseModel):
    scene: int
    name: str
    annotation: str = ""
    description: str = ""
    subtitles: list[SubtitleSegment] = Field(default_factory=list)


# --- API Response Models ---

class SessionSummary(BaseModel):
    id: str
    status: SessionStage
    created_at: str
    updated_at: str
    article_title: str
    article_excerpt: str
    progress: SessionProgress
    scene_count: int = 0


class SessionDetail(BaseModel):
    id: str
    status: SessionStage
    created_at: str
    updated_at: str
    article_title: str
    article_excerpt: str
    article: str = ""
    requirements: str = ""
    error: str | None = None
    progress: SessionProgress
    scene_count: int = 0
    resume_count: int = 0
    video_duration_sec: float = 0.0
    total_frames: int = 0
    claude_session_id: str | None = None
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30
    has_video: bool = False
    has_subtitles: bool = False
    has_project_zip: bool = False
    scenes: list[SceneInfo] = Field(default_factory=list)


class SceneInfo(BaseModel):
    scene: int
    name: str
    has_video: bool = False
