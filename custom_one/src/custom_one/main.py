from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from custom_one.api import routes
from custom_one.config import settings
from custom_one.services.pipeline import Pipeline
from custom_one.services.session_manager import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sm = SessionManager()
    pl = Pipeline(sm)
    routes.session_manager = sm
    routes.pipeline = pl
    yield
    # Cleanup: stop all running tasks
    for sid in list(sm._running_tasks.keys()):
        await sm.stop_task(sid)


app = FastAPI(
    title="Custom One - Article to Video",
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
