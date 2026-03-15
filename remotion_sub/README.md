# Remotion Sub - 文章转讲解视频工具

将长篇文章自动转换为带动画的讲解短视频。基于 Remotion + LLM + TTS 技术栈。

## 生成流程

```
文章 → 字幕脚本(subtitles.json) → TTS配音 → Claude Agent SDK 生成 Remotion 工程代码 → Remotion 渲染 mp4
```

1. **生成字幕脚本**：通过 Claude Agent SDK 将文章转换为 subtitles.json
2. **TTS 生成配音**：阿里云 CosyVoice 流式语音合成（WSS 协议），音色 zhishuo
3. **生成 Remotion 工程**：Claude Agent SDK 生成完整的 Remotion TypeScript 项目，每个 scene 独立 Composition
4. **渲染视频**：通过 `npx remotion render` 渲染，失败自动用 Claude Agent SDK 修复并重试（最多 3 次）
5. **最终产物**：subtitles.json、output.mp4、remotion 工程 zip 包

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Python FastAPI（全链路 async） |
| 依赖管理 | uv |
| 数据库 | SQLite（aiosqlite，WAL 模式） |
| LLM | Claude Code SDK (Python) + OpenRouter API |
| TTS | 阿里云 CosyVoice 流式语音合成（WSS） |
| 视频渲染 | Remotion（Node.js/TypeScript） |
| 配置管理 | .env + python-dotenv + pydantic-settings |
| CLI | Click |

## 项目结构

```
remotion_sub/
├── pyproject.toml                          # 项目配置、依赖、CLI 入口
├── .env.example                            # 环境变量模板
├── .gitignore
├── remotion_sub.db                         # SQLite 数据库（自动生成）
│
├── src/remotion_sub/
│   ├── config.py                           # 配置（从 .env 加载）
│   ├── database.py                         # SQLite 初始化
│   ├── main.py                             # FastAPI 应用入口
│   ├── cli.py                              # CLI 命令
│   │
│   ├── models/
│   │   └── schemas.py                      # Pydantic 模型（请求/响应/内部）
│   │
│   ├── api/
│   │   └── routes.py                       # REST API 路由（11 个端点）
│   │
│   ├── services/
│   │   ├── session.py                      # Session 管理（SQLite CRUD + 任务追踪）
│   │   ├── scriptwriter.py                 # 文章 → subtitles.json
│   │   ├── tts.py                          # CosyVoice WSS TTS + ffmpeg 合并
│   │   ├── remotion_generator.py           # Claude Agent SDK → Remotion 工程
│   │   ├── renderer.py                     # Remotion CLI 渲染（单场景 + 完整视频）
│   │   └── pipeline.py                     # 流水线编排（含自动重试/修复）
│   │
│   ├── prompts/                            # LLM 提示词模板
│   ├── resources/remotion-best-practices/  # Remotion 技能文件（供 Claude Agent 使用）
│   └── static/webui/index.html             # Web UI（单文件，深色主题）
│
└── workspaces/                             # 每个 session 的工作目录
    └── {session_id}/
        ├── article.md
        ├── subtitles.json
        ├── audio/                          # TTS 音频文件
        ├── remotion/                       # Remotion 工程代码
        ├── videos/                         # 渲染输出
        │   ├── scene1.mp4
        │   ├── scene2.mp4
        │   └── full.mp4
        └── project.zip                     # 工程归档
```

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 3. 启动服务
uv run remotion-sub server

# 浏览器打开 http://localhost:8000
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENROUTER_API_KEY` | OpenRouter API Key（Claude Code SDK 使用） | - |
| `CLAUDE_CODE_MODEL` | Claude 模型 | `anthropic/claude-sonnet-4-20250514` |
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key | - |
| `TTS_VOICE` | TTS 音色 | `zhishuo` |
| `TTS_SPEED` | TTS 语速 | `45` |
| `TTS_PITCH` | TTS 语调 | `25` |
| `TTS_VOLUME` | TTS 音量 | `60` |
| `VIDEO_WIDTH` | 视频宽度 | `1920` |
| `VIDEO_HEIGHT` | 视频高度 | `1080` |
| `VIDEO_FPS` | 帧率 | `30` |
| `HOST` | 服务监听地址 | `0.0.0.0` |
| `PORT` | 服务端口 | `8000` |

## 访问方式

### 1. Web UI

启动服务后浏览器打开 `http://localhost:8000`。

功能：
- 创建/删除/结束 session
- 实时查看生成进度（SSE 推送）
- Scenes 页签：逐个播放场景视频，支持连续播放和单场景循环
- 场景视频满意后点击"Render Full Video"渲染完整视频
- Resume & Modify：提交新 prompt 修改视频内容

### 2. CLI

```bash
# 从文章文件直接生成视频
uv run remotion-sub run article.md -r "60秒，技术受众" -o output.mp4

# 列出所有 session
uv run remotion-sub list

# 查看 session 状态
uv run remotion-sub status <session_id>

# 恢复并修改
uv run remotion-sub resume <session_id> -p "把第二个场景的动画换成柱状图"
```

### 3. HTTP REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/sessions` | POST | 提交文章，启动生成流水线 |
| `/api/sessions` | GET | 列出所有 session |
| `/api/sessions/{id}` | GET | 获取 session 详情 |
| `/api/sessions/{id}/status` | GET | 获取状态快照 |
| `/api/sessions/{id}/stream` | GET | SSE 实时状态推送 |
| `/api/sessions/{id}/resume` | POST | 恢复并提交修改 prompt |
| `/api/sessions/{id}/stop` | POST | 结束任务 |
| `/api/sessions/{id}` | DELETE | 删除 session（自动先结束任务） |
| `/api/sessions/{id}/render` | POST | 触发渲染完整视频 |
| `/api/sessions/{id}/video` | GET | 下载完整视频 |
| `/api/sessions/{id}/scenes/{n}/video` | GET | 下载单个场景视频 |
| `/api/sessions/{id}/subtitles` | GET | 获取字幕脚本 |

**创建 session 示例：**

```bash
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"article": "你的文章内容...", "requirements": "60秒技术视频"}'
```

## 前置依赖

- Python >= 3.11
- Node.js >= 18（Remotion 渲染需要）
- ffmpeg / ffprobe（音频处理需要）
- Claude Code CLI（claude-code-sdk 内置）
