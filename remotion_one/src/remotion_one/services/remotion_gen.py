"""Generate Remotion project code using Claude Code SDK."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import claude_code_sdk

from ..config import settings

logger = logging.getLogger(__name__)


def _build_system_prompt(video_width: int, video_height: int, video_fps: int) -> str:
    """Build system prompt for Remotion code generation."""

    # Load remotion-best-practices SKILL.md
    skill_dir = settings.resources_dir / "remotion-best-practices"
    skill_content = ""
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        skill_content = skill_md.read_text(encoding="utf-8")

    # Load key rule files
    rules_dir = skill_dir / "rules"
    key_rules = [
        "animations.md", "audio.md", "compositions.md", "fonts.md",
        "sequencing.md", "timing.md", "transitions.md",
    ]
    rules_content = ""
    if rules_dir.exists():
        for rule_file in key_rules:
            rule_path = rules_dir / rule_file
            if rule_path.exists():
                rules_content += f"\n\n### {rule_file}\n{rule_path.read_text(encoding='utf-8')}"

    orientation = "横版" if video_width > video_height else "竖版"

    return f"""你是一位精英级 Remotion 视频动画专家。你的任务是基于 subtitles.json 创建一个完整的 Remotion 项目，生成可渲染的动画视频。

## 视频规格
- 分辨率：{video_width}x{video_height} ({orientation})
- 帧率：{video_fps} FPS

## 核心要求

1. **读取项目根目录的 subtitles.json**，基于其中每个 scene 的 description 设计画面
2. **每个 Scene 必须有独立的组件文件**（Scene01.tsx, Scene02.tsx, ...）
3. **严格禁止创建 GenericScene 通用组件**
4. **配音文件已在 public/audio/ 目录**，使用 staticFile() 引用
5. **字幕与配音必须同步**：先用 ffprobe 获取每个音频文件时长，然后计算帧数
6. **所有静态资源必须使用 staticFile() API 引用**

## 画面框架布局

- **顶部 15%**：标题展示区域（仅标题文字，无背景色）
- **中间 70%**：核心动画内容区域，每个 Scene 至少5个视觉元素，70%为图，30%为文字
- **底部 15%**：字幕展示区域（仅字幕文字，无背景色）
- Scene 背景铺满整个画面 100%，UI 组件限制在中间 70% 区域

## 动画标准

- 每个 Scene 至少3个动画效果
- 使用 spring、interpolate 等 Remotion 动画 API
- 所有 interpolate 必须同时设置 extrapolateLeft: 'clamp' 和 extrapolateRight: 'clamp'
- Sequence 内部 useCurrentFrame() 返回相对帧数（从0开始），不要再减去 startFrame
- 每个 Scene 在 frame=0 时必须有至少1个元素 opacity 为1（避免首帧空白）

## 字幕规范

- 字幕字体大小：fontSize: {int(48 * video_height / 1080)}
- 每一帧画面最多2行字幕
- 字幕区域无背景色，文字可有描边/阴影增强可读性

## 中文排版规范

- 中文与英文、数字之间必须添加半角空格
- 中文标点使用全角

## 工作流程

1. 读取 subtitles.json
2. 用 ffprobe 获取 public/audio/ 下所有音频文件的时长
3. 创建 Remotion 项目结构（如果不存在）
4. 为每个 Scene 创建独立的组件文件
5. 创建主视频组合组件，精确计算时间轴
6. 安装依赖（npm install）
7. 确保项目可以成功构建

## Remotion Best Practices

{skill_content}

{rules_content}
"""


def _copy_best_practices(workspace_dir: Path) -> None:
    """Copy remotion-best-practices to the workspace .claude/skills/ directory."""
    src = settings.resources_dir / "remotion-best-practices"
    if not src.exists():
        return
    dest = workspace_dir / ".claude" / "skills" / "remotion-best-practices"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    logger.info(f"Copied remotion-best-practices to {dest}")


async def generate_remotion_project(
    workspace_dir: Path,
    video_width: int,
    video_height: int,
    video_fps: int,
    resume_session_id: str | None = None,
    extra_prompt: str | None = None,
) -> str:
    """Generate Remotion project code using Claude Code SDK.

    Args:
        workspace_dir: Working directory for the project.
        video_width: Video width.
        video_height: Video height.
        video_fps: Video FPS.
        resume_session_id: Claude session ID to resume (for modifications).
        extra_prompt: Additional prompt for modifications.

    Returns:
        Claude session ID for future resume.
    """
    _copy_best_practices(workspace_dir)

    system_prompt = _build_system_prompt(video_width, video_height, video_fps)

    if extra_prompt:
        prompt = extra_prompt
    else:
        subtitles_path = workspace_dir / "subtitles.json"
        subtitles_content = subtitles_path.read_text(encoding="utf-8")
        prompt = (
            f"请基于以下 subtitles.json 创建完整的 Remotion 视频项目。\n"
            f"项目目录就是当前工作目录。\n"
            f"audio 文件已经生成在 public/audio/ 目录下。\n"
            f"请先用 ffprobe 获取所有音频文件时长，然后创建项目。\n\n"
            f"subtitles.json 内容：\n```json\n{subtitles_content}\n```"
        )

    options = claude_code_sdk.ClaudeCodeOptions(
        system_prompt=system_prompt,
        allowed_tools=[
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ],
        permission_mode="bypassPermissions",
        model=settings.claude_model,
        cwd=str(workspace_dir),
        max_turns=50,
        env={
            "ANTHROPIC_API_KEY": settings.openrouter_api_key,
            "ANTHROPIC_BASE_URL": settings.openrouter_base_url,
        },
    )

    if resume_session_id:
        options.resume = resume_session_id

    claude_session_id = ""
    async for message in claude_code_sdk.query(prompt=prompt, options=options):
        if isinstance(message, claude_code_sdk.ResultMessage):
            claude_session_id = message.session_id
            if message.is_error:
                raise RuntimeError(f"Claude Code SDK error: {message.result}")
            logger.info(f"Remotion project generated. Session: {claude_session_id}")
        elif isinstance(message, claude_code_sdk.AssistantMessage):
            for block in message.content:
                if isinstance(block, claude_code_sdk.TextBlock):
                    logger.debug(f"Claude: {block.text[:200]}")

    return claude_session_id


async def fix_render_error(
    workspace_dir: Path,
    error_output: str,
    claude_session_id: str,
    video_width: int,
    video_height: int,
    video_fps: int,
) -> str:
    """Use Claude Code SDK to fix rendering errors.

    Returns:
        Updated Claude session ID.
    """
    prompt = (
        f"Remotion 渲染失败，请修复错误后确保项目可以成功渲染。\n\n"
        f"错误输出：\n```\n{error_output[-3000:]}\n```"
    )

    return await generate_remotion_project(
        workspace_dir=workspace_dir,
        video_width=video_width,
        video_height=video_height,
        video_fps=video_fps,
        resume_session_id=claude_session_id,
        extra_prompt=prompt,
    )
