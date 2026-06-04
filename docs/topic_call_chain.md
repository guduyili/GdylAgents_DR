# 用户输入 topic 后的完整调用链

本文记录当前项目中，用户在前端输入研究主题（topic）后，从浏览器到后端 Agent，再到搜索、总结、报告生成和 SSE 推送的完整调用链。

目标读者：刚开始学习 Agent 工程的开发者。

阅读建议：先把这篇文档当成“地图”，再沿着每个文件逐个阅读源码。

---

## 1. 一句话总览

用户输入 topic 后，前端通过 `/research/stream` 发起 SSE 请求；后端 `main.py` 创建 `DeepResearchAgent`；`DeepResearchAgent` 委托 `StreamRunner` 编排完整流程：规划任务、并发执行每个任务、搜索资料、流式总结、记录工具调用、生成最终报告、保存报告，并把过程事件持续推送给前端。

核心链路：

```text
前端 topic
  -> POST /research/stream
  -> main.py
  -> DeepResearchAgent.run_stream()
  -> StreamRunner.run()
  -> PlanningService.plan_todo_list()
  -> TaskExecutor.execute() x N
  -> dispatch_search()
  -> prepare_research_context()
  -> SummarizationService.stream_task_summary()
  -> ToolCallTracker / NoteTool
  -> ReportingService.generate_report()
  -> ReportPersistence
  -> SSE final_report / done
```

---

## 2. 关键文件职责

| 文件 | 职责 |
|---|---|
| `frontend/src/App.vue` | 接收用户输入、展示计划、进度、摘要和最终报告 |
| `frontend/src/services/api.ts` | 封装 `/research/plan` 和 `/research/stream` 请求，解析 SSE 数据 |
| `backend/src/main.py` | FastAPI HTTP 入口，负责接收请求、构造配置、返回 StreamingResponse |
| `backend/src/agent.py` | `DeepResearchAgent` 编排入口，创建 LLM、工具、服务，并把运行委托给服务 |
| `backend/src/services/planner.py` | 把 topic 拆成 TodoItem 任务列表 |
| `backend/src/services/stream_runner.py` | 流式运行主编排：SSE 事件、线程、队列、最终报告事件 |
| `backend/src/services/task_executor.py` | 单任务执行：搜索、上下文整理、总结、任务状态事件 |
| `backend/src/services/search.py` | 搜索后端分发和研究上下文整理 |
| `backend/src/services/summarizer.py` | 调用任务总结 Agent，支持同步和流式总结 |
| `backend/src/services/reporter.py` | 汇总所有任务结果，生成最终 Markdown 报告 |
| `backend/src/services/report_persistence.py` | 保存最终报告到 NoteTool / notes index，并构造 report_note 事件 |
| `backend/src/services/tool_events.py` | 收集工具调用事件，推断 task_id / note_id，并推送给前端 |
| `backend/src/models.py` | `SummaryState`、`TodoItem` 等核心数据结构 |
| `backend/src/config.py` | 从环境变量和请求参数构造运行配置 |

---

## 3. 前端入口：用户输入 topic

典型用户路径：

1. 用户在页面输入研究主题。
2. 前端先调用 `/research/plan` 生成任务规划。
3. 用户确认或编辑任务。
4. 前端调用 `/research/stream` 开始执行。
5. 前端持续读取 SSE 事件并更新 UI。

从工程角度看，前端最重要的是两件事：

- 把 topic 和任务列表传给后端。
- 按事件类型分发后端返回的数据。

常见事件包括：

```text
status
  流程状态提示，例如“初始化研究流程”。

todo_list
  后端生成或确认后的任务列表。

task_status
  单个任务的状态变化，例如 in_progress、completed、skipped、failed。

sources
  某个任务搜索完成后的来源摘要和原始上下文。

task_summary_chunk
  单个任务总结的流式文本片段。

tool_call
  Agent 调用工具后的可观测事件，例如创建 note。

report_note
  最终报告被保存后的笔记事件。

final_report
  最终 Markdown 报告。

done
  整个流程结束。

error
  异常事件。
```

---

## 4. 后端 HTTP 入口：main.py

