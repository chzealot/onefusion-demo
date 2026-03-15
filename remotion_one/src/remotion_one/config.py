"""Configuration management via .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # OpenRouter
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    claude_model: str = os.getenv("CLAUDE_MODEL", "anthropic/claude-sonnet-4")

    # Video
    video_width: int = int(os.getenv("VIDEO_WIDTH", "1920"))
    video_height: int = int(os.getenv("VIDEO_HEIGHT", "1080"))
    video_fps: int = int(os.getenv("VIDEO_FPS", "30"))

    # TTS
    tts_voice: str = os.getenv("TTS_VOICE", "yunxi")

    # Workspace
    workspace_dir: Path = Path(os.getenv("WORKSPACE_DIR", "./workspaces")).resolve()

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Resources
    resources_dir: Path = Path(__file__).parent / "resources"

    def validate(self) -> None:
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required in .env")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
