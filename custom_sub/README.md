# Custom Sub

将文章转换为讲解视频的工具。基于 LLM 生成脚本、TTS 配音、React 动画和无头浏览器渲染。

## 技术栈

- **Python 3.11+** / FastAPI / async 全链路
- **Claude Agent SDK (Python)** — 通过 OpenRouter API 生成字幕脚本和 React 动画代码
- **DashScope CosyVoice** — 阿里云百炼 TTS（音色 zhishuo）
- **React 18 + Vite + TypeScript** — 每个 scene 独立前端项目
- **Playwright** — 无头浏览器逐帧截图
- **ffmpeg** — 合成音视频
- **uv** — Python 依赖管理

## 快速开始

```bash
# 1. 复制并编辑环境变量
cp .env.example .env
# 填入 OPENROUTER_API_KEY 和 DASHSCOPE_API_KEY

# 2. 安装依赖
uv sync
uv run playwright install chromium

# 3. 启动服务器（Web UI + REST API）
uv run custom-sub serve

# 4. 或使用 CLI
uv run custom-sub submit article.txt -r "侧重技术原理讲解"
```

Web UI 访问 `http://localhost:8000`。

## 项目结构

```
custom_sub/
├── pyproject.toml                  # uv 项目配置
├── .env.example                    # 环境变量模板
├── src/custom_sub/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # pydantic-settings 配置
│   ├── cli.py                      # Click CLI
│   ├── api/
│   │   ├── models.py               # Pydantic 数据模型
│   │   └── routes.py               # REST API 路由
│   ├── services/
│   │   ├── session.py              # 文件系统 session 管理
│   │   ├── scriptwriter.py         # Claude Agent → subtitles.json
│   │   ├── tts.py                  # DashScope CosyVoice TTS
│   │   ├── animator.py             # Claude Agent → React 动画代码
│   │   ├── renderer.py             # Playwright 逐帧截图 + ffmpeg 合成
│   │   └── pipeline.py             # 全流程编排（含错误自动修复）
│   ├── templates/scene_base/       # React+Vite 场景模板
│   │   ├── src/hooks/useFrame.ts   # 帧号 hook（预览/渲染双模式）
│   │   ├── src/utils/animation.ts  # interpolate/spring 动画工具
│   │   ├── src/components/Subtitle.tsx
│   │   └── src/SceneContent.tsx    # Claude Agent 修改此文件
│   └── web/static/index.html       # Vue3 + Tailwind Web UI
└── sessions/                       # 会话数据（gitignored）
```

## 核心流程

```
提交文章 → 生成字幕脚本 → TTS 配音 → 生成 React 动画 → 渲染视频
                                                        ↑ 失败自动修复
```

1. **生成字幕脚本** — Claude Agent SDK 将文章转为 `subtitles.json`
2. **TTS 配音** — DashScope CosyVoice 为每句字幕生成 mp3
3. **生成动画** — Claude Agent SDK 为每个 scene 生成独立 React + Vite 项目
4. **渲染视频** — Playwright 逐帧截图 + ffmpeg 合成 mp4（渲染失败自动调用 Claude 修复代码后重试）
5. **打包产物** — `output.mp4` + `project.zip`

## REST API

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/sessions` | 提交文章+要求，返回 session_id |
| `GET` | `/api/sessions` | 列出所有 session |
| `GET` | `/api/sessions/{id}` | 查询进展 |
| `POST` | `/api/sessions/{id}/resume` | 提交修改意见（文字+图片） |
| `GET` | `/api/sessions/{id}/video` | 下载完整视频 |
| `GET` | `/api/sessions/{id}/scenes` | 列出场景及状态 |
| `GET` | `/api/sessions/{id}/scenes/{n}/video` | 下载单个场景视频 |
| `POST` | `/api/sessions/{id}/render` | 触发渲染完整视频 |
| `POST` | `/api/sessions/{id}/stop` | 停止任务（不删除） |
| `DELETE` | `/api/sessions/{id}` | 删除 session（自动停止后删除） |
| `GET` | `/api/sessions/{id}/subtitles` | 获取 subtitles.json |
| `GET` | `/api/sessions/{id}/download` | 下载工程 zip 包 |

## CLI 命令

```bash
uv run custom-sub submit <article.txt> [-r "要求"]   # 提交文章
uv run custom-sub list                                # 列出 session
uv run custom-sub progress <session_id>               # 查看进展
uv run custom-sub resume <session_id> "修改意见"       # 提交修改
uv run custom-sub stop <session_id>                   # 停止任务
uv run custom-sub delete <session_id>                 # 删除 session
uv run custom-sub serve [--host 0.0.0.0] [--port 8000] # 启动服务器
```

## 场景模板设计

每个 scene 是独立的 React + Vite 项目，支持两种模式：

- **预览模式**（默认）— 实时动画播放，可通过 iframe 嵌入 Web UI 调试
- **渲染模式**（`?mode=render&frame=N`）— 按帧号渲染静态画面，供 Playwright 截图

动画系统基于帧号而非时间，确保渲染精确同步：

```tsx
const frame = useCurrentFrame()
const opacity = interpolate(frame, [0, 30], [0, 1])
const scale = spring(frame, { stiffness: 100, damping: 15 })
```

## 配置项（.env）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENROUTER_API_KEY` | OpenRouter API Key | — |
| `OPENROUTER_MODEL` | 模型 ID | `anthropic/claude-sonnet-4-20250514` |
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | — |
| `TTS_VOICE` | TTS 音色 | `zhishuo` |
| `TTS_RATE` | 语速 | `45` |
| `TTS_PITCH` | 语调 | `25` |
| `TTS_VOLUME` | 音量 | `60` |
| `VIDEO_WIDTH` | 视频宽度 | `1920` |
| `VIDEO_HEIGHT` | 视频高度 | `1080` |
| `VIDEO_FPS` | 帧率 | `30` |

支持 4K（3840x2160）和竖屏（1080x1920）等配置。

## Session 数据结构

```
sessions/{session_id}/
├── article.txt          # 原始文章
├── requirements.txt     # 用户要求
├── subtitles.json       # 字幕脚本（含 TTS 时长信息）
├── status.json          # 流程状态
├── audio/               # TTS 音频文件
├── scenes/
│   ├── scene1/          # 独立 React+Vite 项目
│   ├── scene2/
│   └── ...
├── videos/
│   ├── scene1.mp4
│   ├── scene2.mp4
│   └── ...
├── output.mp4           # 最终合成视频
└── project.zip          # 工程代码打包
```