`backend/src/main.py` 是后端的 HTTP 边界。

当请求进入 `/research/stream` 时，主流程通常是：

```text
stream_research(payload)
  -> _build_config(payload)
  -> DeepResearchAgent(config)
  -> event_iterator()
  -> for event in agent.run_stream(topic, todo_items=...)
  -> yield SSE 文本: data: {...}\n\n
  -> StreamingResponse(event_iterator(), media_type="text/event-stream")
```

这里有两个关键点：

1. `main.py` 不应该承载 Agent 业务逻辑。
   它主要负责 HTTP 请求、配置构造、异常转换和 SSE 包装。

2. `agent.run_stream()` 产出的是 Python dict。
   `main.py` 再把 dict 序列化成 SSE 文本格式。

---

## 5. Agent 初始化：DeepResearchAgent.__init__()

`DeepResearchAgent` 是总协调器，但经过拆分后，它不应该继续变成巨型类。

当前初始化阶段做了这些事：

```text
DeepResearchAgent.__init__()
  -> Configuration.from_env() 或使用请求传入 config
  -> create_llm(config)
  -> 创建 NoteTool（如果 enable_notes=True）
  -> 创建 ToolRegistry 并注册 NoteTool
  -> 创建 ToolCallTracker
  -> 创建 ReportPersistence
  -> 创建三个 ToolAwareSimpleAgent
       - 研究规划专家 todo_agent
       - 报告撰写专家 report_agent
       - 任务总结专家 summarizer_factory
  -> 创建业务服务
       - PlanningService
       - SummarizationService
       - ReportingService
       - TaskExecutor
       - StreamRunner
```

理解这里的重点：

- `DeepResearchAgent` 负责“装配依赖”。
- `PlanningService`、`TaskExecutor`、`StreamRunner` 等服务负责具体业务。
- `ToolCallTracker` 被注入到 `ToolAwareSimpleAgent`，用于记录工具调用。

---

## 6. 流式主流程：DeepResearchAgent.run_stream()

当前 `run_stream()` 已经很薄：

```text
DeepResearchAgent.run_stream(topic, todo_items=None)
  -> yield from self.stream_runner.run(topic, todo_items=todo_items)
```

这说明职责已经从 `agent.py` 向 `StreamRunner` 下沉。

这是一个好的重构方向：

- `agent.py` 保留为编排入口。
- `stream_runner.py` 管理流式执行细节。
- `task_executor.py` 管理单任务执行细节。

---

## 7. StreamRunner.run()：完整 SSE 编排

`StreamRunner.run()` 是用户输入 topic 后的核心运行链路。

```text
StreamRunner.run(topic, todo_items=None)
  -> state = SummaryState(research_topic=topic)
  -> yield status: 初始化研究流程

  -> 如果前端传入 todo_items
       state.todo_items = todo_items
     否则
       state.todo_items = planner.plan_todo_list(state)
       yield planner 阶段产生的 tool_call 事件

  -> 如果没有规划结果
       创建 fallback task

  -> 给每个 task 分配 stream_token 和 step
  -> yield todo_list

  -> yield from _run_task_workers(state, channel_map)
  -> yield from _emit_final_report(state)
```

这里有三个学习重点：

1. `SummaryState` 是贯穿全流程的共享状态。
2. `todo_items` 是任务执行的骨架。
3. SSE 事件不是一次性返回，而是每完成一步就 yield 一个事件。

---

## 8. 任务并发：StreamRunner._run_task_workers()

`_run_task_workers()` 负责并发执行多个任务，并把 worker 线程中的事件转发到主生成器。

核心结构：

```text
_run_task_workers(state, channel_map)
  -> event_queue = Queue()
  -> 定义 enqueue(event)
       - 补 task_id
       - 补 step
       - 补 stream_token
       - event_queue.put(payload)

  -> 定义 tool_event_sink(event)
       - enqueue(event)

  -> set_tool_event_sink(tool_event_sink)

  -> 为每个 TodoItem 启动一个 Thread(worker)

  -> worker(task, step)
       - enqueue task_status: in_progress
       - for event in task_executor.execute(...): enqueue(event)
       - 如果异常，enqueue task_status: failed
       - finally enqueue 内部事件 __task_done__

  -> 主线程循环 event_queue.get()
       - 如果是 __task_done__，计数加一，不推给前端
       - 否则 yield event

  -> finally
       - set_tool_event_sink(None)
       - join 所有线程
```

