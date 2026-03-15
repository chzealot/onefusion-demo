"""Animator service: Uses Claude Agent SDK to generate React animation code for each scene."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, query

from custom_sub.config import settings

logger = logging.getLogger(__name__)

ANIMATOR_SYSTEM_PROMPT = """你是一位精英级前端动画专家，擅长使用 React 和 TypeScript 创建专业的视频动画场景。

## 你的任务

你将收到一个视频场景的描述信息，需要修改当前 React+Vite 项目中的 `src/SceneContent.tsx` 文件，
创建精美的动画效果来可视化场景内容。

## 技术栈

- React 18 + TypeScript + Vite
- 基于帧号的动画系统（不要使用 CSS transition/animation 或 setTimeout）
- 项目已提供以下工具函数：
  - `useCurrentFrame()`: 获取当前帧号
  - `interpolate(frame, inputRange, outputRange, options?)`: 线性插值
  - `spring(frame, config?)`: 弹簧动画
  - `Easing`: 缓动函数集合（easeIn, easeOut, easeInOut, bounce 等）

## 动画要求

1. **所有动画必须基于帧号**，使用 `interpolate()` 和 `spring()` 函数
2. **禁止使用**: CSS transition, CSS animation, setTimeout, setInterval, requestAnimationFrame, GSAP
3. 原因：视频渲染是逐帧截图的，时间相关的动画无法正确渲染

## 视觉要求

1. 每个场景至少包含 5 个视觉元素（图形、图标、文字等）
2. 至少 3 个不同的动画效果（淡入、位移、缩放、旋转等）
3. 背景应该有渐变或动态效果
4. 使用 SVG 或 CSS 绘制图形元素（不依赖外部图片）
5. 配色专业，使用科技感/现代感的色彩方案
6. 文字大小适配视频分辨率（默认 1080p，标题至少 48px，正文至少 24px）
7. 70% 以上的视觉元素是图形/图标，文字不超过 30%

## 文件修改规范

- 只修改 `src/SceneContent.tsx` 文件
- 可以在 `src/components/` 下创建新的子组件文件
- 导入路径使用相对路径
- 不要修改 `src/App.tsx`、`src/hooks/`、`src/utils/` 下的文件
- 不要安装新的 npm 包

## SceneContent 组件接口

```tsx
interface Props {
  config: SceneConfig  // 包含 scene, name, description, subtitles, total_frames 等
}

export function SceneContent({ config }: Props) {
  const frame = useCurrentFrame()
  // 你的动画代码...
}
```

## 质量标准

- 代码必须完整，没有 TODO 或占位符
- 视觉效果丰富且与场景描述匹配
- 动画流畅，时序合理
- 所有文字使用中文排版规范（中英文间加空格，全角标点）
"""


async def generate_animations(
    session_dir: Path,
    scenes: list[dict],
    resume_session_id: str | None = None,
) -> None:
    """Generate React animation code for each scene using Claude Agent SDK.

    For each scene:
    1. Copy the base template to sessions/{id}/scenes/sceneN/
    2. Inject scene config
    3. Call Claude Agent SDK to generate SceneContent.tsx
    4. Install npm dependencies
    """
    scenes_dir = session_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    template_dir = settings.templates_dir / "scene_base"

    for scene_data in scenes:
        scene_num = scene_data["scene"]
        scene_dir = scenes_dir / f"scene{scene_num}"

        # Copy base template
        if scene_dir.exists():
            shutil.rmtree(scene_dir)
        shutil.copytree(template_dir, scene_dir)

        # Copy audio files for this scene
        audio_src = session_dir / "audio"
        audio_dst = scene_dir / "public" / "audio"
        audio_dst.mkdir(parents=True, exist_ok=True)
        for seg in scene_data.get("subtitles", []):
            src_file = audio_src / seg["file"]
            if src_file.exists():
                shutil.copy2(src_file, audio_dst / seg["file"])

        # Inject scene config into index.html
        await _inject_scene_config(scene_dir, scene_data)

        # Generate animation code with Claude Agent SDK
        await _generate_scene_animation(scene_dir, scene_data)

        # Install npm dependencies
        await _npm_install(scene_dir)

        logger.info("Scene %d animation generated", scene_num)


async def _inject_scene_config(scene_dir: Path, scene_data: dict) -> None:
    """Inject scene configuration into the HTML file as a global variable."""
    config = {
        "scene": scene_data["scene"],
        "name": scene_data["name"],
        "annotation": scene_data.get("annotation", ""),
        "description": scene_data.get("description", ""),
        "subtitles": scene_data.get("subtitles", []),
        "total_frames": scene_data.get("total_frames", 150),
        "fps": settings.video_fps,
        "width": settings.video_width,
        "height": settings.video_height,
    }

    index_html = scene_dir / "index.html"
    content = index_html.read_text()
    script_tag = (
        f'<script>window.__SCENE_CONFIG__ = {json.dumps(config, ensure_ascii=False)};</script>\n'
        '    <script type="module" src="/src/main.tsx"></script>'
    )
    content = content.replace(
        '<script type="module" src="/src/main.tsx"></script>',
        script_tag,
    )
    index_html.write_text(content)


async def _generate_scene_animation(scene_dir: Path, scene_data: dict) -> None:
    """Use Claude Agent SDK to generate the scene animation code."""
    scene_info = json.dumps(scene_data, ensure_ascii=False, indent=2)

    prompt = f"""请为以下视频场景创建精美的 React 动画。

