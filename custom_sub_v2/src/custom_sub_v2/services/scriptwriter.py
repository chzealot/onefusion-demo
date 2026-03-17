"""Scriptwriter service: article -> subtitles.json via direct OpenRouter API call."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from custom_sub_v2.config import settings
from custom_sub_v2.services.logger import get_project_logger

# System prompt for scriptwriting
SCRIPTWRITER_SYSTEM_PROMPT = """你是一位拥有10年以上经验的精英短视频内容编导，专门为知识频道创建引人入胜的讲解视频脚本。

**核心原则：口播稿/解说词要极致精简，极致压缩。传递核心观点和关键论据即可。短视频才便于传播。**

## 你的任务

将用户提供的文章转换为短视频字幕脚本（subtitles.json），需要：
1. 提取核心信息和关键要点（3-5个主要观点）
2. 使用对话式第二人称语言
3. 保持句子简短（每句15-25个字）
4. 消除书面语习惯

## 视频结构

1. **开头吸引点**: 3-5秒的注意力抓取器
2. **核心论点**: 2-4个关键点，每个有支撑证据
3. **结尾CTA**: 互动引导话术

## 输出要求

直接输出 JSON 数组，不要包含任何 markdown 代码块标记或其他文字，结构如下：
[
    {
        "scene": 1,
        "name": "镜头一：开头吸引点",
        "annotation": "[标注语气：疑问→反转]",
        "description": "画面描述，务必完整",
        "subtitles": [
            {
                "file": "scene1-seg1.mp3",
                "text": "字幕文本",
                "rate": "+40%",
                "pitch": "+0Hz"
            }
        ]
    }
]

## 规范

- 每个 scene 的 subtitles 数组长度不超过 4 个
- 可以通过增加镜头数量来丰富内容
- 中文和英文之间有半角空格
- 中文和数字之间有半角空格
- 标点符号统一采用全角字符
- 每行字幕必须是完整的语义单元
- text 既是字幕也是 TTS 文本，每条不超过 25 个汉字
- description 必须与 subtitles 文本保持一致性
- rate 默认 "+40%"，pitch 默认 "+0Hz"
- 文件命名：scene{场景编号}-seg{片段编号}.mp3
- 如果有 "——"，务必改成 "："

## 禁止
- 书面语词汇（鉴于、综上所述、本文）
- 长难句（超过25字必须拆分）
- 模糊的CTA
- 将完整句子拆成多行字幕
- **text 字段中绝对不能出现双引号（" 或 \u201c\u201d）**，如需引用请用书名号《》或直接去掉引号
- JSON 结构字符（大括号、方括号、逗号、冒号）必须使用半角ASCII字符
- JSON 字符串值内的中文标点使用全角
"""


async def generate_script(
    session_dir: Path,
    article: str,
    requirements: str = "",
    project_id: str = "",
) -> list[dict]:
    """Generate subtitles.json from article text via OpenRouter API.

    Returns the parsed JSON data.
    """
    log = get_project_logger(project_id) if project_id else None

    # Build user prompt
    prompt_parts = ["请将以下文章转换为短视频字幕脚本。直接输出 JSON 数组。"]
    if requirements:
        prompt_parts.append(f"\n用户的具体要求：\n{requirements}")
    prompt_parts.append(f"\n文章内容：\n{article}")
    user_prompt = "\n".join(prompt_parts)

    if log:
        log.info("Calling OpenRouter scriptwriter API...")

    # Call OpenRouter API directly
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openrouter_scriptwriter_model,
                "messages": [
                    {"role": "system", "content": SCRIPTWRITER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 8192,
            },
        )
        resp.raise_for_status()
        result = resp.json()

    # Extract content from response
    content = result["choices"][0]["message"]["content"]
    if log:
        log.info("OpenRouter response received (%d chars)", len(content))

    # Strip markdown code block if present
    content = content.strip()
    if content.startswith("```"):
        # Remove opening ```json or ```
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
        content = content.strip()

    # Repair and parse JSON
    content = _repair_json(content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        if log:
            log.error("JSON parse failed at line %d col %d: %s", e.lineno, e.colno, e.msg)
        raise RuntimeError(f"subtitles.json has invalid JSON: {e}") from e

    # Validate basic structure
    if not isinstance(data, list) or len(data) == 0:
        raise RuntimeError("subtitles.json is empty or not a list")

    # Write subtitles.json
    subtitles_path = session_dir / "subtitles.json"
    subtitles_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if log:
        log.info("Generated %d scenes in subtitles.json", len(data))
    return data


def _repair_json(raw: str) -> str:
    """Repair common JSON issues produced by LLMs."""
    raw = raw.strip().lstrip("\ufeff")

    lines = raw.split('\n')
    repaired_lines = []

    for line in lines:
        # Match pattern: <whitespace>"key": "value"<optional comma>
        m = re.match(r'^(\s*"[^"]+"\s*:\s*)"(.*)(",?\s*)$', line)
        if m:
            prefix = m.group(1)
            value = m.group(2)
            suffix = m.group(3)

            # Remove any unescaped double quotes within the value
            value = value.replace('"', '')
            for q in '\u201c\u201d\u201e\u201f':
                value = value.replace(q, '')

            line = f'{prefix}"{value}{suffix}'

        # Fix fullwidth structural chars outside of string context
        if not re.match(r'^\s*"', line.strip()) and not line.strip().startswith('"'):
            line = line.replace('\uff0c', ',').replace('\uff1a', ':')

        repaired_lines.append(line)

    return '\n'.join(repaired_lines)
