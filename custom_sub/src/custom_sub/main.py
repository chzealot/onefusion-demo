"""FastAPI application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from custom_sub.api.routes import router
from custom_sub.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(
    title="custom_sub",
    description="Article to explainer video tool",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)

# Serve Web UI
web_dir = Path(__file__).parent / "web" / "static"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="webui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