## 场景信息
```json
{scene_info}
```

## 视频参数
- 分辨率: {settings.video_width}x{settings.video_height}
- FPS: {settings.video_fps}
- 总帧数: {scene_data.get('total_frames', 150)}

## 要求
1. 修改 `src/SceneContent.tsx`，创建与场景描述匹配的视觉动画
2. 可以在 `src/components/` 下创建子组件
3. 所有动画必须基于帧号（使用 interpolate/spring），不要用 CSS transition
4. 至少 5 个视觉元素，3 个动画效果
5. 使用科技感配色和渐变背景
6. 代码完整，不留 TODO

请直接修改文件，不需要解释。
"""

    messages = []
    async for msg in query(
        prompt=prompt,
        options=ClaudeCodeOptions(
            model=settings.openrouter_model,
            cwd=str(scene_dir),
            system_prompt=ANIMATOR_SYSTEM_PROMPT,
            allowed_tools=["Write", "Edit", "Read", "Bash"],
            max_turns=20,
            permission_mode="bypassPermissions",
            env=_build_env(),
        ),
    ):
        messages.append(msg)

    logger.info(
        "Scene %d: Claude Agent completed with %d messages",
        scene_data["scene"],
        len(messages),
    )


async def _npm_install(scene_dir: Path) -> None:
    """Install npm dependencies for a scene project."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "npm", "install", "--prefer-offline",
        cwd=str(scene_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning(
            "npm install failed in %s: %s",
            scene_dir,
            stderr.decode()[:500],
        )
    else:
        logger.info("npm install completed for %s", scene_dir.name)


async def resume_and_modify(
    session_dir: Path,
    prompt: str,
    scenes: list[dict],
    claude_session_id: str | None = None,
) -> None:
    """Resume a session and modify animations based on user feedback."""
    scenes_dir = session_dir / "scenes"

    for scene_data in scenes:
        scene_num = scene_data["scene"]
        scene_dir = scenes_dir / f"scene{scene_num}"
        if not scene_dir.exists():
            continue

        modify_prompt = f"""用户对视频提出了修改意见，请根据以下反馈修改动画代码：

## 用户反馈
{prompt}

## 当前场景信息
```json
{json.dumps(scene_data, ensure_ascii=False, indent=2)}
```

请直接修改相关文件。
"""
        async for msg in query(
            prompt=modify_prompt,
            options=ClaudeCodeOptions(
                model=settings.openrouter_model,
                cwd=str(scene_dir),
                system_prompt=ANIMATOR_SYSTEM_PROMPT,
                allowed_tools=["Write", "Edit", "Read", "Bash"],
                max_turns=15,
                permission_mode="bypassPermissions",
                env=_build_env(),
            ),
        ):
            pass

        logger.info("Scene %d modified", scene_num)


def _build_env() -> dict[str, str]:
    """Build environment variables for the Claude CLI subprocess to use OpenRouter."""
    return {
        "ANTHROPIC_AUTH_TOKEN": settings.openrouter_api_key,
        "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
        "ANTHROPIC_API_KEY": "",
    }
