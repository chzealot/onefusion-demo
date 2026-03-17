"""Animator service: Uses Claude Agent SDK to generate a multi-entry Vite project."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, query

from custom_sub_v2.config import settings
from custom_sub_v2.services.logger import get_project_logger

ANIMATOR_SYSTEM_PROMPT = """你是一位精英级前端动画专家，擅长使用 React 和 TypeScript 创建专业的视频动画场景。

## 你的任务

你将收到一个视频场景的描述信息，需要修改当前多入口 Vite 项目中对应场景的组件文件，
创建精美的动画效果来可视化场景内容。

## 技术栈

- React 18 + TypeScript + Vite（多入口项目）
- 基于帧号的动画系统（不要使用 CSS transition/animation 或 setTimeout）
- 项目已提供以下工具函数（在 src/hooks/ 和 src/utils/ 中）：
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

- 修改 `src/scenes/SceneXX/index.tsx` 文件
- 可以在 `src/scenes/SceneXX/` 下创建子组件文件
- 导入路径使用相对路径
- 共用 hooks 和 utils 从 `../../hooks/useFrame` 和 `../../utils/animation` 导入
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
    project_id: str = "",
) -> None:
    """Generate React animation code for each scene in a multi-entry Vite project.

    1. Copy the project_base template to sessions/{id}/project/
    2. Create scene entry points
    3. For each scene, call Claude Agent SDK to generate scene components
    4. Install npm dependencies once
    """
    log = get_project_logger(project_id) if project_id else None
    project_dir = session_dir / "project"
    template_dir = settings.templates_dir / "project_base"

    # Copy base template
    if project_dir.exists():
        shutil.rmtree(project_dir)
    shutil.copytree(template_dir, project_dir)

    # Create scene directories and entry points
    for scene_data in scenes:
        scene_num = scene_data["scene"]
        scene_dir = project_dir / "src" / "scenes" / f"Scene{scene_num:02d}"
        scene_dir.mkdir(parents=True, exist_ok=True)

        # Copy default SceneContent
        _create_default_scene(scene_dir, scene_num)

        # Create scene-specific HTML entry
        _create_scene_entry(project_dir, scene_data, scene_num)

        # Copy audio files for this scene
        audio_src = session_dir / "audio"
        audio_dst = project_dir / "public" / "audio"
        audio_dst.mkdir(parents=True, exist_ok=True)
        for seg in scene_data.get("subtitles", []):
            src_file = audio_src / seg["file"]
            if src_file.exists():
                shutil.copy2(src_file, audio_dst / seg["file"])

    # Update vite.config.ts with all scene entries
    _update_vite_config(project_dir, scenes)

    # Install npm dependencies once
    await _npm_install(project_dir, log)

    # Generate animation code for each scene
    for scene_data in scenes:
        scene_num = scene_data["scene"]
        if log:
            log.info("Generating animation for scene %d...", scene_num)

        await _generate_scene_animation(project_dir, scene_data, log)

        if log:
            log.info("Scene %d animation generated", scene_num)


def _create_default_scene(scene_dir: Path, scene_num: int) -> None:
    """Create a default SceneContent component."""
    content = f'''import {{ useCurrentFrame }} from '../../hooks/useFrame'
import {{ interpolate, spring, Easing }} from '../../utils/animation'
import type {{ SceneConfig }} from '../../types'

interface Props {{
  config: SceneConfig
}}

export function SceneContent({{ config }}: Props) {{
  const frame = useCurrentFrame()

  const titleOpacity = interpolate(frame, [0, 20], [0, 1])
  const titleY = spring(frame, {{ stiffness: 80, damping: 15, from: -50, to: 0 }})
  const descOpacity = interpolate(frame, [15, 35], [0, 1], {{ easing: Easing.easeOut }})

  return (
    <div
      style={{{{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '5%',
        background: 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
      }}}}
    >
      <h1
        style={{{{
          fontSize: '48px',
          fontWeight: 800,
          color: '#fff',
          opacity: titleOpacity,
          transform: `translateY(${{titleY}}px)`,
          textAlign: 'center',
          marginBottom: '24px',
        }}}}
      >
        {{config.name}}
      </h1>
      <p
        style={{{{
          fontSize: '24px',
          color: 'rgba(255,255,255,0.8)',
          opacity: descOpacity,
          textAlign: 'center',
          maxWidth: '80%',
          lineHeight: 1.6,
        }}}}
      >
        {{config.description}}
      </p>
    </div>
  )
}}
'''
    (scene_dir / "index.tsx").write_text(content)