为什么需要 Queue？

因为任务在多个线程里执行，但 FastAPI 的 SSE 响应只能由主生成器持续 yield。Queue 是 worker 线程和主生成器之间的桥。

---

## 9. 单任务执行：TaskExecutor.execute()

每个任务的实际执行在 `TaskExecutor.execute()` 中完成。

完整链路：

```text
TaskExecutor.execute(state, task, emit_stream=True, step=N)
  -> task.status = "in_progress"

  -> dispatch_search(task.query, config, state.research_loop_count)
       返回 search_result, notices, answer_text, backend

  -> drain tool events

  -> 如果有 notices
       yield status 事件

  -> 如果没有搜索结果
       task.status = "skipped"
       yield task_status: skipped
       return

  -> prepare_research_context(search_result, answer_text, config)
       返回 sources_summary, context

  -> 更新 task.sources_summary
  -> 加锁更新共享 state
       state.web_research_results.append(context)
       state.sources_gathered.append(sources_summary)
       state.research_loop_count += 1

  -> 流式模式
       yield from _run_streaming_summary(...)

  -> 同步模式
       summarizer.summarize_task(...)
       task.status = "completed"
```

对初学者来说，`TaskExecutor` 是最适合重点阅读和练习测试的模块。它有明确输入、明确输出，也最容易写单元测试。

---

## 10. 搜索链路：dispatch_search() 和 prepare_research_context()

搜索阶段主要做两件事：

1. 根据配置选择搜索后端。
2. 把搜索结果整理成后续 LLM 可读的上下文。

概念链路：

```text
task.query
  -> dispatch_search(query, config, loop_count)
  -> search_result / answer_text / backend / notices
  -> prepare_research_context(search_result, answer_text, config)
  -> sources_summary
  -> context
```

`context` 会交给总结 Agent 使用。

`sources_summary` 会被保存到 `task.sources_summary`，也会通过 `sources` 事件推给前端。

---

## 11. 总结链路：SummarizationService

流式模式下，单任务总结由 `SummarizationService.stream_task_summary()` 完成。

```text
TaskExecutor._run_streaming_summary(...)
  -> yield sources 事件
  -> summarizer.stream_task_summary(state, task, context)
       返回 summary_stream, summary_getter

  -> for chunk in summary_stream
       yield task_summary_chunk
       drain tool events

  -> summary_getter()
       获取完整 summary_text

  -> task.summary = summary_text
  -> task.status = "completed"
  -> yield task_status: completed
```

这里有一个很重要的 Agent 工程模式：

- `summary_stream` 用于实时显示。
- `summary_getter()` 用于在流结束后拿到完整文本。
- chunk 事件面向 UI，完整 summary 面向后续报告生成。

---

## 12. 工具调用链路：ToolCallTracker 和 NoteTool

项目使用 HelloAgents 的 `ToolAwareSimpleAgent`。

当 LLM 输出工具调用指令并执行工具后，框架会调用注册的 listener：

```text
ToolAwareSimpleAgent
  -> NoteTool.run(...)
  -> tool_call_listener(payload)
  -> ToolCallTracker.record(payload)
```

`ToolCallTracker.record()` 做几件事：

```text
record(payload)
  -> 读取 agent_name / tool_name / parameters / result
  -> 推断 task_id
  -> 提取 note_id
  -> 构造 ToolCallEvent
  -> 追加到内部事件列表
  -> 如果当前设置了 event_sink
       立即把 tool_call 事件推给 StreamRunner 的 Queue
```

同步模式和流式模式的区别：

```text
同步模式:
  工具事件先暂存在 tracker 内部
  后续通过 drain(state) 批量取出

流式模式:
  StreamRunner 设置 event_sink
  record() 之后立即 enqueue
  前端可以实时看到 tool_call 事件
```

