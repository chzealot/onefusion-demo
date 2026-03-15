"""Generate subtitles.json from article using LLM (Anthropic SDK + OpenRouter)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from anthropic import AsyncAnthropic

from ..config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位拥有10年以上经验的精英短视频内容编导，专门为知识频道创建引人入胜的短视频脚本。你擅长将复杂的长篇内容转化为易于消化的短视频脚本。

**核心原则：口播稿/解说词要极致精简，极致压缩。传递核心观点和关键论据即可。短视频才便于传播，也会有更好的完播率。**

## 你的核心专长

- **内容提炼**: 从冗长文档中提取最有价值的见解并极致压缩，只保留核心观点和关键论据
- **受众心理学**: 理解如何在前3秒钩住观众
- **口语化表达精通**: 将书面文字转换为自然、有说服力的口语
- **参与度架构**: 构建内容以实现最大留存率和转化率

## 视频结构设计

创建清晰的大纲，包含：
- **开头吸引点 (Opening Hook)**: 3-5秒的注意力抓取器，使用好奇心缺口、震惊事实、可共鸣的痛点或大胆陈述
- **核心论点 (Main Arguments)**: 2-4个关键点，每个都有支撑证据或案例
- **过渡衔接 (Transitions)**: 段落之间的流畅连接
- **结尾CTA (Closing Call-to-Action)**: 为观众提供清晰的下一步行动

## 脚本编写要求

- 使用对话式的第二人称语言("你"而非正式称谓)
- 保持句子简短(理想情况下每句15-25个字)
- 消除书面语习惯(不使用"此外"、"综上所述"等)
- 包含自然的停顿和强调标记
- 在整个过程中保持能量和动力
- 大声朗读时听起来真实自然

## 输出要求

你必须输出一个合法的 JSON 数组，格式如下。不要输出任何其他内容，只输出 JSON。

**JSON 结构**:
```json
[
    {
        "scene": 1,
        "name": "镜头一：开头吸引点",
        "annotation": "[标注语气：疑问 → 反转 → 揭秘]",
        "description": "画面描述，务必完整，后续将基于description生成分镜的画面",
        "subtitles": [
            {
                "file": "scene1-seg1.mp3",
                "text": "字幕文本，也是TTS文本",
                "rate": "+40%",
                "pitch": "+0Hz"
            }
        ]
    }
]
```

**规范**:
- 每个场景(scene)的 subtitles 数组长度不超过4个
- 可以通过增加镜头数量来丰富内容表达
- 每条 text 不超过25个汉字
- 每一行 text 必须是完整的语义单元，不要把一句完整的话拆分成多行
- description 必须与 subtitles 中的文本保持一致性
- rate 默认为"+40%"（快节奏），pitch 默认为"+0Hz"
- 文件命名格式：scene{场景编号}-seg{片段编号}.mp3

**TTS 文本规范**:
1. 中文和英文之间有半角空格
2. 中文和数字之间有半角空格
3. 双引号、逗号等标点符号统一采用全角字符
4. 如果字幕文本中有双引号，则去掉
5. 如果文本中有"——"，务必改成"："

**质量标准**:
- 每个句子都能自然说出来，不拗口
- 开头5秒内必须有明确钩子
- 信息密度适中，不贪多求全
- 保持原文核心观点的准确性

**绝对避免**:
- 书面语词汇（如：鉴于、综上所述、本文）
- 长难句（超过30个字的句子需拆分）
- 模糊的CTA（如：希望对你有帮助）
- 缺乏节奏感的平铺直叙
- JSON 文件中使用半角标点（逗号、句号等必须用全角）
- 将一句完整的话拆分成多行字幕
"""


async def generate_subtitles(
    article: str,
    requirements: str,
    output_path: Path,
) -> Path:
    """Generate subtitles.json from article content.

    Args:
        article: The article text to convert.
        requirements: Additional user requirements.
        output_path: Path to write subtitles.json.

    Returns:
        Path to the generated subtitles.json file.
    """
    client = AsyncAnthropic(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )

    user_prompt = f"请将以下文章转换为短视频脚本，直接输出 JSON 数组，不要输出其他内容。\n\n"
    if requirements:
        user_prompt += f"**具体要求**：{requirements}\n\n"
    user_prompt += f"**文章内容**：\n{article}"

    logger.info("Calling LLM to generate subtitles script...")
    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first and last lines (```json and ```)
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip() == "```" and in_block:
                break
            if in_block:
                json_lines.append(line)
        raw_text = "\n".join(json_lines)

    # Validate JSON
    subtitles = json.loads(raw_text)
    if not isinstance(subtitles, list):
        raise ValueError("LLM output is not a JSON array")

    # Post-process: replace "——" with "："
    for scene in subtitles:
        for sub in scene.get("subtitles", []):
            sub["text"] = sub["text"].replace("——", "：")
            # Remove double quotes from text
            sub["text"] = sub["text"].replace('"', "").replace('"', "").replace('"', "")

    output_path.write_text(json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Subtitles written to {output_path}")
    return output_path
