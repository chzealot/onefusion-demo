# RemotionOne

将文章转换为讲解视频的工具。采用 Remotion + LLM 技术，全链路自动化：文章 → 视频脚本 → TTS 配音 → Remotion 工程代码 → MP4 视频。

## 技术栈

- **Python 3.11+** / FastAPI / async 全链路
- **Anthropic SDK + OpenRouter** - LLM 生成视频脚本（subtitles.json）
- **edge-tts** - 中文语音合成
- **Claude Code SDK** - 自动生成 Remotion 工程代码（通过 OpenRouter API）
- **Remotion** - React 视频框架，渲染 MP4
- **uv** - Python 依赖管理

## 项目结构

```
remotion_one/
├── pyproject.toml                  # uv 项目配置
├── .env / .env.example             # 环境变量
├── web/index.html                  # Web UI（Tailwind + Alpine.js）
├── workspaces/                     # 每个 session 的工作目录
└── src/remotion_one/
    ├── config.py                   # .env 配置管理
    ├── models.py                   # Pydantic 数据模型
    ├── session.py                  # 文件级 Session 管理
    ├── pipeline.py                 # 全链路 Pipeline 编排
    ├── main.py                     # FastAPI 入口
    ├── cli.py                      # CLI 入口
    ├── api/routes.py               # REST API 路由
    ├── services/
    │   ├── scriptwriter.py         # LLM 生成 subtitles.json
    │   ├── tts.py                  # edge-tts 语音合成
    │   ├── remotion_gen.py         # Claude Code SDK 生成 Remotion 代码
    │   └── renderer.py             # Remotion 渲染 + 自动修复
    └── resources/
        └── remotion-best-practices/  # Remotion 最佳实践 skill（注入到工程中）
```

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 OPENROUTER_API_KEY
```

`.env` 关键配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENROUTER_API_KEY` | OpenRouter API Key（必填） | - |
| `OPENROUTER_BASE_URL` | OpenRouter API 地址 | `https://openrouter.ai/api/v1` |
| `CLAUDE_MODEL` | 模型名称 | `anthropic/claude-sonnet-4` |
| `VIDEO_WIDTH` | 视频宽度 | `1920` |
| `VIDEO_HEIGHT` | 视频高度 | `1080` |
| `VIDEO_FPS` | 视频帧率 | `30` |
| `TTS_VOICE` | TTS 音色 | `yunxi` |

支持的 TTS 音色：`yunxi`（男声温暖）、`xiaoxiao`（女声亲切）、`yunyang`（男声新闻）、`xiaoyi`（女声年轻）

### 3. 启动服务

```bash
uv run remotion-one serve
```

浏览器打开 `http://localhost:8000` 进入 Web UI。

## 访问方式

提供三种等价的访问方式：

### Web UI

浏览器打开 `http://localhost:8000`，支持：
- 提交文章、配置参数
- 实时查看 pipeline 进度
- 在线播放/下载视频
- 上传参考图片修改视频

### REST API

```bash
# 提交文章
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"article": "文章内容...", "requirements": "具体要求"}'

# 查询进度
curl http://localhost:8000/api/sessions/{session_id}

# 修改视频（resume）
curl -X POST http://localhost:8000/api/sessions/{session_id}/resume \
  -H "Content-Type: application/json" \
  -d '{"prompt": "修改指令", "images": ["base64图片..."]}'

# 下载产物
curl -O http://localhost:8000/api/sessions/{session_id}/video      # MP4 视频
curl -O http://localhost:8000/api/sessions/{session_id}/subtitles   # subtitles.json
curl -O http://localhost:8000/api/sessions/{session_id}/project     # Remotion 工程 ZIP

# 列出所有 session
curl http://localhost:8000/api/sessions
```

### CLI

```bash
# 提交文章（支持 @文件路径）
uv run remotion-one submit --article @article.txt --requirements "面向开发者"

# 查询进度（--watch 持续轮询）
uv run remotion-one status {session_id} --watch

# 修改视频
uv run remotion-one resume {session_id} --prompt "把配色改成蓝色系"

# 下载产物
uv run remotion-one download {session_id} --type video
uv run remotion-one download {session_id} --type subtitles
uv run remotion-one download {session_id} --type project

# 列出所有 session
uv run remotion-one list
```

## 生成流程

```
文章 + 要求
    │
    ▼
┌─────────────────┐
│ 1. 生成脚本      │  Anthropic SDK + OpenRouter → subtitles.json
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. TTS 配音      │  edge-tts → public/audio/*.mp3
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. 生成代码      │  Claude Code SDK → Remotion 工程
└────────┬────────┘
         ▼
┌─────────────────┐
│ 4. 渲染视频      │  npx remotion render → output.mp4
│   (失败自动修复)  │  渲染报错 → Claude Code SDK 修复 → 重试（最多3次）
└────────┬────────┘
         ▼
    产物清单
    ├── subtitles.json
    ├── output.mp4
    └── project.zip（Remotion 工程代码）
```

## Resume 流程

视频生成完成后，可通过 session_id 提交新的 prompt（文字 + 图片）修改视频：

1. 从 `project.zip` 恢复 Remotion 工程
2. Claude Code SDK resume 上次的会话，执行修改指令
3. 重新渲染 MP4
4. 生成新版本的产物清单

## 视频分辨率

默认 1920x1080 (1080p)，支持通过参数配置：

| 预设 | 宽度 | 高度 |
|------|------|------|
| 1080p 横版 | 1920 | 1080 |
| 4K 横版 | 3840 | 2160 |
| 1080p 竖版 | 1080 | 1920 |
| 4K 竖版 | 2160 | 3840 |

提交时通过 `video_width` / `video_height` 参数指定。
