from __future__ import annotations

import asyncio
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from custom_one.config import settings
from custom_one.models.schemas import (
    SessionData,
    SessionDetail,
    SessionProgress,
    SessionStage,
    SessionSummary,
)


class SessionManager:
    def __init__(self) -> None:
        self._base_dir = settings.workspaces_dir.resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._running_tasks: dict[str, asyncio.Task] = {}

    def _session_dir(self, session_id: str) -> Path:
        return self._base_dir / session_id

    def _session_file(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    async def create(self, article: str, requirements: str) -> SessionData:
        session_id = uuid4().hex[:12]
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "audio").mkdir(exist_ok=True)
        (session_dir / "animation").mkdir(exist_ok=True)
        (session_dir / "output").mkdir(exist_ok=True)

        title = article.strip().split("\n")[0][:60]
        excerpt = article.strip()[:200]

        data = SessionData(
            id=session_id,
            article_title=title,
            article_excerpt=excerpt,
            article=article,
            requirements=requirements,
        )
        await self._save(data)

        # Save article as file for reference
        (session_dir / "article.md").write_text(article, encoding="utf-8")
        if requirements:
            (session_dir / "requirements.txt").write_text(requirements, encoding="utf-8")

        return data

    async def load(self, session_id: str) -> SessionData:
        path = self._session_file(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        text = path.read_text(encoding="utf-8")
        return SessionData.model_validate_json(text)

    async def get_detail(self, session_id: str) -> SessionDetail:
        data = await self.load(session_id)
        sd = self._session_dir(session_id)
        return SessionDetail(
            **data.model_dump(),
            has_video=(sd / "output" / "output.mp4").exists(),
            has_subtitles=(sd / "subtitles.json").exists(),
            has_project_zip=(sd / "project.zip").exists(),
        )

    async def list_sessions(self) -> list[SessionSummary]:
        sessions: list[SessionSummary] = []
        if not self._base_dir.exists():
            return sessions
        for d in sorted(self._base_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            sf = d / "session.json"
            if sf.exists():
                try:
                    data = SessionData.model_validate_json(sf.read_text(encoding="utf-8"))
                    sessions.append(
                        SessionSummary(
                            id=data.id,
                            status=data.status,
                            created_at=data.created_at,
                            updated_at=data.updated_at,
                            article_title=data.article_title,
                            article_excerpt=data.article_excerpt,
                            progress=data.progress,
                        )
                    )
                except Exception:
                    continue
        return sessions

    async def update_status(
        self,
        session_id: str,
        stage: SessionStage,
        *,
        percent: int = 0,
        message: str = "",
        error: str | None = None,
        **extra_fields,
    ) -> None:
        data = await self.load(session_id)
        data.status = stage
        data.progress = SessionProgress(stage=stage, percent=percent, message=message)
        data.updated_at = datetime.now()
        if error is not None:
            data.error = error
        for k, v in extra_fields.items():
            if hasattr(data, k):
                setattr(data, k, v)
        await self._save(data)

    async def save_subtitles(self, session_id: str, subtitles: list[dict]) -> None:
        path = self._session_dir(session_id) / "subtitles.json"
        path.write_text(json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8")

    async def load_subtitles(self, session_id: str) -> list[dict]:
        path = self._session_dir(session_id) / "subtitles.json"
        return json.loads(path.read_text(encoding="utf-8"))

    async def save_audio_durations(self, session_id: str, durations: dict) -> None:
        path = self._session_dir(session_id) / "audio-durations.json"
        path.write_text(json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8")

    async def load_audio_durations(self, session_id: str) -> dict:
        path = self._session_dir(session_id) / "audio-durations.json"
        return json.loads(path.read_text(encoding="utf-8"))

    async def archive_project(self, session_id: str) -> None:
        sd = self._session_dir(session_id)
        animation_dir = sd / "animation"
        zip_path = sd / "project.zip"
        if not animation_dir.exists():
            return

        def _zip():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in animation_dir.rglob("*"):
                    if "node_modules" in f.parts or "__pycache__" in f.parts:
                        continue
                    if f.is_file():
                        zf.write(f, f.relative_to(animation_dir))

        await asyncio.to_thread(_zip)

    async def restore_project(self, session_id: str) -> None:
        sd = self._session_dir(session_id)
        zip_path = sd / "project.zip"
        animation_dir = sd / "animation"
        if not zip_path.exists():
            raise FileNotFoundError(f"No project archive for session {session_id}")

        if animation_dir.exists():
            shutil.rmtree(animation_dir)
        animation_dir.mkdir(parents=True)

        def _unzip():
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(animation_dir)

        await asyncio.to_thread(_unzip)

    async def delete(self, session_id: str) -> None:
        await self.stop_task(session_id)
        sd = self._session_dir(session_id)
        if sd.exists():
            shutil.rmtree(sd)

    def register_task(self, session_id: str, task: asyncio.Task) -> None:
        self._running_tasks[session_id] = task

    async def stop_task(self, session_id: str) -> None:
        task = self._running_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            data = await self.load(session_id)
            if data.status not in (SessionStage.COMPLETED, SessionStage.ERROR):
                await self.update_status(session_id, SessionStage.STOPPED, message="Stopped by user")
        except FileNotFoundError:
            pass

    def is_running(self, session_id: str) -> bool:
        task = self._running_tasks.get(session_id)
        return task is not None and not task.done()

    def get_video_path(self, session_id: str) -> Path | None:
        p = self._session_dir(session_id) / "output" / "output.mp4"
        return p if p.exists() else None

    async def _save(self, data: SessionData) -> None:
        path = self._session_file(data.id)
        path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
