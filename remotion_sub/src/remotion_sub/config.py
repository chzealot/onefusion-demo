"""Application configuration loaded from .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenRouter (for Claude Code SDK)
    openrouter_api_key: str = ""
    claude_code_model: str = "anthropic/claude-sonnet-4-20250514"

    # TTS - Alibaba Cloud DashScope CosyVoice
    dashscope_api_key: str = ""
    tts_voice: str = "zhishuo"
    tts_speed: int = 45
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
    workspaces_dir: Path = Path("./workspaces")
    db_path: Path = Path("./remotion_sub.db")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent

    @property
    def resources_dir(self) -> Path:
        return Path(__file__).resolve().parent / "resources"

    @property
    def prompts_dir(self) -> Path:
        return Path(__file__).resolve().parent / "prompts"

    @property
    def templates_dir(self) -> Path:
        return Path(__file__).resolve().parent / "templates"


settings = Settings()
