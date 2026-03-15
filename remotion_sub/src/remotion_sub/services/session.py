"""Session manager: CRUD operations on sessions via SQLite."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite

from remotion_sub.config import settings
from remotion_sub.models.schemas import (
    SceneInfo,
    SessionDetail,
    SessionProgress,
    SessionStage,
    SessionSummary,
)

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db
        self._base_dir = settings.workspaces_dir.resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._running_tasks: dict[str, asyncio.Task] = {}

    def session_dir(self, session_id: str) -> Path:
        return self._base_dir / session_id

    async def create(
        self,
        article: str,
        requirements: str = "",
        video_width: int = 0,
        video_height: int = 0,
        video_fps: int = 0,
    ) -> str:
        session_id = uuid4().hex[:12]
        sd = self.session_dir(session_id)
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "audio").mkdir(exist_ok=True)
        (sd / "remotion").mkdir(exist_ok=True)
        (sd / "videos").mkdir(exist_ok=True)

        title = article.strip().split("\n")[0][:60]
        excerpt = article.strip()[:200]
        now = datetime.now(timezone.utc).isoformat()

        w = video_width or settings.video_width
        h = video_height or settings.video_height
        fps = video_fps or settings.video_fps

        await self.db.execute(
            """INSERT INTO sessions
               (id, article, article_title, article_excerpt, requirements,
                video_width, video_height, video_fps, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, article, title, excerpt, requirements, w, h, fps, now, now),
        )
        await self.db.commit()

        # Save article as file for reference
        (sd / "article.md").write_text(article, encoding="utf-8")
        if requirements:
            (sd / "requirements.txt").write_text(requirements, encoding="utf-8")

        return session_id

    async def get_detail(self, session_id: str) -> SessionDetail:
        row = await self._get_row(session_id)
        sd = self.session_dir(session_id)

        # Build scene info
        scenes: list[SceneInfo] = []
        subtitles_path = sd / "subtitles.json"
        if subtitles_path.exists():
            try:
                data = json.loads(subtitles_path.read_text(encoding="utf-8"))
                for s in data:
                    scene_num = s["scene"]
                    has_video = (sd / "videos" / f"scene{scene_num}.mp4").exists()
                    scenes.append(SceneInfo(scene=scene_num, name=s.get("name", ""), has_video=has_video))
            except Exception:
                pass

        return SessionDetail(
            id=row["id"],
            status=SessionStage(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            article_title=row["article_title"],
            article_excerpt=row["article_excerpt"],
            article=row["article"],
            requirements=row["requirements"],
            error=row["error"],
            progress=SessionProgress(
                stage=SessionStage(row["status"]),
                percent=row["step_percent"],
                message=row["step_message"] or "",
            ),
            scene_count=row["scene_count"],
            resume_count=row["resume_count"],
            video_duration_sec=row["video_duration_sec"],
            total_frames=row["total_frames"],
            claude_session_id=row["claude_session_id"],
            video_width=row["video_width"],
            video_height=row["video_height"],
            video_fps=row["video_fps"],
            has_video=(sd / "videos" / "full.mp4").exists(),
            has_subtitles=(sd / "subtitles.json").exists(),
            has_project_zip=(sd / "project.zip").exists(),
            scenes=scenes,
        )

    async def list_sessions(self) -> list[SessionSummary]:
        cursor = await self.db.execute(
            """SELECT id, status, created_at, updated_at, article_title,
                      article_excerpt, step_percent, step_message, scene_count
               FROM sessions ORDER BY updated_at DESC"""
        )
        rows = await cursor.fetchall()
        return [
            SessionSummary(
                id=r["id"],
                status=SessionStage(r["status"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                article_title=r["article_title"],
                article_excerpt=r["article_excerpt"],
                progress=SessionProgress(
                    stage=SessionStage(r["status"]),
                    percent=r["step_percent"],
                    message=r["step_message"] or "",
                ),
                scene_count=r["scene_count"],
            )
            for r in rows
        ]

    async def update_status(
        self,
        session_id: str,
        stage: SessionStage,
        *,
        percent: int = 0,
        message: str = "",
        error: str | None = None,
        **extra,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        sets = ["status=?", "step_percent=?", "step_message=?", "updated_at=?"]
        vals: list = [stage.value, percent, message, now]

        if error is not None:
            sets.append("error=?")
            vals.append(error)

        for k, v in extra.items():
            sets.append(f"{k}=?")
            vals.append(v)

        vals.append(session_id)
        await self.db.execute(
            f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", vals
        )
        await self.db.commit()

    async def save_subtitles(self, session_id: str, subtitles: list[dict]) -> None:
        sd = self.session_dir(session_id)
        (sd / "subtitles.json").write_text(
            json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await self.update_status(
            session_id,
            SessionStage((await self._get_row(session_id))["status"]),
            scene_count=len(subtitles),
        )

    async def load_subtitles(self, session_id: str) -> list[dict]:
        path = self.session_dir(session_id) / "subtitles.json"
        if not path.exists():
            raise FileNotFoundError("subtitles.json not found")
        return json.loads(path.read_text(encoding="utf-8"))

    async def save_audio_durations(self, session_id: str, durations: dict) -> None:
        path = self.session_dir(session_id) / "audio-durations.json"
        path.write_text(json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8")

    async def load_audio_durations(self, session_id: str) -> dict:
        path = self.session_dir(session_id) / "audio-durations.json"
        return json.loads(path.read_text(encoding="utf-8"))

    async def archive_project(self, session_id: str) -> None:
        sd = self.session_dir(session_id)
        remotion_dir = sd / "remotion"
        zip_path = sd / "project.zip"
        if not remotion_dir.exists():
            return

        def _zip():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in remotion_dir.rglob("*"):
                    if "node_modules" in f.parts or "__pycache__" in f.parts:
                        continue
                    if f.is_file():
                        zf.write(f, f.relative_to(remotion_dir))

        await asyncio.to_thread(_zip)

    async def restore_project(self, session_id: str) -> None:
        sd = self.session_dir(session_id)
        zip_path = sd / "project.zip"
        remotion_dir = sd / "remotion"
        if not zip_path.exists():
            raise FileNotFoundError(f"No project archive for session {session_id}")

        if remotion_dir.exists():
            shutil.rmtree(remotion_dir)
        remotion_dir.mkdir(parents=True)

        def _unzip():
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(remotion_dir)

        await asyncio.to_thread(_unzip)

    async def delete(self, session_id: str) -> None:
        await self.stop_task(session_id)
        sd = self.session_dir(session_id)
        if sd.exists():
            shutil.rmtree(sd)
        await self.db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        await self.db.commit()

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
            row = await self._get_row(session_id)
            if row["status"] not in (SessionStage.COMPLETED.value, SessionStage.ERROR.value):
                await self.update_status(
                    session_id, SessionStage.STOPPED, message="Stopped by user"
                )
        except Exception:
            pass

    def is_running(self, session_id: str) -> bool:
        task = self._running_tasks.get(session_id)
        return task is not None and not task.done()

    def get_video_path(self, session_id: str) -> Path | None:
        p = self.session_dir(session_id) / "videos" / "full.mp4"
        return p if p.exists() else None

    def get_scene_video_path(self, session_id: str, scene_num: int) -> Path | None:
        p = self.session_dir(session_id) / "videos" / f"scene{scene_num}.mp4"
        return p if p.exists() else None

    async def _get_row(self, session_id: str) -> aiosqlite.Row:
        cursor = await self.db.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise FileNotFoundError(f"Session {session_id} not found")
        return row
