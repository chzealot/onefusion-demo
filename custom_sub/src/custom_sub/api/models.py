"""Pydantic models for API request/response."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class SessionStatus(str, Enum):
    PENDING = "pending"
    GENERATING_SCRIPT = "generating_script"
    GENERATING_TTS = "generating_tts"
    GENERATING_ANIMATION = "generating_animation"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class StepName(str, Enum):
    SCRIPT = "script"
    TTS = "tts"
    ANIMATION = "animation"
    RENDER = "render"
    PACKAGE = "package"


# --- Subtitle Schema ---

class SubtitleSegment(BaseModel):
    file: str
    text: str
    rate: str = "+40%"
    pitch: str = "+0Hz"
    duration_ms: Optional[int] = None  # filled after TTS
    start_frame: Optional[int] = None
    end_frame: Optional[int] = None


class SceneData(BaseModel):
    scene: int
    name: str
    annotation: str
    description: str
    subtitles: list[SubtitleSegment]
    total_frames: Optional[int] = None


# --- API Request Models ---

class SubmitArticleRequest(BaseModel):
    article: str = Field(..., description="Article text to convert")
    requirements: str = Field("", description="Specific requirements for the video")
    video_width: Optional[int] = None
    video_height: Optional[int] = None
    video_fps: Optional[int] = None


class ResumeSessionRequest(BaseModel):
    prompt: str = Field(..., description="Modification prompt (text)")
    images: list[str] = Field(default_factory=list, description="Base64 encoded images")


# --- API Response Models ---

class SubmitArticleResponse(BaseModel):
    session_id: str
    status: SessionStatus
    message: str


class StepProgress(BaseModel):
    name: StepName
    status: str  # pending / in_progress / completed / failed
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SessionProgress(BaseModel):
    session_id: str
    status: SessionStatus
    steps: list[StepProgress]
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    article_preview: str = ""


class SessionListItem(BaseModel):
    session_id: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    article_preview: str = ""


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]


class SceneVideoInfo(BaseModel):
    scene: int
    name: str
    video_url: Optional[str] = None
    preview_url: Optional[str] = None
    ready: bool = False
