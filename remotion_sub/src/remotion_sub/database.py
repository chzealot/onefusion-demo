"""SQLite database management with aiosqlite."""

from __future__ import annotations

import aiosqlite

from remotion_sub.config import settings

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'CREATED',
    article         TEXT NOT NULL,
    article_title   TEXT NOT NULL DEFAULT '',
    article_excerpt TEXT NOT NULL DEFAULT '',
    requirements    TEXT NOT NULL DEFAULT '',
    error           TEXT,

    video_width     INTEGER NOT NULL DEFAULT 1920,
    video_height    INTEGER NOT NULL DEFAULT 1080,
    video_fps       INTEGER NOT NULL DEFAULT 30,

    current_step    TEXT DEFAULT 'script',
    step_message    TEXT DEFAULT '',
    step_percent    INTEGER DEFAULT 0,

    scene_count     INTEGER DEFAULT 0,
    claude_session_id TEXT,
    resume_count    INTEGER DEFAULT 0,
    video_duration_sec REAL DEFAULT 0.0,
    total_frames    INTEGER DEFAULT 0,

    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


async def init_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(settings.db_path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute(_CREATE_TABLE)
    await db.commit()
    return db
