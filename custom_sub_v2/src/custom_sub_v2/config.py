"""Application configuration loaded from .env file."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4-20250514"
    openrouter_scriptwriter_model: str = "anthropic/claude-sonnet-4-20250514"

    # DashScope TTS
    dashscope_api_key: str = ""
    tts_voice: str = "zhishuo"
    tts_rate: int = 45
    tts_pitch: int = 25
    tts_volume: int = 60
    tts_sample_rate: int = 16000
    tts_format: str = "mp3"

    # Video defaults
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Paths
    sessions_dir: Path = Path("sessions")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def project_root(self) -> Path:
        """Project root directory (where pyproject.toml is)."""
        return Path(__file__).parent.parent.parent

    @property
    def templates_dir(self) -> Path:
        return Path(__file__).parent / "templates"

    @property
    def sessions_path(self) -> Path:
        path = self.project_root / self.sessions_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
