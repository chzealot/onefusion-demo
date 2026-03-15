"""Pydantic models for API request/response."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionStatus(str, enum.Enum):
    CREATED = "created"
    SCRIPTING = "scripting"
    TTS_GENERATING = "tts_generating"
    CODING = "coding"
    RENDERING = "rendering"
    COMPLETED = "completed"
    ERROR = "error"


class SubmitRequest(BaseModel):
    article: str = Field(..., description="Article content to convert")
    requirements: str = Field(default="", description="Specific requirements for the video")
    video_width: int | None = Field(default=None, description="Video width in pixels")
    video_height: int | None = Field(default=None, description="Video height in pixels")
    video_fps: int | None = Field(default=None, description="Video FPS")
    tts_voice: str | None = Field(default=None, description="TTS voice: yunxi/xiaoxiao/yunyang/xiaoyi")


class SubmitResponse(BaseModel):
    session_id: str
    status: SessionStatus
    message: str


class ResumeRequest(BaseModel):
    prompt: str = Field(..., description="Modification instructions")
    images: list[str] = Field(default_factory=list, description="Base64-encoded images")


class SessionProgress(BaseModel):
    session_id: str
    status: SessionStatus
    current_step: str = ""
    progress: int = 0  # 0-100
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)


class SessionState(BaseModel):
    session_id: str
    status: SessionStatus = SessionStatus.CREATED
    current_step: str = ""
    progress: int = 0
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    article: str = ""
    requirements: str = ""
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30
    tts_voice: str = "yunxi"
    claude_session_id: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
