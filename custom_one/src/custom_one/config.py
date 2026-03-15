from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM - Script Generation (OpenRouter)
    openrouter_api_key: str = ""
    llm_model: str = "anthropic/claude-opus-4.6"

    # LLM - Animation Generation (Claude Code SDK via OpenRouter)
    claude_code_api_key: str = ""
    claude_code_base_url: str = "https://openrouter.ai/api"
    claude_code_model: str = "claude-opus-4-20250514"

    # TTS - Alibaba Cloud DashScope
    dashscope_api_key: str = ""
    tts_voice: str = "longshuo"
    tts_speed: int = 45
    tts_pitch: int = 25
    tts_volume: int = 60
    tts_sample_rate: int = 16000
    tts_format: str = "mp3"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workspaces_dir: Path = Path("./workspaces")

    # Video
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
