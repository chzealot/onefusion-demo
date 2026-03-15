"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from remotion_sub.api import routes
from remotion_sub.database import init_db
from remotion_sub.services.pipeline import Pipeline
from remotion_sub.services.session import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db()
    sm = SessionManager(db)
    pl = Pipeline(sm)
    routes.session_manager = sm
    routes.pipeline = pl
    yield
    # Cleanup: stop all running tasks
    for sid in list(sm._running_tasks.keys()):
        await sm.stop_task(sid)
    await db.close()


app = FastAPI(
    title="Remotion Sub - Article to Video",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)

# Serve Web UI
static_dir = Path(__file__).parent / "static" / "webui"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="webui")
