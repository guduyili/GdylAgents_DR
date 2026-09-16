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
    ├── beginner_agent_guide.md    # Agent 初学者入门指南（从零开始，推荐先读）
    ├── rag_learning_path.md       # RAG 进阶学习与实现路径（历史报告检索）
    ├── project.md                 # 架构与前后端调用链概览
    ├── agent_learning_roadmap.md  # Agent 知识学习与扩展路线图（项目视角）
    ├── agent_deep_dive_plan.md    # 原理与工程进阶计划：代码基线、实验、验收与优先级
    ├── learning.md                # 项目内具体练习与 8 周动手计划
    ├── cancellation.md            # 取消链路与 Redis 多 worker 广播
    ├── run_store.md               # 研究运行时间线存储
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
POST /research/stream          # 响应头 X-Research-Run-Id
POST /research/runs/{run_id}/cancel
GET  /research/runs/{run_id}
GET  /notes/reports
GET  /notes/reports/{note_id}
```

研究任务取消链路（SSE 断开 + 显式 cancel API）详见 [docs/cancellation.md](docs/cancellation.md)。

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

最小版本更新及逐版测试记录见 [版本迭代索引](docs/releases/README.md)。每版记录改动范围、复现命令、实际测试结果，并使用独立 Git 提交和版本标签管理。

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

**学习文档分层**：

**后续深入学习 Agent 原理与工程实现**：优先阅读 [进阶学习、优化与拓展计划](docs/agent_deep_dive_plan.md)，按“评估基线 → 决策循环与工具 → 证据质量 → RAG → 状态恢复 → 多 Agent 对照实验”推进。该文以当前代码核对能力边界，并给出实验与验收标准。

| 文档 | 适合场景 |
|------|----------|
| [docs/beginner_agent_guide.md](docs/beginner_agent_guide.md) | **Agent 初学者先读**：概念心智模型、6 周入门路径、自检清单、文档阅读顺序 |
| [docs/rag_learning_path.md](docs/rag_learning_path.md) | **RAG 进阶主线**：历史报告检索、4 周实现、Phase1 骨架用法 |
| [docs/topic_call_chain.md](docs/topic_call_chain.md) | 跑通系统后：用户输入 topic 后的完整调用链 |
| [docs/learning.md](docs/learning.md) | 已懂主链路：项目内具体练习、代码阅读路径、最小可验证交付 |
| [docs/agent_learning_roadmap.md](docs/agent_learning_roadmap.md) | 进阶全景：编排、RAG、MCP、多 Agent、平台化 |
| [docs/agent_deep_dive_plan.md](docs/agent_deep_dive_plan.md) | **原理与工程深挖**：当前代码边界、优先实验、12 周计划与评估口径 |
| [docs/cancellation.md](docs/cancellation.md) | 长任务取消链路与 Redis 多 worker 部署 |

当前仓库已进入工程阶段（并发控制、取消广播、fact_check/review、evals、Skill 等均已落地）。  
**初学者**：按 beginner guide 阶段 0～3 打底 → 再选一条进阶线。  
**RAG 进阶**：见 [docs/rag_learning_path.md](docs/rag_learning_path.md)；Phase1 词项检索已接入（`ENABLE_REPORT_RAG=true`）。
