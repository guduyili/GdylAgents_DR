# GdylAgents_DR 深度学习与扩展路线

本文基于**当前仓库实际代码**整理，面向已经理解项目主链路的 agent learner，提供由浅入深的学习、动手和扩展方向。

> **还是 Agent 零基础？** 请先读 [beginner_agent_guide.md](./beginner_agent_guide.md)（概念心智、6 周入门、文档阅读顺序）。  
> **想从整个 Agent 项目视角规划后续学习？** 请参阅 [agent_learning_roadmap.md](./agent_learning_roadmap.md)（能力地图、学习方法论、RAG/MCP/多 Agent/平台化等方向与 12 周路径）。

---

## 1. 项目当前定位与架构快照

GdylAgents_DR 是一个深度研究助手，核心链路：

```
用户输入 topic → PlanRunner 规划任务 → StreamRunner 并发执行 → TaskExecutor(搜索+总结) → FinalReportGenerator 报告 → SSE 逐事件推送前端
```

关键模块职责：

| 模块 | 职责 | 文件 |
|:--|:--|:--|
| HTTP 入口 | FastAPI 路由、请求序列化 | `main.py` |
| 编排门面 | 只做依赖装配和入口转发 | `agent.py` |
| 依赖装配 | 集中创建全部服务 | `services/research_services_factory.py` |
| 规划入口 | 仅生成任务列表 | `services/plan_runner.py` |
| 流式编排 | SSE 事件流、并发 worker 管理 | `services/stream_runner.py` |
| 同步编排 | 非 SSE 的完整流程 | `services/sync_runner.py` |
| 单任务执行 | 搜索 → 上下文整理 → 总结 | `services/task_executor.py` |
| SSE 事件契约 | Pydantic 强类型 + 校验 | `services/stream_events.py` |
| 工具追踪 | 线程安全事件累积 + drain/sink | `services/tool_events.py` |
| 工具事件桥 | 同步/流式消费策略切换 | `services/tool_event_bridge.py` |
| 运行持久化 | 内存/SQLite 两种 backend | `services/research_run_store.py` |
| 报告持久化 | 写 NoteTool + 标题去重 | `services/report_persistence.py` |
| LLM 工厂 | 统一创建 LLM 实例 | `services/llm_factory.py` |
| Agent 工厂 | 创建规划/总结/报告 Agent | `services/agent_factory.py` |
| 搜索调度 | DuckDuckGo / Tavily / SearXNG | `services/search.py` |
| 任务序列化 | TodoItem → 前端 payload | `services/task_serializer.py` |

前端核心类型系统：

| 类型 | 用途 | 文件 |
|:--|:--|:--|
| `ResearchStreamEvent` | SSE 事件联合类型 (10 种) | `types/research.ts` |
| `TimelineEventView` | 时间线事件视图模型 | `types/view.ts` |
| `api.ts` | SSE 流式接收 + REST 请求 | `services/api.ts` |
| 6 个组件 | Trace、Timeline、Board、Form、PlanEditor、History | `components/*.vue` |

---

## 2. 已完成的架构演进（你现在站在的位置）

如果你已经理解了以下内容，说明你已经具备了"基础 learner"水平：

- `DeepResearchAgent` 是薄门面，真正逻辑在 `services/*`
- `StreamRunner` 通过 `Queue + Thread` 管理并发任务，`__task_done__` 是内部哨兵
- `ToolEventBridge` 在流式模式下走 sink 直推，同步模式下走 drain 批量提取
- `stream_events.py` 的 `normalize_stream_event()` 对每个公开事件做 Pydantic 校验
- `research_run_store.py` 支持内存和 SQLite 两种存储，run_id 贯穿全链路
- 前端 `research.ts` 的 TypeScript 联合类型与后端 Pydantic 模型一一对齐
- `TracePanel` 和 `TimelinePanel` 已经落地，不再是 TODO

**下一步的目标**：从"能读懂项目"升级到"能稳定扩展项目"。

