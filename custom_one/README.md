  项目结构                                                        
                                                                                                                                                                                                               
  custom_one/                                                     
  ├── pyproject.toml                    # uv 依赖管理                                                                                                                                                          
  ├── .env.example                      # 配置模板                
  ├── .gitignore
  ├── templates/
  │   ├── script_prompt.md              # 文章→脚本的 LLM 提示词
  │   └── animation_prompt.md           # 动画工程生成提示词
  ├── src/custom_one/
  │   ├── config.py                     # 从 .env 加载配置
  │   ├── main.py                       # FastAPI 应用入口
  │   ├── cli.py                        # CLI 入口 (click)
  │   ├── models/schemas.py             # Pydantic 数据模型
  │   ├── api/routes.py                 # REST API 路由 (15 endpoints)
  │   ├── services/
  │   │   ├── session_manager.py        # Session 生命周期管理
  │   │   ├── script_generator.py       # 文章→subtitles.json (OpenRouter)
  │   │   ├── tts_service.py            # 阿里云 DashScope TTS (WebSocket)
  │   │   ├── animation_generator.py    # Claude Code SDK → React+Vite
  │   │   ├── video_renderer.py         # Playwright + ffmpeg 渲染
  │   │   └── pipeline.py              # 全流程编排 + 自动重试
  │   └── static/webui/index.html       # Web UI (暗色主题 SPA)

  核心流程

  1. 提交文章 → OpenRouter API 生成 subtitles.json
  2. TTS → 阿里云 DashScope WebSocket 生成 MP3 配音
  3. 动画生成 → Claude Code SDK 生成 React+Vite 项目
  4. 渲染 → Playwright 逐帧截图 + ffmpeg 合成 MP4
  5. 归档 → 项目打包为 zip，支持通过 session ID 恢复修改

  关键设计

  - 帧控制协议: React 应用读取 window.__CURRENT_FRAME__，渲染后设置 window.__FRAME_READY__ = true，Playwright 等待信号后截图
  - 渲染重试: 渲染失败自动调用 Claude Code SDK 修复代码，最多重试 3 次
  - Session 管理: 文件系统存储，支持 stop/delete/resume 操作
  - Web UI: 实时 SSE 推送进度，iframe 预览动画，帧滑块调试

  启动方式

  # 配置 .env 后启动 HTTP Server + Web UI
  uv run custom-one server

  # CLI 直接生成
  uv run custom-one run article.md -o output.mp4

  需要先安装 Playwright 浏览器：uv run playwright install chromium