def _create_scene_entry(project_dir: Path, scene_data: dict, scene_num: int) -> None:
    """Create an HTML entry point for a scene with injected config."""
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

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Scene {scene_num:02d}</title>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body, #root {{ width: 100%; height: 100%; overflow: hidden; }}
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script>window.__SCENE_CONFIG__ = {json.dumps(config, ensure_ascii=False)};</script>
    <script>window.__SCENE_ID__ = "Scene{scene_num:02d}";</script>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
'''
    (project_dir / f"scene{scene_num:02d}.html").write_text(html)


def _update_vite_config(project_dir: Path, scenes: list[dict]) -> None:
    """Update vite.config.ts with multi-entry input configuration."""
    entries = ['    main: resolve(__dirname, "index.html"),']
    for scene_data in scenes:
        n = scene_data["scene"]
        entries.append(f'    scene{n:02d}: resolve(__dirname, "scene{n:02d}.html"),')

    entries_str = "\n".join(entries)
    config = f'''import {{ defineConfig }} from 'vite'
import react from '@vitejs/plugin-react'
import {{ resolve }} from 'path'

export default defineConfig({{
  plugins: [react()],
  server: {{
    host: true,
    cors: true,
  }},
  build: {{
    rollupOptions: {{
      input: {{
{entries_str}
      }},
    }},
  }},
}})
'''
    (project_dir / "vite.config.ts").write_text(config)


async def _generate_scene_animation(
    project_dir: Path,
    scene_data: dict,
    log=None,
) -> None:
    """Use Claude Agent SDK to generate the scene animation code."""
    scene_num = scene_data["scene"]
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
1. 修改 `src/scenes/Scene{scene_num:02d}/index.tsx`，创建与场景描述匹配的视觉动画
2. 可以在 `src/scenes/Scene{scene_num:02d}/` 下创建子组件文件
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
            cwd=str(project_dir),
            system_prompt=ANIMATOR_SYSTEM_PROMPT,
            allowed_tools=["Write", "Edit", "Read", "Bash"],
            max_turns=20,
            permission_mode="bypassPermissions",
            env=_build_env(),
        ),
    ):
        messages.append(msg)

    if log:
        log.info(
            "Scene %d: Claude Agent completed with %d messages",
            scene_num, len(messages),
        )


async def resume_and_modify(
    session_dir: Path,
    prompt: str,
    scenes: list[dict],
    project_id: str = "",
) -> None:
    """Resume a session and modify animations based on user feedback."""
    log = get_project_logger(project_id) if project_id else None
    project_dir = session_dir / "project"

    for scene_data in scenes:
        scene_num = scene_data["scene"]

        modify_prompt = f"""用户对视频提出了修改意见，请根据以下反馈修改动画代码：

## 用户反馈
{prompt}

## 当前场景信息
```json
{json.dumps(scene_data, ensure_ascii=False, indent=2)}
```

请修改 `src/scenes/Scene{scene_num:02d}/index.tsx` 及相关文件。
"""
        async for msg in query(
            prompt=modify_prompt,
            options=ClaudeCodeOptions(
                model=settings.openrouter_model,
                cwd=str(project_dir),
                system_prompt=ANIMATOR_SYSTEM_PROMPT,
                allowed_tools=["Write", "Edit", "Read", "Bash"],
                max_turns=15,
                permission_mode="bypassPermissions",
                env=_build_env(),
            ),
        ):
            pass

        if log:
            log.info("Scene %d modified", scene_num)


async def _npm_install(project_dir: Path, log=None) -> None:
    """Install npm dependencies for the project."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "npm", "install", "--prefer-offline",
        cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        if log:
            log.warning("npm install failed: %s", stderr.decode()[:500])
    else:
        if log:
            log.info("npm install completed")


def _build_env() -> dict[str, str]:
    """Build environment variables for the Claude CLI subprocess to use OpenRouter."""
    return {
        "ANTHROPIC_AUTH_TOKEN": settings.openrouter_api_key,
        "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
        "ANTHROPIC_API_KEY": "",
    }
