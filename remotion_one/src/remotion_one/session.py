"""Session management - file-based session storage."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .config import settings
from .models import SessionState, SessionStatus


class SessionManager:
    def __init__(self) -> None:
        self._base_dir = settings.workspace_dir

    def _session_dir(self, session_id: str) -> Path:
        return self._base_dir / session_id

    def _state_file(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    def create(
        self,
        article: str,
        requirements: str = "",
        video_width: int | None = None,
        video_height: int | None = None,
        video_fps: int | None = None,
        tts_voice: str | None = None,
    ) -> SessionState:
        session_id = uuid.uuid4().hex[:16]
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        state = SessionState(
            session_id=session_id,
            article=article,
            requirements=requirements,
            video_width=video_width or settings.video_width,
            video_height=video_height or settings.video_height,
            video_fps=video_fps or settings.video_fps,
            tts_voice=tts_voice or settings.tts_voice,
        )
        self._save(state)
        return state

    def get(self, session_id: str) -> SessionState | None:
        state_file = self._state_file(session_id)
        if not state_file.exists():
            return None
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return SessionState(**data)

    def update(
        self,
        session_id: str,
        *,
        status: SessionStatus | None = None,
        current_step: str | None = None,
        progress: int | None = None,
        log: str | None = None,
        error: str | None = None,
        claude_session_id: str | None = None,
        artifacts: dict[str, str] | None = None,
    ) -> SessionState:
        state = self.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")

        if status is not None:
            state.status = status
        if current_step is not None:
            state.current_step = current_step
        if progress is not None:
            state.progress = progress
        if log is not None:
            state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log}")
            # Keep last 200 log lines
            if len(state.logs) > 200:
                state.logs = state.logs[-200:]
        if error is not None:
            state.error = error
        if claude_session_id is not None:
            state.claude_session_id = claude_session_id
        if artifacts is not None:
            state.artifacts.update(artifacts)

        state.updated_at = datetime.now().isoformat()
        self._save(state)
        return state

    def list_sessions(self) -> list[SessionState]:
        sessions = []
        if not self._base_dir.exists():
            return sessions
        for d in sorted(self._base_dir.iterdir(), reverse=True):
            if d.is_dir() and (d / "session.json").exists():
                state = self.get(d.name)
                if state:
                    sessions.append(state)
        return sessions

    def _save(self, state: SessionState) -> None:
        state_file = self._state_file(state.session_id)
        state_file.write_text(state.model_dump_json(indent=2), encoding="utf-8")


session_manager = SessionManager()
