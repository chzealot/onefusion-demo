"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .api.routes import router
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="RemotionOne",
    description="Article to explainer video tool",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve Web UI
web_dir = Path(__file__).parent.parent.parent / "web"


@app.get("/")
async def serve_ui():
    return FileResponse(web_dir / "index.html")


@app.on_event("startup")
async def startup():
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    if not settings.openrouter_api_key:
        logging.getLogger(__name__).warning("OPENROUTER_API_KEY not set - pipeline will fail until configured")


def run():
    import uvicorn
    uvicorn.run(
        "remotion_one.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