这个机制的价值是“可观测性”：你不仅知道最终报告是什么，也能看到 Agent 过程中调用了哪些工具、写了哪些 note。

---

## 13. 最终报告链路：ReportingService 和 ReportPersistence

所有任务完成后，进入最终报告阶段：

```text
StreamRunner._emit_final_report(state)
  -> final_step = len(state.todo_items) + 1

  -> reporting.generate_report(state)
       使用所有 task.summary、sources、topic 生成 Markdown 报告

  -> 如果报告生成失败
       使用任务摘要拼接兜底报告

  -> drain tool events

  -> state.structured_report = report
  -> state.running_summary = report

  -> persist_final_report(state, report)
       保存最终报告 note
       更新 notes_index.json
       返回 report_note 事件

  -> yield report_note（如果有）
  -> yield final_report
  -> yield done
```

对初学者来说，这里可以学到两个工程习惯：

1. 关键路径要有 fallback。
   报告模型失败时，至少还能用任务摘要生成兜底报告。

2. 最终产物要持久化。
   用户不应该只能在当前页面看到报告，刷新后也应该能从历史记录读取。

---

## 14. 数据结构在链路中的流动

### SummaryState

`SummaryState` 是一次研究运行的全局状态，典型字段包括：

```text
research_topic
  用户输入的 topic。

todo_items
  规划出的任务列表。

web_research_results
  每个任务整理后的上下文。

sources_gathered
  每个任务的来源摘要。

research_loop_count
  当前搜索/研究轮次计数。

running_summary / structured_report
  最终报告文本。

report_note_id / report_note_path
  最终报告持久化后的 note 信息。
```

### TodoItem

`TodoItem` 是单个研究任务，典型字段包括：

```text
id
  任务编号。

title
  任务标题。

intent
  任务意图。

query
  用于搜索的查询词。

status
  pending / in_progress / completed / skipped / failed。

summary
  单任务总结。

sources_summary
  搜索来源摘要。

note_id / note_path
  如果任务过程中写入 note，则记录对应信息。

stream_token
  前端区分任务流的 token。
```

---

## 15. 按事件视角看完整时序

下面按前端收到事件的顺序理解：

```text
1. status
   初始化研究流程

2. tool_call（可选）
   规划阶段如果调用工具，会出现工具事件

3. todo_list
   返回任务列表

4. task_status: in_progress
   某个任务开始执行

5. status（可选）
   搜索 notices，例如后端降级或提示

6. sources
   某个任务搜索完成，返回来源和上下文

7. task_summary_chunk x 多次
   单任务总结流式输出

8. tool_call（可选）
   总结过程中如果写 note，会实时出现

9. task_status: completed / skipped / failed
   单任务结束

10. report_note（可选）
    最终报告保存成功

11. final_report
    返回最终 Markdown 报告全文

12. done
    整个流程结束
```

注意：多个任务是并发执行的，所以第 4 到第 9 步可能会交错出现。前端应该依赖 `task_id` 和 `stream_token` 来归属事件，而不是假设事件严格按任务顺序出现。

---

## 16. 当前架构的优点

当前拆分后，项目已经具备几个比较好的工程特征：

1. `DeepResearchAgent` 变薄了。
   它主要负责装配依赖和暴露入口。

2. 单任务执行可测试。
   `TaskExecutor` 可以用假的 search_dispatcher、context_preparer、summarizer 做单元测试。

3. 流式运行可测试。
   `StreamRunner` 可以用假的 planner、task_executor、reporting 验证事件顺序。

4. 工具调用具备可观测性。
   `ToolCallTracker` 让工具调用不再是黑盒。

5. 最终报告有兜底策略。
   报告生成失败时不会直接中断整个用户体验。

---

## 17. 当前仍值得优化的点

建议按优先级处理：

### 17.1 抽出工具注册工厂

当前 `DeepResearchAgent.__init__()` 仍然直接创建 `NoteTool` 和 `ToolRegistry`。

建议新增：

```text
backend/src/services/tool_registry_factory.py
```

职责：

```text
create_note_tool(config)
create_tool_registry(note_tool)
```

这样 `agent.py` 会更像依赖装配层。

### 17.2 抽出 Agent 工厂

