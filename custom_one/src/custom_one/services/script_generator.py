from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx

from custom_one.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _load_system_prompt() -> str:
    path = TEMPLATES_DIR / "script_prompt.md"
    return path.read_text(encoding="utf-8")


async def generate_script(article: str, requirements: str) -> list[dict]:
    system_prompt = _load_system_prompt()

    user_content = f"## 文章内容\n\n{article}"
    if requirements:
        user_content += f"\n\n## 具体要求\n\n{requirements}"

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.7,
                "max_tokens": 8192,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]

    # Extract JSON from response (may be wrapped in markdown code block)
    json_match = re.search(r"```json\s*\n([\s\S]*?)\n```", content)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON array
        json_match = re.search(r"\[[\s\S]*\]", content)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise ValueError(f"Failed to extract JSON from LLM response:\n{content[:500]}")

    # Clean up: replace Chinese punctuation in JSON structure keys
    json_str = json_str.replace("，", ",").replace("：", ":")

    subtitles = json.loads(json_str)

    if not isinstance(subtitles, list):
        raise ValueError("Expected JSON array for subtitles")

    # Post-process: fix em dashes
    for scene in subtitles:
        for sub in scene.get("subtitles", []):
            sub["text"] = sub["text"].replace("——", "：")
        if "description" in scene:
            scene["description"] = scene["description"].replace("——", "：")

    logger.info("Generated %d scenes from article", len(subtitles))
    return subtitles
