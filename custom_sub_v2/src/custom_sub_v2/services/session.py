"""File-based session management with dual ID system (proj_ / agent_)."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles

from custom_sub_v2.api.models import (
    SessionListItem,
    SessionProgress,
    SessionStatus,
    StepName,
    StepProgress,
)
from custom_sub_v2.config import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_proj_id() -> str:
    return f"proj_{uuid.uuid4().hex[:10]}"


def _gen_agent_id() -> str:
    return f"agent_{uuid.uuid4().hex[:10]}"


def _session_dir(project_id: str) -> Path:
    return settings.sessions_path / project_id


def _status_file(project_id: str) -> Path:
    return _session_dir(project_id) / "status.json"


class SessionManager:
    """Manages session lifecycle on the local filesystem with dual ID system."""

    async def create_session(
        self,
        article: str,
        requirements: str = "",
        video_width: Optional[int] = None,
        video_height: Optional[int] = None,
        video_fps: Optional[int] = None,
    ) -> str:
        project_id = _gen_proj_id()
        agent_id = _gen_agent_id()
        sdir = _session_dir(project_id)
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "audio").mkdir(exist_ok=True)
        (sdir / "scenes").mkdir(exist_ok=True)
        (sdir / "videos").mkdir(exist_ok=True)
        (sdir / "logs").mkdir(exist_ok=True)
        (sdir / "project").mkdir(exist_ok=True)

        # Save article
        async with aiofiles.open(sdir / "article.txt", "w") as f:
            await f.write(article)

        # Save requirements
        if requirements:
            async with aiofiles.open(sdir / "requirements.txt", "w") as f:
                await f.write(requirements)

        # Initial status
        now = _now().isoformat()
        status_data = {
            "project_id": project_id,
            "agent_id": agent_id,
            "status": SessionStatus.PENDING.value,
            "created_at": now,
            "updated_at": now,
            "article_preview": article[:200],
            "error": None,
            "video_width": video_width or settings.video_width,
            "video_height": video_height or settings.video_height,
            "video_fps": video_fps or settings.video_fps,
            "steps": {
                step.value: {
                    "name": step.value,
                    "status": "pending",
                    "message": "",
                    "started_at": None,
                    "completed_at": None,
                }
                for step in StepName
            },
            "claude_session_id": None,
            "version": 1,
        }
        await self._write_status(project_id, status_data)
        return project_id

    async def get_progress(self, project_id: str) -> SessionProgress:
        data = await self._read_status(project_id)
        steps = [
            StepProgress(**data["steps"][step.value])
            for step in StepName
        ]
        return SessionProgress(
            project_id=data["project_id"],
            agent_id=data.get("agent_id", ""),
            status=SessionStatus(data["status"]),
            steps=steps,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            error=data.get("error"),
            article_preview=data.get("article_preview", ""),
        )

    async def list_sessions(self) -> list[SessionListItem]:
        sessions_path = settings.sessions_path
        items = []
        if not sessions_path.exists():
            return items
        for entry in sorted(sessions_path.iterdir(), reverse=True):
            if entry.is_dir() and (entry / "status.json").exists():
                try:
                    data = await self._read_status(entry.name)
                    items.append(SessionListItem(
                        project_id=data["project_id"],
                        agent_id=data.get("agent_id", ""),
                        status=SessionStatus(data["status"]),
                        created_at=datetime.fromisoformat(data["created_at"]),
                        updated_at=datetime.fromisoformat(data["updated_at"]),
                        article_preview=data.get("article_preview", ""),
                    ))
                except Exception:
                    pass
        return items

    async def update_status(
        self,
        project_id: str,
        status: Optional[SessionStatus] = None,
        error: Optional[str] = None,
        claude_session_id: Optional[str] = None,
    ) -> None:
        data = await self._read_status(project_id)
        if status is not None:
            data["status"] = status.value
        if error is not None:
            data["error"] = error
        if claude_session_id is not None:
            data["claude_session_id"] = claude_session_id
        data["updated_at"] = _now().isoformat()
        await self._write_status(project_id, data)

    async def update_step(
        self,
        project_id: str,
        step: StepName,
        step_status: str,
        message: str = "",
    ) -> None:
        data = await self._read_status(project_id)
        step_data = data["steps"][step.value]
        step_data["status"] = step_status
        step_data["message"] = message
        now = _now().isoformat()
        if step_status == "in_progress" and not step_data["started_at"]:
            step_data["started_at"] = now
        if step_status in ("completed", "failed"):
            step_data["completed_at"] = now
        data["updated_at"] = now
        await self._write_status(project_id, data)

    async def get_status_data(self, project_id: str) -> dict:
        return await self._read_status(project_id)

    async def set_agent_id(self, project_id: str, agent_id: str) -> None:
        data = await self._read_status(project_id)
        data["agent_id"] = agent_id
        await self._write_status(project_id, data)

    async def get_agent_id(self, project_id: str) -> Optional[str]:
        data = await self._read_status(project_id)
        return data.get("agent_id")

    async def set_claude_session_id(self, project_id: str, claude_sid: str) -> None:
        await self.update_status(project_id, claude_session_id=claude_sid)

    async def get_claude_session_id(self, project_id: str) -> Optional[str]:
        data = await self._read_status(project_id)
        return data.get("claude_session_id")

    async def delete_session(self, project_id: str) -> None:
        sdir = _session_dir(project_id)
        if sdir.exists():
            shutil.rmtree(sdir)

    async def stop_session(self, project_id: str) -> None:
        await self.update_status(project_id, status=SessionStatus.STOPPED)

    def session_dir(self, project_id: str) -> Path:
        return _session_dir(project_id)

    def session_exists(self, project_id: str) -> bool:
        return _status_file(project_id).exists()

    async def get_article(self, project_id: str) -> str:
        path = _session_dir(project_id) / "article.txt"
        async with aiofiles.open(path, "r") as f:
            return await f.read()

    async def get_requirements(self, project_id: str) -> str:
        path = _session_dir(project_id) / "requirements.txt"
        if not path.exists():
            return ""
        async with aiofiles.open(path, "r") as f:
            return await f.read()

    async def increment_version(self, project_id: str) -> int:
        data = await self._read_status(project_id)
        data["version"] = data.get("version", 1) + 1
        await self._write_status(project_id, data)
        return data["version"]

    # --- Internal ---

    async def _read_status(self, project_id: str) -> dict:
        path = _status_file(project_id)
        async with aiofiles.open(path, "r") as f:
            return json.loads(await f.read())

    async def _write_status(self, project_id: str, data: dict) -> None:
        path = _status_file(project_id)
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))


session_manager = SessionManager()
