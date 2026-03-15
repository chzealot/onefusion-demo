"""Remotion project generator: uses Claude Agent SDK to create Remotion code."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk.types import AssistantMessage, ResultMessage

from remotion_sub.config import settings

logger = logging.getLogger(__name__)


def _get_sdk_env() -> dict[str, str]:
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = settings.openrouter_api_key
    env["ANTHROPIC_BASE_URL"] = "https://openrouter.ai/api/v1"
    return env


def _build_prompt(subtitles: list[dict], durations: dict, video_config: dict) -> str:
    """Build the Remotion project generation prompt."""
    width = video_config.get("width", 1920)
    height = video_config.get("height", 1080)
    fps = video_config.get("fps", 30)

    return f"""请创建一个 Remotion 视频项目，基于以下字幕脚本和音频时长数据。

## 视频规格
- 分辨率：{width}x{height}
- 帧率：{fps} fps

## 关键要求

1. **每个 scene 必须是一个独立的 Composition**：
   - 在 Root.tsx 中为每个 scene 注册独立的 `<Composition>` 组件，ID 格式为 `scene-{{N}}`
   - 另外注册一个 `full-video` Composition，将所有 scene 按顺序组合

2. **每个 scene 有独立的组件文件**：如 Scene01.tsx, Scene02.tsx 等，放在 src/compositions/ 目录

3. **音频集成**：
   - 音频文件已存在于 public/audio/ 目录
   - 使用 Remotion 的 `<Audio>` 组件和 `staticFile()` 引用音频
   - 每条字幕对应一个音频文件，需在对应时间段播放

4. **字幕显示**：
   - 在画面底部 15% 区域显示字幕
   - 字幕与音频严格同步
   - 字体大小：{int(48 * height / 1080)}px

5. **画面布局**：
   - 顶部 15%：标题区域
   - 中间 70%：核心内容/动画区域
   - 底部 15%：字幕区域

6. **时序计算**：
   - 基于 audio-durations.json 中的实际音频时长精确计算帧数
   - scene 之间有 0.5s 缓冲（{int(0.5 * fps)} 帧）
   - segment 之间有 0.3s 间隔（{int(0.3 * fps)} 帧）

7. **动画质量**：
   - 每个 Scene 必须包含丰富的视觉元素和动画效果
   - 使用 Remotion 的 interpolate()、spring() 等 API
   - 根据 description 定制化设计每个场景的视觉方案
   - 禁止使用 GenericScene 等通用组件

8. **项目结构**：
   ```
   src/
   ├── index.ts          # registerRoot
   ├── Root.tsx           # 所有 Composition 注册
   ├── types.ts           # TypeScript 类型
   ├── compositions/
   │   ├── Scene01.tsx
   │   ├── Scene02.tsx
   │   └── ...
   ├── components/
   │   └── Subtitle.tsx   # 共享字幕组件
   └── lib/
       └── timing.ts      # 时序计算工具
   ```

## 字幕脚本数据 (subtitles.json)
```json
{json.dumps(subtitles, ensure_ascii=False, indent=2)}
```

## 音频时长数据 (audio-durations.json)
```json
{json.dumps(durations, ensure_ascii=False, indent=2)}
```

请直接在当前目录创建完整的 Remotion 项目。public/audio/ 目录下的音频文件已经准备好，不需要重新生成。
先执行 npm install 安装依赖，确保项目可以正常构建。

注意：
- 使用 remotion 4.x 版本
- 使用 TypeScript
- 确保 package.json 中包含所有必要依赖
- 不要使用占位符或 TODO，所有代码必须完整实现
"""


async def generate_remotion(
    session_dir: Path,
    subtitles: list[dict],
    durations: dict,
    video_config: dict,
    on_progress=None,
) -> str | None:
    """Generate the Remotion project using Claude Agent SDK. Returns claude session_id."""
    remotion_dir = session_dir / "remotion"
    remotion_dir.mkdir(parents=True, exist_ok=True)

    # Copy audio files to remotion project's public/audio
    public_audio = remotion_dir / "public" / "audio"
    public_audio.mkdir(parents=True, exist_ok=True)
    audio_src = session_dir / "audio"
    for mp3 in audio_src.glob("*.mp3"):
        if mp3.name != "combined.mp3" and not mp3.name.startswith("silence_"):
            shutil.copy2(mp3, public_audio / mp3.name)

    # Copy subtitles.json and durations
    (remotion_dir / "public" / "subtitles.json").write_text(
        json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (remotion_dir / "public" / "audio-durations.json").write_text(
        json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Copy remotion-best-practices skill into the workspace
    _copy_skill_files(remotion_dir)

    prompt = _build_prompt(subtitles, durations, video_config)

    options = ClaudeCodeOptions(
        cwd=str(remotion_dir),
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

    logger.info("Remotion project generation complete for %s", session_dir.name)
    return claude_session_id


async def resume_remotion(
    session_dir: Path,
    resume_prompt: str,
    claude_session_id: str | None = None,
    on_progress=None,
) -> str | None:
    """Resume/modify an existing Remotion project."""
    remotion_dir = session_dir / "remotion"

    options = ClaudeCodeOptions(
        cwd=str(remotion_dir),
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


async def fix_remotion_errors(
    session_dir: Path,
    error_message: str,
    claude_session_id: str | None = None,
    on_progress=None,
) -> str | None:
    """Use Claude Code SDK to fix Remotion project errors."""
    fix_prompt = f"""The Remotion project has an error during rendering. Please fix it.

Error message:
```
{error_message}
```

Please investigate the error, fix the code, and ensure the project builds and renders correctly.
Run `npx remotion render src/index.ts full-video --frames=0-1` to verify the fix works.
"""
    return await resume_remotion(
        session_dir, fix_prompt, claude_session_id, on_progress
    )


def _copy_skill_files(remotion_dir: Path) -> None:
    """Copy remotion-best-practices skill files into the workspace."""
    skill_src = settings.resources_dir / "remotion-best-practices"
    if not skill_src.exists():
        logger.warning("remotion-best-practices skill not found at %s", skill_src)
        return

    # Place as .claude/skills/ in the remotion project so Claude agent can find it
    skill_dst = remotion_dir / ".claude" / "skills" / "remotion-best-practices"
    if skill_dst.exists():
        shutil.rmtree(skill_dst)
    shutil.copytree(skill_src, skill_dst)
    logger.info("Copied remotion-best-practices skill to %s", skill_dst)
