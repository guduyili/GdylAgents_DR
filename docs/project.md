# GdylAgents_DR 架构文档

## 前后端完整调用链路

```mermaid
sequenceDiagram
    participant User as "用户浏览器"
    participant AppVue as "App.vue<br/>handleSubmit()"
    participant ApiTS as "api.ts<br/>runResearchStream()"
    participant MainPy as "main.py<br/>POST /research/stream"
    participant AgentPy as "agent.py<br/>DeepResearchAgent"
    participant Planner as "services/planner.py<br/>PlanningService"
    participant Search as "services/search.py<br/>dispatch_search()"
    participant Summarizer as "services/summarizer.py<br/>SummarizationService"
    participant Reporter as "services/reporter.py<br/>ReportingService"
    participant NoteTool as "hello_agents<br/>NoteTool"
    participant LLM as "LLM API<br/>(gpt-5.4)"

    User->>AppVue: 输入主题 + 点击"开始研究"
    AppVue->>ApiTS: runResearchStream({topic, search_api})
    ApiTS->>MainPy: POST /research/stream (fetch + text/event-stream)

    Note over MainPy: _build_config(payload)<br/>构建 Configuration

    MainPy->>AgentPy: agent.run_stream(topic)
    Note over AgentPy: 启动后台线程执行研究<br/>主线程通过 Queue 接收事件

    rect rgb(230, 240, 255)
        Note over AgentPy,LLM: 阶段1: 规划
        AgentPy->>Planner: plan_todo_list(state)
        Planner->>LLM: ToolAwareSimpleAgent.run(todo_planner_instructions)
        LLM-->>Planner: JSON 任务列表 [{title, intent, query}...]
        Planner-->>AgentPy: List[TodoItem]
        AgentPy-->>MainPy: SSE: {type: "todo_list", todo_list: [...]}
        MainPy-->>ApiTS: data: {...}\n\n
        ApiTS-->>AppVue: onEvent("todo_list")
        AppVue-->>User: 显示任务规划列表
    end

    rect rgb(230, 255, 230)
        Note over AgentPy,NoteTool: 阶段2: 逐任务执行 (并发多线程)
        loop 每个 TodoItem
            AgentPy->>Search: dispatch_search(task.query, config)
            Search-->>AgentPy: 搜索结果 + sources_summary
            AgentPy-->>MainPy: SSE: {type: "sources", task_id, backend}
            MainPy-->>AppVue: 显示来源信息

            AgentPy->>Summarizer: summarize_task(state, task, context)
            Summarizer->>LLM: run(task_summarizer_instructions + context)
            LLM-->>Summarizer: 包含 [TOOL_CALL:note:...] 的输出流

            opt 启用 Notes
                Summarizer->>NoteTool: create/update note
                NoteTool-->>Summarizer: note_id
            end

            Summarizer-->>AgentPy: summary 文本 + note_id
            AgentPy-->>MainPy: SSE: {type: "task_status", task_id, status, summary}
            MainPy-->>AppVue: 显示任务摘要
        end
    end

    rect rgb(255, 240, 220)
        Note over AgentPy,LLM: 阶段3: 生成最终报告
        AgentPy->>Reporter: generate_report(state)
        Reporter->>LLM: ToolAwareSimpleAgent.run(report_writer_instructions)<br/>使用 gpt-5.4-mini (REPORT_MODEL_ID)
        LLM-->>Reporter: Markdown 报告全文
        Reporter-->>AgentPy: report 字符串

        opt 启用 Notes
            AgentPy->>NoteTool: create conclusion note
            NoteTool-->>AgentPy: conclusion_note_id<br/>写入 notes_index.json
        end

        AgentPy-->>MainPy: SSE: {type: "final_report", report, note_id}
        MainPy-->>ApiTS: data: {type: "final_report"}\n\n
        ApiTS-->>AppVue: onEvent("final_report")
        AppVue-->>User: renderMd(report) 渲染 Markdown 报告

        AgentPy-->>MainPy: SSE: {type: "done"}
        MainPy-->>ApiTS: data: {type: "done"}\n\n
        ApiTS-->>AppVue: return（流结束）
    end

    opt 用户点击"历史记录"
        User->>AppVue: 点击历史按钮
        AppVue->>MainPy: GET /notes/reports
        MainPy-->>AppVue: [{id, title, created_at}...]
        User->>AppVue: 点击某条记录
        AppVue->>MainPy: GET /notes/reports/{note_id}
        MainPy-->>AppVue: {id, title, content}
        AppVue-->>User: renderMd(content) 显示历史报告
    end
```

---

## 流式输出启动机制

