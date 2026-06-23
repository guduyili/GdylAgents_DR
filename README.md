# GdylAgents_DR

GdylAgents_DR 是一个基于 FastAPI、Vue 3 和 HelloAgents 的深度研究助手项目。

用户输入研究主题后，系统会自动生成研究计划，按任务搜索和总结资料，通过 SSE 实时推送进度，最后生成 Markdown 研究报告并保存到本地笔记目录。

## 技术栈

后端：

- Python 3.10+
- FastAPI
- HelloAgents
- SSE / StreamingResponse
- 本地文件持久化笔记和报告索引

前端：

- Vue 3
- TypeScript
- Vite

## 目录结构

```text
.
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   └── src/
│       ├── main.py                 # FastAPI HTTP 入口
│       ├── agent.py                # 深度研究流程编排
│       ├── config.py               # 环境变量配置
│       ├── models.py               # 后端数据模型
│       ├── services/               # 规划、搜索、总结、报告、事件追踪服务
│       └── utils.py                # 通用工具函数
├── frontend/
│   ├── package.json
│   ├── .env.example
│   └── src/
│       ├── App.vue
│       ├── services/api.ts
│       └── types/research.ts
└── docs/
    ├── project.md                 # 架构与前后端调用链概览
    ├── learning.md                # 初学者优化与学习建议
    ├── topic_call_chain.md        # 用户输入 topic 后的完整 Agent 调用链
    └── tool_call_event.md         # 工具调用事件记录链路
```

## 环境变量配置

后端：

```bash
cd backend
cp .env.example .env
```

然后编辑 backend/.env，至少配置：

```bash
LLM_PROVIDER=custom
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=your-api-key
LLM_MODEL_ID=your-model-id
REPORT_MODEL_ID=your-report-model-id
SEARCH_API=duckduckgo
NOTES_WORKSPACE=./data/notes
RUN_STORE_BACKEND=sqlite
RUN_STORE_DB_PATH=./data/research_runs.sqlite3
```

前端：

```bash
cd frontend
cp .env.example .env
```

默认配置：

```bash
VITE_API_BASE_URL=http://localhost:8000
```

注意：

- .env 里可能包含 API Key，不要提交到 Git。
- .env.example 只放示例值，可以提交。
- 运行生成的笔记、报告、dist、缓存目录不应提交。

## 后端启动

推荐在 backend 目录安装依赖并启动：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

如果使用 uv：

```bash
cd backend
uv sync --extra dev
uv run uvicorn main:app --app-dir src --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/healthz
```

预期返回：

```json
{"status":"ok"}
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

构建验证：

```bash
npm run build
```

## 常用接口

```text
GET  /healthz
POST /research/plan
POST /research/stream
GET  /notes/reports
GET  /notes/reports/{note_id}
```

## Docker Compose 部署

项目根目录提供 `docker-compose.yml`，会构建前后端镜像并通过 nginx 反代：

```bash
# 1. 配置 LLM / 搜索密钥（compose 会加载此文件）
cp backend/.env.example backend/src/.env
# 编辑 backend/src/.env，至少填写 LLM_* 与 SEARCH_API 相关项

# 2. 构建并启动
docker compose build
docker compose up -d

# 3. 访问
# 前端：http://localhost:3000
# 后端健康检查仅在容器内：curl http://0.0.0.0:8000/healthz
```

Compose 中与本地开发不同的路径/行为（`environment` 会覆盖 `env_file` 中的同名项）：

| 变量 | 容器内值 | 说明 |
|------|----------|------|
| `NOTES_WORKSPACE` | `/app/src/note` | 笔记 volume 挂载点 |
| `RUN_STORE_DB_PATH` | `/app/src/data/research_runs.sqlite3` | 运行时间线 SQLite |
| `SKILLS_WORKSPACE` | `/app/src/skills` | Skill 目录；镜像内已 COPY，并只读挂载 `./backend/skills` |
| `RESEARCH_PIPELINE` | `plan,search,summarize,fact_check,report,review` | 多阶段流水线 |
| `ENABLE_FACT_CHECK` / `ENABLE_REPORT_REVIEW` | `true` | 事实核对与报告评审 |
| `ENABLE_BROWSER_FETCH` | `false` | 默认关闭 Playwright（避免 slim 镜像膨胀） |

更新 Skill 文件后无需重建镜像，重启 backend 即可（volume 已挂载）。启用浏览器抓取需单独安装 Playwright 依赖，不建议在默认 slim 镜像中开启。

## 测试

后端测试推荐使用 uv 安装 dev 依赖并运行：

```bash
cd backend
uv run --extra dev python -m pytest -q
```

如果使用手动虚拟环境：

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

前端构建检查：

```bash
cd frontend
npm run build
```

## 当前重点优化方向

当前仓库的架构已从 demo 阶段进化到工程阶段：`DeepResearchAgent` 只做编排门面，`services/*` 承载全部业务，SSE 事件有强类型契约和 `run_id` 级可观测性，前端已拆出 Trace/Timeline 等组件。

**详细的学习路线、代码阅读路径、具体练习和最小可验证交付，请参阅 [docs/learning.md](docs/learning.md)**，该文档基于当前仓库实际代码持续更新。

推荐优先级：

1. 可靠性：并发限制、搜索/总结超时、搜索 fallback
2. 协议收紧：所有事件走 `normalize_stream_event()`、前端 zod 校验
3. 可观测性：阶段耗时事件、Trace 过滤/导出、工具调用预览
4. 能力扩展：轻量模式、搜索后端 Protocol、报告后处理
5. 测试：核心路径单测、Agent 评估体系