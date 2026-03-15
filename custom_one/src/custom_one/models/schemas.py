from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class SessionStage(str, enum.Enum):
    CREATED = "CREATED"
    GENERATING_SCRIPT = "GENERATING_SCRIPT"
    GENERATING_TTS = "GENERATING_TTS"
    GENERATING_ANIMATION = "GENERATING_ANIMATION"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class SessionProgress(BaseModel):
    stage: SessionStage = SessionStage.CREATED
    percent: int = 0
    message: str = ""


class SessionCreate(BaseModel):
    article: str = Field(..., min_length=1, description="Article content")
    requirements: str = Field(default="", description="Specific requirements for the video")


class SessionResumeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Modification instructions")
    images: list[str] = Field(default_factory=list, description="Base64-encoded images")


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


class SessionData(BaseModel):
    id: str
    status: SessionStage = SessionStage.CREATED
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    article_title: str = ""
    article_excerpt: str = ""
    article: str = ""
    requirements: str = ""
    error: str | None = None
    progress: SessionProgress = Field(default_factory=SessionProgress)
    resume_count: int = 0
    video_duration_sec: float = 0.0
    total_frames: int = 0
    vite_port: int | None = None
    claude_session_id: str | None = None


class SessionSummary(BaseModel):
    id: str
    status: SessionStage
    created_at: datetime
    updated_at: datetime
    article_title: str
    article_excerpt: str
    progress: SessionProgress


class SessionDetail(SessionData):
    has_video: bool = False
    has_subtitles: bool = False
    has_project_zip: bool = False