```mermaid
flowchart TD
    A["前端 handleSubmit()<br/>App.vue"] -->|"POST /research/stream<br/>fetch + Accept: text/event-stream"| B

    subgraph FastAPI ["FastAPI 进程 (单线程 uvicorn)"]
        B["main.py<br/>stream_research(payload)<br/>@app.post('/research/stream')"]
        B --> C["event_iterator() 生成器函数<br/>for event in agent.run_stream(topic):<br/>    yield 'data: {JSON}\\n\\n'"]
        C --> D["StreamingResponse(event_iterator())<br/>media_type='text/event-stream'"]
    end

    subgraph AgentRunStream ["agent.py run_stream() - Python generator"]
        E["yield status: '初始化研究流程'"]
        F["planner.plan_todo_list() → 任务列表"]
        G["yield todo_list: [tasks...]"]
        H["event_queue = Queue()"]
        I["为每个 task 启动 Thread(worker)"]
        J["主线程: while finished < total:<br/>    event = event_queue.get()<br/>    yield event"]
        K["reporter.generate_report()"]
        L["yield final_report + done"]

        E --> F --> G --> H --> I --> J --> K --> L
    end

    subgraph Workers ["后台线程 (每个任务独立)"]
        W1["worker(task_1)<br/>dispatch_search()<br/>summarize_task()<br/>→ enqueue(events)"]
        W2["worker(task_2)<br/>dispatch_search()<br/>summarize_task()<br/>→ enqueue(events)"]
        W3["worker(task_N)..."]
    end

    D --> AgentRunStream
    I -->|"Thread.start()"| W1
    I -->|"Thread.start()"| W2
    I -->|"Thread.start()"| W3
    W1 -->|"event_queue.put()"| J
    W2 -->|"event_queue.put()"| J
    W3 -->|"event_queue.put()"| J

    subgraph Frontend ["前端 SSE 接收"]
        R["api.ts: reader.read() 循环<br/>buffer 拼接 + '\\n\\n' 切割"]
        S["JSON.parse(dataPayload)<br/>onEvent(event)"]
        T["App.vue 响应不同 type:<br/>todo_list / task_status<br/>sources / final_report / done"]
    end

    D -->|"HTTP chunked transfer<br/>每 yield 一条立即刷新到网络"| R
    R --> S --> T
```

---

## 工具调用事件记录链路

```mermaid
sequenceDiagram
    participant HA as "hello_agents<br/>ToolAwareSimpleAgent"
    participant Tracker as "ToolCallTracker<br/>.record(payload)"
    participant Logger as "logging<br/>INFO 日志"
    participant Sink as "event_sink 回调<br/>(流式模式)"
    participant Queue as "event_queue<br/>(run_stream 主线程)"

    Note over HA: LLM 输出包含 [TOOL_CALL:note:{...}]
    HA->>HA: 解析 TOOL_CALL 指令
    HA->>HA: 调用 NoteTool.run(params)
    Note over HA: NoteTool 写文件，返回结果字符串<br/>"✅ 笔记创建成功\nID: note_xxx"

    HA->>Tracker: tool_call_listener(payload)<br/>payload = {agent_name, tool_name,<br/>raw_parameters, parsed_parameters, result}

    Note over Tracker: record() 执行：
    Tracker->>Tracker: _infer_task_id(parsed_parameters)<br/>优先 task_id 字段 → tags → title
    Tracker->>Tracker: _extract_note_id(result)<br/>正则提取 "ID: note_xxx"
    Tracker->>Tracker: 构建 ToolCallEvent<br/>写入 self._events[]

    Tracker->>Logger: logger.info("工具调用已记录:<br/>agent=研究规划专家 tool=note<br/>task_id=1 note_id=note_xxx ...")

    alt 流式模式 (run_stream)
        Tracker->>Sink: sink(_build_payload(event))<br/>即 agent.py 中的 tool_event_sink()
        Sink->>Queue: event_queue.put({type:'tool_call',...})
        Queue-->>Queue: run_stream 主线程 yield 推送给前端
    else 同步模式 (run)
        Note over Tracker: 事件暂存在 _events[]
        Tracker-->>Tracker: drain(state) 时批量提取<br/>并将 note_id 写回 TodoItem.note_id
    end
```

---

## SSE 事件类型说明

| 事件 type | 触发时机 | 关键字段 |
|:--|:--|:--|
| `status` | 流程各阶段开始/切换 | `message`, `step` |
| `todo_list` | 规划完成 | `tasks[]` |
| `sources` | 单个任务搜索完成 | `task_id`, `backend`, `latest_sources` |
| `task_summary_chunk` | 总结流式输出 | `task_id`, `chunk`, `stream_token` |
| `task_status` | 任务状态变更 | `task_id`, `status`, `summary`, `note_id` |
| `tool_call` | 工具调用完成 | `agent`, `tool`, `parameters`, `note_id` |
| `final_report` | 报告生成完成 | `report`, `note_id` |
| `done` | 全流程结束 | — |
| `error` | 异常发生 | `detail` |
