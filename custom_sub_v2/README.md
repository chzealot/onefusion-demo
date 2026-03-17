# custom_sub_v2

Article to explainer video tool v2 — 文章转短视频自动化工具

## v2 核心变化（vs v1）

| 特性 | v1 | v2 |
|------|----|----|
| 字幕脚本生成 | Claude Agent SDK | OpenRouter API 直调 |
| 前端动画工程 | 每 scene 独立 Vite 项目 | 单个 Vite 多入口项目 |
| Web UI | Vue3 单文件 | React + Vite 独立工程 |
| ID 体系 | 单 session_id | 双 ID：`proj_` / `agent_` |
| 日志系统 | 全局日志 | 每项目独立日志 + 实时流 |
| 片头/片尾 | 静态图片 | 无 |

## 快速开始

### 1. 安装依赖

```bash
cd custom_sub_v2
uv sync
uv run playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 OPENROUTER_API_KEY 和 DASHSCOPE_API_KEY
```

### 3. 启动服务

```bash
uv run python -m custom_sub_v2.cli serve
```

### 4. Web UI（开发模式）

```bash
cd web
npm install
npm run dev
# 打开 http://localhost:3000
```

### 5. CLI 使用

```bash
# 提交文章
uv run python -m custom_sub_v2.cli submit article.md

# 带要求提交
uv run python -m custom_sub_v2.cli submit article.md -r "风格轻松幽默，3个场景"

# 查看列表
uv run python -m custom_sub_v2.cli list

# 查看进度
uv run python -m custom_sub_v2.cli progress proj_xxxx

# 修改并重新渲染
uv run python -m custom_sub_v2.cli resume proj_xxxx "背景改成蓝色"

# 停止
uv run python -m custom_sub_v2.cli stop proj_xxxx

# 删除
uv run python -m custom_sub_v2.cli delete proj_xxxx
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions` | 提交文章，启动流水线 |
| GET | `/api/sessions` | 列出所有会话 |
| GET | `/api/sessions/{id}` | 查询进度 |
| POST | `/api/sessions/{id}/resume` | 修改并重新渲染 |
| POST | `/api/sessions/{id}/stop` | 停止 |
| DELETE | `/api/sessions/{id}` | 删除 |
| GET | `/api/sessions/{id}/video` | 下载完整视频 |
| GET | `/api/sessions/{id}/scenes` | 场景列表 |
| GET | `/api/sessions/{id}/scenes/{n}/video` | 下载场景视频 |
| POST | `/api/sessions/{id}/render` | 触发渲染 |
| GET | `/api/sessions/{id}/subtitles` | 获取字幕 JSON |
| GET | `/api/sessions/{id}/download` | 下载项目 ZIP |
| GET | `/api/sessions/{id}/logs` | 实时日志流（SSE） |

## 流水线

```
Article → [Script] → [TTS] → [Animation] → [Render] → [Package]
           OpenRouter   DashScope  Claude Agent  Playwright   ZIP
           直调 API     CosyVoice  SDK           + FFmpeg
```

## 项目结构

```
custom_sub_v2/
├── pyproject.toml
├── .env.example
├── src/custom_sub_v2/
│   ├── config.py          # Pydantic Settings
│   ├── main.py            # FastAPI 入口
│   ├── cli.py             # Click CLI
│   ├── api/
│   │   ├── models.py      # 请求/响应模型
│   │   └── routes.py      # REST 路由 + SSE 日志
│   ├── services/
│   │   ├── logger.py      # 每项目独立日志
│   │   ├── session.py     # 双 ID 会话管理
│   │   ├── scriptwriter.py # OpenRouter 直调
│   │   ├── tts.py         # DashScope CosyVoice
│   │   ├── animator.py    # Claude Agent SDK
│   │   ├── renderer.py    # Playwright + FFmpeg
│   │   └── pipeline.py    # 流水线编排
│   └── templates/
│       └── project_base/  # 多入口 Vite 模板
├── web/                   # React Web UI
└── sessions/              # 运行时数据
```
