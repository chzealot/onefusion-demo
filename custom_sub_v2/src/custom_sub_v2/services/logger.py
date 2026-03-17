"""Per-project logging manager with real-time streaming support."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from custom_sub_v2.config import settings


class ProjectLogger:
    """Manages per-project log files and provides real-time log streaming."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._log_dir = settings.sessions_path / project_id / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "pipeline.log"

        # Create a dedicated Python logger
        self._logger = logging.getLogger(f"project.{project_id}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # File handler
        if not self._logger.handlers:
            fh = logging.FileHandler(str(self._log_file), encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            self._logger.addHandler(fh)

            # Also log to root logger for console output
            sh = logging.StreamHandler()
            sh.setLevel(logging.INFO)
            sh.setFormatter(logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            ))
            self._logger.addHandler(sh)

    @property
    def log_file(self) -> Path:
        return self._log_file

    def info(self, msg: str, *args) -> None:
        self._logger.info(msg, *args)

    def debug(self, msg: str, *args) -> None:
        self._logger.debug(msg, *args)

    def warning(self, msg: str, *args) -> None:
        self._logger.warning(msg, *args)

    def error(self, msg: str, *args) -> None:
        self._logger.error(msg, *args)

    def exception(self, msg: str, *args) -> None:
        self._logger.exception(msg, *args)

    async def read_all(self) -> str:
        """Read entire log file content."""
        if not self._log_file.exists():
            return ""
        async with aiofiles.open(self._log_file, "r") as f:
            return await f.read()

    async def tail(self, lines: int = 50) -> list[str]:
        """Read last N lines from log file."""
        if not self._log_file.exists():
            return []
        async with aiofiles.open(self._log_file, "r") as f:
            content = await f.read()
        all_lines = content.strip().split("\n")
        return all_lines[-lines:]

    async def stream(self) -> AsyncIterator[str]:
        """Stream log lines in real-time (for SSE/WebSocket)."""
        if not self._log_file.exists():
            # Wait for log file to be created
            for _ in range(30):
                await asyncio.sleep(1)
                if self._log_file.exists():
                    break
            else:
                return

        async with aiofiles.open(self._log_file, "r") as f:
            # Read existing content first
            content = await f.read()
            if content:
                for line in content.strip().split("\n"):
                    yield line

            # Then follow new lines
            while True:
                line = await f.readline()
                if line:
                    yield line.rstrip("\n")
                else:
                    await asyncio.sleep(0.3)


# Cache loggers per project
_loggers: dict[str, ProjectLogger] = {}


def get_project_logger(project_id: str) -> ProjectLogger:
    """Get or create a ProjectLogger for a given project."""
    if project_id not in _loggers:
        _loggers[project_id] = ProjectLogger(project_id)
    return _loggers[project_id]