当前 `DeepResearchAgent` 仍然直接创建 `ToolAwareSimpleAgent`。

建议新增：

```text
backend/src/services/agent_factory.py
```

职责：

```text
create_tool_aware_agent(...)
create_todo_agent(...)
create_report_agent(...)
create_summarizer_factory(...)
```

这样可以统一管理模型覆盖、工具注册、listener 注入等逻辑。

### 17.3 强类型 SSE 协议

当前事件是 dict，容易出现字段名不一致。

建议后端增加 Pydantic 事件模型，前端增加 TypeScript union types。

推荐类型：

```text
StatusEvent
TodoListEvent
SourcesEvent
TaskSummaryChunkEvent
TaskStatusEvent
ToolCallEvent
ReportNoteEvent
FinalReportEvent
DoneEvent
ErrorEvent
```

### 17.4 增加 timeout 和并发限制

当前每个任务都会启动线程。后续建议增加：

```text
MAX_CONCURRENT_TASKS
SEARCH_TIMEOUT_SECONDS
SUMMARY_TIMEOUT_SECONDS
REPORT_TIMEOUT_SECONDS
```

并增加搜索 fallback 和报告 fallback 的测试。

### 17.5 增加 run_id 和 trace

建议每次研究生成一个 `run_id`，所有事件都带上：

```text
run_id
task_id
event_type
step
started_at
finished_at
duration_ms
```

这样前端可以做 Debug 面板，后端也更容易定位问题。

### 17.6 建立 Agent eval

建议新增：

```text
backend/evals/cases.jsonl
backend/evals/run_eval.py
```

最小指标：

```text
是否生成 final_report
是否所有任务都有终态
是否包含 sources
是否出现空摘要
是否有异常事件
总耗时
```

---

## 18. 给 Agent 初学者的源码阅读顺序

建议不要从 LLM prompt 开始读，而是按调用链从外到内读：

1. `README.md`
2. `docs/topic_call_chain.md`
3. `backend/src/main.py`
4. `backend/src/models.py`
5. `backend/src/agent.py`
6. `backend/src/services/stream_runner.py`
7. `backend/src/services/task_executor.py`
8. `backend/src/services/search.py`
9. `backend/src/services/summarizer.py`
10. `backend/src/services/reporter.py`
11. `backend/src/services/report_persistence.py`
12. `backend/src/services/tool_events.py`
13. `frontend/src/services/api.ts`
14. `frontend/src/App.vue`

每读一个模块，都问自己三个问题：

```text
它的输入是什么？
它的输出是什么？
它是否有副作用？例如网络请求、文件写入、状态修改、线程、队列。
```

---

## 19. 推荐练习任务

适合初学者从小到大练习：

1. 给 `TaskExecutor` 新增一个“搜索异常时 task_status=failed”的测试。
2. 给 `StreamRunner` 新增一个“多个任务事件交错时仍带正确 stream_token”的测试。
3. 为所有 SSE 事件定义后端 Pydantic 模型。
4. 在前端把 `ResearchStreamEvent` 改成 TypeScript 联合类型。
5. 增加 `MAX_CONCURRENT_TASKS` 配置。
6. 给每个事件补 `run_id`。
7. 新增一个最小 eval 脚本，验证固定 topic 是否能生成报告。
8. 抽出 `tool_registry_factory.py`。
9. 抽出 `agent_factory.py`。
10. 给报告持久化增加更多异常场景测试。

---

## 20. 总结

这条调用链可以被理解为四层：

```text
HTTP 层：main.py
  负责请求、响应、SSE 包装。

编排层：DeepResearchAgent / StreamRunner
  负责把规划、任务执行、报告生成串起来。

能力层：PlanningService / TaskExecutor / SummarizationService / ReportingService
  负责具体 Agent 能力。

基础设施层：search / ToolCallTracker / NoteTool / ReportPersistence / config / models
  负责外部搜索、工具调用观测、文件持久化和数据结构。
```

后续优化时，尽量保持这个分层：不要把 HTTP、线程、搜索、LLM、文件写入全部塞回一个函数里。每次只拆一个职责，先写测试，再改实现，最后跑完整测试。
