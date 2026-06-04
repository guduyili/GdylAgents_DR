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

当前阶段暂时不优先做运行产物清理，先从 Agent 架构拆分开始优化。推荐顺序如下：

1. 后端 Agent 拆分：先把 `agent.py` 中的 LLM 创建、工具注册、任务执行、流式运行、报告持久化拆成独立服务。
2. 测试体系：每拆出一个服务，就补一组低成本单元测试，保证重构不改变行为。
3. SSE 协议稳定性：为前后端事件定义强类型协议，减少 `type: string` 和任意字段带来的维护风险。
4. 并发与 timeout：限制最大并发任务数，为搜索、总结、报告生成增加超时和 fallback。
5. 可观测性与评估：增加 run_id、阶段耗时、任务 trace，并建立最小 eval 用例集。
6. 前端拆分：继续把大型页面拆成 ResearchForm、PlanEditor、ResearchBoard、HistoryPage、ReportViewer 等组件。

### 方向一：后端 Agent 拆分

`backend/src/agent.py` 当前承担了过多职责：

- LLM 初始化
- NoteTool 与 ToolRegistry 初始化
- Planner / Summarizer / Reporter Agent 创建
- 同步研究流程
- SSE 流式研究流程
- 多线程任务调度
- 单任务搜索与总结
- 最终报告持久化
- note_id 提取与 task 序列化

拆分目标不是重写项目，而是让 `DeepResearchAgent` 回到“编排入口”的角色。建议逐步拆成：

| 模块 | 职责 |
|---|---|
| `services/llm_factory.py` | 根据 `Configuration` 创建主 LLM 和报告 LLM，统一处理 ollama / lmstudio / custom provider |
| `services/tool_registry_factory.py` | 创建 NoteTool、ToolRegistry，并集中管理工具注册 |
| `services/task_executor.py` | 执行单个任务：搜索、准备上下文、总结、更新任务状态 |
| `services/stream_runner.py` | 管理 SSE 队列、多线程 worker、stream_token、任务完成信号 |
| `services/report_store.py` / `report_persistence.py` | 负责最终报告写入、读取、防路径穿越和报告事件构造 |

当前已开始第一步：抽出 `services/llm_factory.py`，让 LLM 参数构造和实例创建从 `agent.py` 中独立出来。

建议后续每次只拆一个职责，并遵循：

1. 先写针对新服务的测试。
2. 确认测试因为模块或行为缺失而失败。
3. 实现最小代码让测试通过。
4. 再接入 `DeepResearchAgent`。
5. 跑完整后端测试，确认没有行为回归。

### 方向二：SSE 强类型协议

前端当前事件类型如果仍使用宽泛结构：

```ts
export interface ResearchStreamEvent {
  type: string;
  [key: string]: unknown;
}
```

后续维护成本会越来越高。建议改为联合类型：

```ts
export type ResearchStreamEvent =
  | StatusEvent
  | TodoListEvent
  | SourcesEvent
  | TaskSummaryChunkEvent
  | TaskStatusEvent
  | ToolCallEvent
  | ReportNoteEvent
  | FinalReportEvent
  | DoneEvent
  | ErrorEvent;
```

这样前端在处理 `event.type` 时可以获得类型收窄，后端也可以用 Pydantic 模型约束事件结构。

### 方向三：并发、timeout 与 fallback

当前流式执行会为每个任务启动 worker。后续建议增加：

- `MAX_CONCURRENT_TASKS`：限制最大并发任务数。
- `SEARCH_TIMEOUT_SECONDS`：搜索超时。
- `SUMMARY_TIMEOUT_SECONDS`：单任务总结超时。
- `REPORT_TIMEOUT_SECONDS`：最终报告生成超时。
- 搜索 fallback：Tavily 失败后降级 DuckDuckGo / SearXNG。
- 报告 fallback：报告模型失败时，用任务摘要生成兜底报告。

这些能力能让 Agent 从 demo 更接近稳定服务。

### 方向四：可观测性

建议为每次研究生成 `run_id`，并让所有事件都带上：

- `run_id`
- `task_id`
- `event_type`
- `step`
- `started_at`
- `finished_at`
- `duration_ms`

前端可以增加 Debug / Trace 面板，展示每个阶段耗时、搜索来源数、工具调用次数、报告 note_id 等信息。

### 方向五：Agent 评估体系

不要只靠主观感觉判断 Agent 效果。建议新增：

```text
backend/evals/
├── cases.jsonl
└── run_eval.py
```

最小评估指标：

- 是否成功生成最终报告
- 是否完成所有任务
- 是否包含 sources
- 是否包含预期章节
- 是否出现空摘要
- 总耗时是否可接受

这样后续改 prompt、换模型、改搜索策略时，可以比较优化前后的效果。

## 学习建议

初学者建议按以下顺序学习：

1. FastAPI 的 BaseModel、HTTPException、StreamingResponse。
2. Python 单元测试、pytest 和 TDD 重构节奏。
3. Agent 编排：Planner、Search、Summarizer、Reporter 的职责边界。
4. 工具调用：工具 schema、工具返回值、工具失败处理、工具调用追踪。
5. SSE 流式协议和前后端事件契约。
6. 并发控制、timeout、fallback 和可观测性。
7. Agent 评估：用固定 case 验证 prompt、模型和搜索策略是否真的变好。
8. 横向扩展：Browser Agent、Coding Agent、Multi-Agent 流水线。

### 8 周学习路线

| 周次 | 目标 | 练习 |
|---|---|---|
| 第 1 周 | 稳定测试与理解项目结构 | 跑通后端测试和前端构建，读 `main.py`、`agent.py`、`services/*` |
| 第 2 周 | 拆分 `agent.py` | 抽出 LLM factory、工具注册、任务执行服务 |
| 第 3 周 | SSE 强类型协议 | 为前后端事件定义联合类型 / Pydantic 模型 |
| 第 4 周 | 并发和 timeout | 增加最大并发、搜索超时、总结超时、报告超时 |
| 第 5 周 | 可观测性 | 增加 run_id、duration_ms、trace 面板 |
| 第 6 周 | Agent 评估 | 建立 `evals/cases.jsonl` 和基础评分脚本 |
| 第 7 周 | Deep Research 质量优化 | Query Rewriting、Source Ranking、Critic 检查 |
| 第 8 周 | 横向拓展 | 选择 Browser Agent 或 Coding Agent 做一个小 demo |

### 如果只能先做三件事

1. 从 `agent.py` 中继续拆出独立服务，但每一步都配测试。
2. 把 SSE 事件协议改成强类型。
3. 增加并发限制、timeout 和基础 trace。
