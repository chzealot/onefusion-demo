from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk.types import AssistantMessage, ResultMessage

from custom_one.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _build_prompt(subtitles: list[dict], durations: dict) -> str:
    """Build the animation generation prompt."""
    template = (TEMPLATES_DIR / "animation_prompt.md").read_text(encoding="utf-8")
    return template.replace(
        "{{SUBTITLES_JSON}}", json.dumps(subtitles, ensure_ascii=False, indent=2)
    ).replace(
        "{{AUDIO_DURATIONS_JSON}}", json.dumps(durations, ensure_ascii=False, indent=2)
    )


def _get_sdk_env() -> dict[str, str]:
    """Build environment variables for Claude Code SDK via OpenRouter."""
    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = settings.claude_code_base_url or "https://openrouter.ai/api"
    env["ANTHROPIC_AUTH_TOKEN"] = settings.claude_code_api_key
    env["ANTHROPIC_API_KEY"] = ""  # Must be explicitly empty for OpenRouter
    return env


async def generate_animation(
    session_dir: Path,
    subtitles: list[dict],
    durations: dict,
    on_progress=None,
) -> str | None:
    """Generate the React+Vite animation project. Returns claude session_id."""
    animation_dir = session_dir / "animation"
    animation_dir.mkdir(parents=True, exist_ok=True)

    # Copy audio files to animation project's public/audio
    public_audio = animation_dir / "public" / "audio"
    public_audio.mkdir(parents=True, exist_ok=True)
    audio_src = session_dir / "audio"
    for mp3 in audio_src.glob("*.mp3"):
        if mp3.name != "combined.mp3" and not mp3.name.startswith("silence_"):
            shutil.copy2(mp3, public_audio / mp3.name)

    # Copy subtitles.json and durations to animation dir
    (animation_dir / "public" / "subtitles.json").write_text(
        json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (animation_dir / "public" / "audio-durations.json").write_text(
        json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    prompt = _build_prompt(subtitles, durations)

    options = ClaudeCodeOptions(
        cwd=str(animation_dir),
        model=settings.claude_code_model or None,
        permission_mode="bypassPermissions",
        allowed_tools=["Write", "Edit", "Bash", "Glob", "Grep", "Read"],
        max_turns=80,
        env=_get_sdk_env(),
    )

    claude_session_id = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            claude_session_id = message.session_id
        elif isinstance(message, AssistantMessage) and on_progress:
            text = ""
            for block in (message.content if isinstance(message.content, list) else []):
                if hasattr(block, "text"):
                    text = block.text
                    break
            if text.strip():
                await on_progress(text[:200])

    logger.info("Animation generation complete for %s", session_dir.name)
    return claude_session_id


async def resume_animation(
    session_dir: Path,
    resume_prompt: str,
    claude_session_id: str | None = None,
    on_progress=None,
) -> str | None:
    """Resume/modify an existing animation project."""
    animation_dir = session_dir / "animation"

    options = ClaudeCodeOptions(
        cwd=str(animation_dir),
        model=settings.claude_code_model or None,
        permission_mode="bypassPermissions",
        allowed_tools=["Write", "Edit", "Bash", "Glob", "Grep", "Read"],
        max_turns=50,
        env=_get_sdk_env(),
    )

    if claude_session_id:
        options.resume = claude_session_id

    new_session_id = None

    async for message in query(prompt=resume_prompt, options=options):
        if isinstance(message, ResultMessage):
            new_session_id = message.session_id
        elif isinstance(message, AssistantMessage) and on_progress:
            text = ""
            for block in (message.content if isinstance(message.content, list) else []):
                if hasattr(block, "text"):
                    text = block.text
                    break
            if text.strip():
                await on_progress(text[:200])

    return new_session_id or claude_session_id


async def fix_animation_errors(
    session_dir: Path,
    error_message: str,
    claude_session_id: str | None = None,
    on_progress=None,
) -> str | None:
    """Use Claude Code SDK to fix animation project errors."""
    fix_prompt = f"""The animation project has an error during rendering. Please fix it.

Error message:
```
{error_message}
```

Please investigate the error, fix the code, and ensure the project builds and renders correctly.
Make sure window.__FRAME_READY__ is set to true after each frame renders.
"""
    return await resume_animation(
        session_dir, fix_prompt, claude_session_id, on_progress
    )