---

## 3. 后续学习与扩展方向（按优先级排序）

### 方向一：可靠性工程 — 让 Agent 从"能跑"到"稳定跑"

#### 3.1 并发任务数限制

当前代码在 `stream_runner.py:229` 为每个 task 直接启 Thread：

```python
for task in state.todo_items:
    thread = Thread(target=worker, args=(task, step), daemon=True)
    threads.append(thread)
    thread.start()
```

如果用户规划了 20 个任务，瞬间启动 20 个线程，会打爆搜索 API 和 LLM 并发。

**练习**：
1. 在 `Configuration` 中新增 `max_concurrent_tasks: int = Field(default=4)`
2. 修改 `StreamRunner._run_task_workers()` 使用 `ThreadPoolExecutor(max_workers=...)` 替代手动 Thread
3. 确保所有任务完成后再进入报告生成阶段
4. 写单测：模拟 10 个任务、max_workers=3，验证同时运行的线程不超过 3

#### 3.2 搜索与总结超时

当前 `TaskExecutor.execute()` 无超时保护，搜索挂住会阻塞整个 worker。

**练习**：
1. 在 `Configuration` 新增 `search_timeout_seconds: int = Field(default=60)` 和 `summary_timeout_seconds: int = Field(default=120)`
2. 在 `TaskExecutor.execute()` 中用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=...)` 包裹搜索和总结调用
3. 超时时 yield `task_status: failed` 事件并跳到下一个任务
4. 写单测验证超时逻辑

#### 3.3 搜索后端 fallback

当前 `search.py` 只在 DuckDuckGo 模式下做了多 backend 重试（lite → api → html），其他模式异常直接抛出。

**练习**：
1. 在 `Configuration` 新增 `search_fallback_chain: list[SearchAPI] = Field(default_factory=lambda: [...])`
2. 修改 `dispatch_search()`：主后端失败时依次尝试 fallback chain
3. 在 `SourcesEvent` 中新增 `search_backend` 字段标识实际使用的后端
4. 写单测：mock 主后端 raise，验证 fallback 生效

---

### 方向二：SSE 协议收紧 — 让前后端契约滴水不漏

#### 3.4 后端事件强制 Pydantic 校验

当前 `normalize_stream_event()` 已经对公开事件做 Pydantic 校验，但 `TaskExecutor` 中仍有部分事件是手动拼 dict 的，比如：

```python
# task_executor.py:164-176
yield {
    "type": "sources",
    "task_id": task.id,
    "latest_sources": task.sources_summary,
    ...
    "source": "task_executor",
}
```

**练习**：
1. 审查 `task_executor.py`、`stream_runner.py` 中所有 `yield {` 和 `enqueue(` 调用
2. 确认每个字典的字段都对应 `stream_events.py` 中某个 Pydantic 模型的字段
3. 写一个 smoke test：构造所有 10 种事件类型，通过 Pydantic 校验不报错
4. 在 CI 中加入 `pytest tests/test_stream_observability.py` 确保不漂移

#### 3.5 前端事件消费增加 schema 校验

当前前端 `api.ts` 直接 `JSON.parse(dataPayload) as ResearchStreamEvent`，没有运行时校验。

**练习**：
1. 安装 `zod`，为每种事件类型定义 zod schema
2. 在 `runResearchStream` 的 `onEvent` 之前做 `schema.safeParse()`
3. 校验失败时 `console.warn` 而不是静默丢弃，方便调试
4. 对比后端 Pydantic 模型，确保两者的字段和类型完全一致

#### 3.6 `task_run_id` 和 `stream_token` 在前端的使用验证

当前后端已稳定下发 `task_run_id` 和 `stream_token`，但前端的 `ResearchBoard.vue` / `App.vue` 是否真的用它们做了任务关联？

**练习**：
1. 搜索前端代码中 `task_run_id` 和 `stream_token` 的所有引用
2. 确认 `task_summary_chunk` 事件是靠 `task_id + stream_token` 关联到正确任务的
3. 如果发现只靠 `task_id` 关联，补齐 `stream_token` 的使用
4. 写一个 E2E 场景：3 个并发任务，不同任务交替推送 chunk，验证前端不会串任务

---

### 方向三：可观测性增强 — 让 Agent 的黑盒变透明

#### 3.7 阶段耗时统计与回放

当前 `stream_runner.py` 已经在 `sources`、`task_status`、`final_report`、`done` 事件中记录了 `duration_ms`，但缺少"阶段"维度的聚合。

**练习**：
1. 新增 `PhaseDurationEvent(BaseStreamEvent)` 事件类型，在 `todo_list` 和 `final_report` 之间插入阶段里程碑：
   ```python
   class PhaseDurationEvent(BaseStreamEvent):
       type: Literal["phase_duration"] = "phase_duration"
       phase: Literal["planning", "search", "summary", "report"] 
       duration_ms: int
   ```
2. 在 `StreamRunner._run_flow()` 的 `yield from self._emit_final_report()` 之后、`done` 之前，遍历 `state.todo_items` 计算 search/summary 各阶段的累计耗时
3. 前端 `TimelinePanel` 中增加"阶段耗时"行，展示搜索总耗时 / 总结总耗时 / 报告耗时 / 全流程耗时
4. `/research/runs/{run_id}` 接口返回的 snapshot 中增加 `phase_durations` 字段

#### 3.8 Trace 面板增加 pruner 和导出

当前 `TracePanel.vue` 只展示 run_id、latestTaskRunId、latestStreamToken 和总耗时。

**练习**：
1. 新增"按 task_id 过滤"下拉，选中后只显示该任务的事件
2. 新增"导出 JSON"按钮：将 `/research/runs/{run_id}` 返回的完整 snapshot 下载为 `.json`
3. 新增"重放按钮"：读取导出的 JSON，在 Timeline 中重新渲染事件序列
4. 对后端 `ResearchRunStore.get_run()` 的返回结构做性能检查（事件数 > 1000 时是否需要分页）

#### 3.9 工具调用事件增加 `input_preview` 和 `output_preview`

当前 `ToolCallEvent` 包含完整的 `parameters` 和 `result`，大搜索結果会让前端渲染卡顿。

**练习**：
1. 在 `stream_events.py` 的 `ToolCallEvent` 中新增 `input_preview: str | None = None` 和 `output_preview: str | None = None`
2. 在 `tool_events.py` 的 `_build_payload()` 中，对 `parameters` 和 `result` 截取前 200 字符作为 preview
3. 前端 `TimelineEventItem` 默认只展示 preview，点击"展开"时才显示完整内容
4. 在 `/research/runs/{run_id}` 中同时提供 preview 和 full 版本

---

### 方向四：能力边界扩展 — 从"深度研究"到"多模式研究"

#### 3.10 轻量研究模式

当前流程固定经过 规划 → 并发搜索总结 → 报告，如果用户只想快速浏览一个话题，等待时间过长。

**练习**：
1. 在 `Configuration` 新增 `research_mode: Literal["deep", "quick"] = Field(default="deep")`
2. quick 模式跳过规划阶段，直接用 topic 做搜索，一次搜索 + 一次总结即出结果
3. 前端 `ResearchForm.vue` 新增模式切换下拉
4. `ResearchRequest` 新增 `mode` 字段，`main.py` 的 `/research/stream` 根据 mode 选择不同 runner

#### 3.11 新增搜索后端适配器

当前 `search.py` 的 `dispatch_search()` 是 if/elif 分发。如果要加 Perplexity 或内部知识库，需要改核心代码。

**练习**：
1. 定义 `SearchBackend` Protocol：
   ```python
   class SearchBackend(Protocol):
       def search(self, query: str, *, max_results: int) -> SearchOutcome: ...
   ```
2. 实现 `DuckDuckGoBackend`、`TavilyBackend`、`SearXNGBackend`
3. 在 `research_services_factory.py` 中根据 `config.search_api` 注入对应的 backend
4. `TaskExecutor` 接受 `SearchBackend` 依赖，不再直接调用 `dispatch_search()`

#### 3.12 报告后处理 — 校验与增强

当前 `ReportingService` 生成报告后直接写入 NoteTool，没有质量校验。

**练习**：
1. 新增 `services/report_post_processor.py`，包含：
   - 引用校验：检查 `## 参考` 章节是否与搜索来源对应
   - 标题清洗：去除重复标题、过深层级
   - 字数统计：如果报告过短（< 500 字）触发补充摘要
2. 在 `FinalReportGenerator.generate_report()` 后调用 post processor
3. 将处理结果作为 `report_meta` 事件推送到前端

---

### 方向五：测试体系 — 让每次改动都有信心

#### 3.13 关键路径单测补齐

当前测试目录 `backend/tests/` 已有 `test_stream_observability.py` 和 `test_stream_runner.py`，但还有很多核心路径没有覆盖。

**优先补测的模块和方法**：

| 模块 | 方法 | 测试要点 |
|:--|:--|:--|
| `task_executor.py` | `execute()` 同步模式 | 搜索结果为空时 → skipped；搜索成功 → completed |
| `task_executor.py` | `execute()` 流式模式 | yield 事件序列：tool_call → sources → task_summary_chunk → task_status |
| `stream_events.py` | `normalize_stream_event()` | 所有不带 run_id/timestamp 的 dict 都被自动补齐 |
| `stream_events.py` | `__task_done__` | 哨兵事件不做 Pydantic 校验 |
| `research_run_store.py` | `SQLiteResearchRunStore` | start → record → complete → get_run 全流程 |
| `tool_event_bridge.py` | `drain()` 流式/同步切换 | sink 模式下 drain 返回空；非 sink 模式下返回新事件 |
| `report_persistence.py` | `persist_final_report()` | note_id 为 None 时不写笔记；note_id 存在时做 update |
| `task_serializer.py` | `serialize_task()` | task_run_id 为 None 时不出现在 payload 中 |

**练习**：
1. 为上表每个测试要点写一个 `test_xxx.py`
2. 使用 fixture mock 掉 LLM 调用和搜索调用，只测编排逻辑
3. 在 CI 中确保 `pytest -q` 全绿

#### 3.14 Agent 评估体系

当前没有固定 topic 的回归测试，每次改 prompt 或模型都不知道是变好还是变差。

**练习**：
1. 新增 `backend/evals/` 目录：
   ```
   backend/evals/
   ├── cases.jsonl       # 评估用例：{"topic": "...", "expected_sections": [...]}
   └── run_eval.py       # 跑一次完整研究，检查结果是否满足最低标准
   ```
2. 最小评估指标：
   - 是否成功生成最终报告（非空）
   - 是否完成所有任务（无 failed 状态）
   - 报告是否包含 sources 段
   - 总耗时是否在阈值内（如 < 300s）
3. 每个 PR 都跑一次 `python -m evals.run_eval --quick`

---

### 方向六：前端继续拆分 — 从"能用"到"好用"

#### 3.15 App.vue 继续瘦身后抽取 composable

当前 `App.vue` 虽然已经拆出 6 个子组件，但状态管理仍集中在主文件中（SSE 处理、任务状态更新、事件分发等）。

**练习**：
1. 抽取 `composables/useResearchWorkflow.ts`：
   - 封装 `runResearchStream` 调用和事件分发逻辑
   - 管理 `plannedTasks`、`taskStates`、`sources`、`toolCalls`、`report` 等响应式状态
2. 抽取 `composables/useHistoryReports.ts`：
   - 封装 `listReports()` 和 `getReport()` 调用
   - 管理 `reports` 和 `selectedReport` 状态
3. `App.vue` 只保留组件组装和 composable 调用，不直接处理 SSE 事件

#### 3.16 ResearchBoard 增加任务级别操作

当前 `ResearchBoard.vue` 只展示任务状态，不能对单个任务做操作。

**练习**：
1. 新增"重新执行"按钮：前端触发 `POST /research/stream`，payload 中 `todo_items` 只包含要重跑的任务
2. 新增"跳过"按钮：前端更新本地状态，后续 `task_summary_chunk` 事件忽略该任务
3. 注意：重新执行需要后端支持"部分任务重跑"接口（当前是全量跑），这属于后端扩展

#### 3.17 报告查看增强

当前报告只展示 Markdown 内容，缺少交互能力。

**练习**：
1. 增加目录导航：解析 Markdown 标题生成侧边栏目录
2. 增加"复制为纯文本"和"下载 .md"按钮
3. 增加来源链接可点击：解析 `[text](url)` 格式，渲染为可点击链接

---

### 方向七：横向扩展 — 从单一 Agent 到多 Agent 协作

#### 3.18 引入评审模式

当前报告生成是单次调用 `ReportingService.generate_report()`，没有交叉验证。

**练习**：
1. 新增 `services/review_service.py`：
   ```python
   class ReviewService:
       def review(self, state: SummaryState, report: str) -> ReviewResult:
           """调用评审 Agent 审查报告完整性和准确性"""
   ```
2. 在 `StreamRunner._emit_final_report()` 中，报告生成后调用 review
3. 新增 `review_result` 事件类型，推送到前端显示评审结果
4. 如果评审发现缺失章节，可触发补充搜索（进阶扩展）

#### 3.19 Browser Agent 原型

当前搜索只走搜索 API，无法获取需要 JS 渲染的页面内容。

**练习**：
1. 新增 `services/browser_fetch.py`，使用 Playwright 或 `hello_agents` 的 BrowserTool
2. 在 `Configuration` 新增 `enable_browser_fetch: bool = False`
3. 当 `fetch_full_page=True` 且搜索结果的页面无法通过纯 HTTP 获取时，使用 browser fetch
4. 注意：browser fetch 需要运行时安装 Chromium，属于运维层面的扩展

#### 3.20 Multi-Agent Pipeline

当前是 研究规划专家 → 任务总结专家 → 报告撰写专家 的固定流水线。

**练习**：
1. 将 `AgentFactory` 扩展为可注册自定义 Agent 的 registry
2. 新增 Skill Agent：能够按需加载 SKILL.md 指引来完成任务
3. 新增 Fact-Check Agent：在总结后自动交叉验证关键事实
4. 将 `ResearchServices` 中的固定 Agent 替换为可插拔的 pipeline 配置

---

## 4. 具体动手路线图（8 周计划）

| 周次 | 方向 | 具体任务 | 交付物 |
|:--|:--|:--|:--|
| 第 1 周 | 可靠性 | 并发限制 + 搜索超时 | `Configuration.max_concurrent_tasks` + ThreadPoolExecutor 替换 |
| 第 2 周 | 可靠性 | 搜索 fallback + 任务级超时 | `dispatch_search` fallback chain + `summary_timeout_seconds` |
| 第 3 周 | 协议 | SSE 事件全量 Pydantic 校验 | 补齐 `task_executor.py` 中的事件字段 + smoke test |
| 第 4 周 | 协议 | 前端 zod schema + task_run_id 关联验证 | 前端运行时校验 + E2E 场景 |
| 第 5 周 | 可观测性 | PhaseDurationEvent + Timeline 耗时行 | 后端新事件类型 + 前端阶段耗时展示 |
| 第 6 周 | 可观测性 | Trace 过滤 + 导出 + 工具通话预览 | Trace 过滤器 + JSON 导出按钮 |
| 第 7 周 | 能力 | 轻量研究模式 + 搜索后端适配器 Protocol | `ResearchMode` 配置 + `SearchBackend` Protocol |
| 第 8 周 | 横向 | 评审模式原型 | `ReviewService` + `review_result` 事件 |

---

## 5. 当你只能做三件事

1. **吃透 `stream_runner.py` 和 `task_executor.py` 的并发模型** — `Queue + Thread + __task_done__` 哨兵、`ToolEventBridge` 的 sink/drain 双模式，是整个项目最精巧也最容易出错的部位。
2. **让所有 SSE 事件都通过 `normalize_stream_event()` 校验** — 这是前后端契约的"焊点"，任何一个字段漂移都会导致前端静默丢失数据。
3. **给 `research_run_store`、`tool_events`、`report_persistence` 补单测** — 这三个模块是持久化层，没有测试覆盖意味着每次重构都是在盲飞。

---

## 6. 代码阅读路径（按理解深度）

### 第一遍：概览（30 分钟）

```
main.py → agent.py → research_services_factory.py
```

理解"谁创建谁、谁依赖谁"。

### 第二遍：主链路（1 小时）

```
stream_runner.py → task_executor.py → search.py → summarizer.py → final_report_generator.py → report_persistence.py
```

沿 SSE 事件流走一遍，关注每个 yield 和 enqueue。

### 第三遍：契约（30 分钟）

```
stream_events.py ↔ types/research.ts
```

逐字段对比 10 种事件类型的 Pydantic 模型和 TypeScript 接口。

### 第四遍：可观测性（30 分钟）

```
tool_events.py → tool_event_bridge.py → TracePanel.vue → TimelinePanel.vue
```

理解工具调用从 LLM 回调到前端渲染的完整路径。

### 第五遍：持久化（30 分钟）

```
research_run_store.py → report_persistence.py → notes.py → main.py (reports API)
```

理解运行记录如何存、如何查、报告如何写、如何读。

---

## 7. 取消链路（已实现，建议优先阅读）

长任务 Agent 必须区分 **HTTP 流结束** 与 **后台执行结束**。本项目已实现：

- `stop_event` 贯穿 `main.py` → `StreamRunner` → `TaskExecutor`
- `POST /research/runs/{run_id}/cancel` 显式取消
- `run_store.status = cancelled` 与 `cancelled` SSE 事件

**学习文档**：[cancellation.md](./cancellation.md)（含 3 天练习、验证命令、多进程扩展思路）

---

## 8. 每个扩展方向的"最小可验证交付"

| 方向 | 最小交付 | 如何验证 |
|:--|:--|:--|
| 并发限制 | `max_concurrent_tasks=2` + ThreadPoolExecutor | 规划 5 个任务，日志确认只有 2 个线程同时执行 |
| 搜索超时 | `search_timeout_seconds=10` + mock 挂住搜索 | 超时后前端收到 `task_status: failed` 事件 |
| 搜索 fallback | 主后端异常 → 自动切 Tavily/DuckDuckGo | 前端 `sources` 事件包含 `backend` 字段 |
| Pydantic 校验 | 所有事件都经过 `normalize_stream_event()` | 运行 `pytest tests/test_stream_observability.py` 全绿 |
| PhaseDurationEvent | 后端 yield 新事件 + 前端显示耗时 | 前端 Timeline 出现"搜索: 3.2s / 总结: 8.1s"的行 |
| 轻量模式 | `POST /research/stream` body 带 `mode: quick` | 前端选择 quick 后只做一次搜索总结 |
| 评审模式 | `ReviewService` + `review_result` 事件 | 报告下方显示"评审意见: 缺少参考来源"的卡片 |
| 取消链路 | `stop_event` + cancel API | 取消后无 `done`，`GET /research/runs/{id}` 为 `cancelled` |

---

## 9. 一句话总结

如果你是一个已经理解现有项目的基础 learner，下一步不是重写，而是按 **主链路加固 → 协议收紧 → 可观测性补齐 → 可靠性工程 → 新能力适配器** 的顺序，每一步都带测试和验证，逐步从一个"能跑的 demo"升级为"可以放心扩展的工程"。