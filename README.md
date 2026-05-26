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
    ├── architecture.md
    ├── learning-and-optimization-guide.md
    └── tool_call_event_chain.md
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

## 测试

后端测试：

```bash
cd backend
python -m pytest -q
```

前端构建检查：

```bash
cd frontend
npm run build
```

## 当前重点优化方向

1. 工程卫生：修复 .gitignore、清理运行产物、补齐 .env.example。
2. 测试体系：先为 config.py、utils.py、planner.py、tool_events.py、main.py 写低成本单元测试。
3. 前端拆分：逐步把大型 App.vue 拆成 ResearchForm、PlanEditor、HistoryPage、ReportViewer 等组件。
4. 后端拆分：继续把 agent.py 中的 LLM 创建、任务执行、流式运行、报告存储拆成独立服务。
5. 稳定性：为 SSE 事件定义前后端强类型协议，增加并发限制、timeout 和搜索 fallback。

## 学习建议

初学者建议按以下顺序学习：

1. Git、.gitignore、.env 和工程目录卫生。
2. FastAPI 的 BaseModel、HTTPException、StreamingResponse。
3. Python 单元测试和 pytest。
4. Vue 3 组件拆分与 TypeScript 类型。
5. SSE 流式协议和前后端事件契约。
6. Agent 编排、并发控制、搜索 fallback 和可观测性。
