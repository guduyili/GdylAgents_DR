# Agent 初学者学习指南（基于 GdylAgents_DR）

> 面向：**几乎零基础的 Agent 学习者**  
> 目标：用本仓库当「母项目」，从概念 → 读代码 → 动手 → 扩展，建立可迁移的 Agent 工程能力。  
> 配套文档：读完本篇后，再进入 [learning.md](./learning.md) 与 [agent_learning_roadmap.md](./agent_learning_roadmap.md)。

---

## 0. 你将得到什么

学完本指南（约 4～6 周、每周 6～10 小时）后，你应当能够：

1. 用自己的话解释 **LLM / Agent / Tool / Pipeline** 的区别  
2. 画出本项目从「用户输入 topic」到「报告完成」的调用链  
3. 本地跑通前后端，并看懂 SSE 事件流  
4. 改一处 prompt / 配置 / 小功能，并用测试或手动验证结果  
5. 知道下一步该学 RAG、MCP、多 Agent 还是平台化，而不是盲目追新框架  

---

## 1. 先建立正确心智模型（第 0 周，1～2 天）

### 1.1 四个容易混的概念

| 概念 | 一句话 | 本项目中的例子 |
|------|--------|----------------|
| **LLM** | 只会「根据上下文生成文本」的模型 | 规划、总结、写报告时调用的模型 |
| **Prompt** | 给模型的说明书与约束 | `prompts.py`、Skill 中的流程说明 |
| **Tool（工具）** | 模型可调用的外部能力（搜索、写笔记等） | 搜索 API、NoteTool、可选 Browser |
| **Agent** | 「目标 + 推理/规划 + 工具 + 循环/流水线」的系统 | `DeepResearchAgent` + `services/*` |

**初学者常见误区**：

- 以为「接了 ChatGPT API」就是 Agent → 其实只是 LLM 调用  
- 以为 Agent 必须是完全自主的黑盒 → 生产系统更常见的是 **可观测、可取消、有阶段的流水线**  
- 一上来就学 LangGraph / AutoGen → 没有「母项目」锚点，概念容易飘  

### 1.2 本项目属于哪一类 Agent

GdylAgents_DR 是一个 **深度研究助手**：

```text
用户输入研究主题 (topic)
  → 规划：拆成多个子任务
  → 执行：每个任务「搜索 → 总结」（可并发）
  → 可选：事实核对 (fact_check)、报告评审 (review)
  → 产出：Markdown 研究报告 + 本地笔记
  → 全程：SSE 实时进度 + 可取消 + 可回看时间线
```

它是典型的：

- **多阶段 Pipeline Agent**（plan → search → summarize → report …）  
- **Tool-using Agent**（搜索、笔记等）  
- **Human-in-the-loop 产品**（用户可编辑计划、取消、看历史）  

不是「纯聊天机器人」。

### 1.3 技术栈最小清单（只需认识，不必先精通）

| 层 | 技术 | 你现在需要知道什么 |
|----|------|-------------------|
| 后端 | Python、FastAPI | HTTP 路由、请求/响应 |
| Agent 编排 | HelloAgents + 本仓库 `services/*` | 谁调谁、事件如何 yield |
| 流式 | SSE（Server-Sent Events） | 服务端持续推送 JSON 事件 |
| 前端 | Vue 3 + TypeScript | 订阅 SSE、按 `type` 更新 UI |
| 持久化 | SQLite + 本地笔记目录 | `run_id`、历史报告 |

---

## 2. 环境与第一次成功体验（第 1 周前半）

### 2.1 必做：跑通系统

按根目录 [README.md](../README.md) 完成：

1. 配置 `backend/.env`（至少 `LLM_*`、`SEARCH_API`）  
2. 启动后端，访问 `GET /healthz`  
3. 启动前端，完成一次「输入 topic → 看到计划 → 出报告」  

**验收标准**：

- [ ] 浏览器里能看到任务列表与进度  
- [ ] 最终有 Markdown 报告  
- [ ] 开发者工具 Network 中能看到 `/research/stream` 的 event-stream  

### 2.2 建议：用 curl 感受 SSE（比只点 UI 更有学习价值）

```bash
# 健康检查
curl http://localhost:8000/healthz

# 仅规划（不执行完整研究）
curl -X POST http://localhost:8000/research/plan \
  -H "Content-Type: application/json" \
  -d "{\"topic\": \"什么是 Agent 工程\"}"

# 完整流式研究（观察事件一行行出来）
curl -N -X POST http://localhost:8000/research/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "{\"topic\": \"什么是 Agent 工程\", \"search_api\": \"duckduckgo\"}"
```

边跑边记下你看到的 `type` 字段：`status` / `todo_list` / `sources` / `task_status` / `final_report` / `done` 等。

### 2.3 第一次读代码：只读 3 个文件（30～45 分钟）

```text
backend/src/main.py          # HTTP 入口，POST /research/stream
backend/src/agent.py         # 门面：装配依赖，委托 StreamRunner
backend/src/services/stream_runner.py  # 真正的编排心脏
```

读的时候只回答三个问题：

1. 请求从哪进来？  
2. 谁负责「规划 / 执行任务 / 写报告」？  
3. 事件是怎么被 `yield` 出去的？  

详细链路见：[topic_call_chain.md](./topic_call_chain.md)

---

## 3. 初学者核心知识地图（本项目 ↔ 通用 Agent 概念）

把下面每行当成「知识点卡片」：左边是通用概念，右边是仓库里的落点。

| 通用 Agent 概念 | 本项目落点 | 建议阅读 |
|-----------------|------------|----------|
| 任务分解 / Planning | `PlanningService`、`plan_runner.py` | [topic_call_chain.md](./topic_call_chain.md) §规划 |
| 工具调用 Tool Use | 搜索、`NoteTool`、`tool_events.py` | [tool_call_event.md](./tool_call_event.md) |
| 状态 State | `SummaryState`、`TodoItem`（`models.py`） | 源码 `models.py` |
| 编排 Orchestration | `StreamRunner` / `SyncRunner` | `stream_runner.py` |
| 流式反馈 Streaming | `stream_events.py` + 前端 `api.ts` | [project.md](./project.md) SSE 表 |
| 可观测性 Observability | Trace/Timeline、`run_store` | [run_store.md](./run_store.md) |
| 取消 / 中断 | `stop_event`、cancel API | [cancellation.md](./cancellation.md) |
| 质量闭环 | fact_check、review、evals | `fact_check_service.py`、`backend/evals/` |
| 领域知识注入 | Skill（`SKILL.md`） | `backend/skills/`、`skill_loader.py` |
| 产品形态 | 计划编辑、进度板、历史报告 | `frontend/src/components/*` |

**学习原则**：每学一个外部名词，先问——**「我项目里哪一块已经做了？差什么？」**

---

## 4. 分阶段学习路径（初学者 6 周）

> 节奏：每周 1～2 个概念 + 1 次读代码 + 1 个小动手点。  
> 不要并行开三条大线（RAG + MCP + 多 Agent 同时学容易学成「收藏夹」）。

### 阶段 0：概念与跑通（第 1 周）

| 天 | 内容 | 交付 |
|----|------|------|
| D1 | 读本文 §1～§2，跑通本地 | 截图或笔记：一次完整研究流程 |
| D2 | 读 [topic_call_chain.md](./topic_call_chain.md) | 手绘调用链（纸笔或 mermaid） |
| D3 | 读 [project.md](./project.md) 的 SSE 事件表 | 对照一次真实 SSE 日志，给每个 type 写一句话 |
| D4 | 读 `models.py` + `config.py` | 列出 5 个你认为最重要的配置项 |
| D5 | 复盘 | 用 200 字解释：什么是 Agent，本项目如何体现 |

**本周自检**：

- [ ] 能不看代码说出：`POST /research/stream` 之后大概发生了什么  
- [ ] 能区分「规划阶段」和「任务执行阶段」  

---

### 阶段 1：主链路精读（第 2 周）

**目标**：理解「编排」而不是只会点按钮。

阅读顺序（建议每天一块）：

```text
Day1  stream_runner.py     # 主编排：规划 → worker → 报告
Day2  task_executor.py     # 单任务：搜索 → 上下文 → 总结
Day3  search.py            # 搜索如何变成 context
Day4  summarizer.py + reporter.py
Day5  stream_events.py ↔ frontend types/research.ts
```

**动手（选 1）**：

1. 在配置里改 `max_concurrent_tasks`（若已有），观察日志/并发感观差异  
2. 或：给某个 `status` 消息改文案，验证前后端是否原样展示  

**本周自检**：

- [ ] 能解释：为什么要用 Queue + Worker，而不是 for 循环顺序执行  
- [ ] 能说出至少 6 种 SSE 事件类型及触发时机  

---

### 阶段 2：工具、取消与可观测（第 3 周）

| 主题 | 文档 / 代码 | 你要搞懂的问题 |
|------|-------------|----------------|
| 工具调用事件 | [tool_call_event.md](./tool_call_event.md) | LLM 如何触发 note 工具？前端如何看到？ |
| 运行时间线 | [run_store.md](./run_store.md) | `run_id` 存在哪？`GET /research/runs/{id}` 返回什么？ |
| 取消 | [cancellation.md](./cancellation.md) | 关浏览器后后端会不会继续烧 token？ |

**动手（强烈建议）**：

1. 发起一次研究，中途点「取消」  
2. 查 `GET /research/runs/{run_id}`，确认状态为 `cancelled`，且**没有**正常的 `done` 完成语义（理解「终态」）  

**本周自检**：

- [ ] 能区分「SSE 断开」与「Agent 执行停止」  
- [ ] 能指出 `tool_call` 从后端到 Timeline 的大致路径  

---

### 阶段 3：测试、配置与质量（第 4 周）

初学者最容易忽略，却最区分「玩 demo」与「做工程」的一层。

| 主题 | 位置 | 练习 |
|------|------|------|
| 单测 | `backend/tests/` | 跑通 `pytest`，挑 1 个测试读懂「它在防什么 bug」 |
| 离线评估 | `backend/evals/` | 读 `cases.jsonl`，跑一次 `run_eval`（可用 quick） |
| 流水线开关 | `RESEARCH_PIPELINE`、`research_pipeline.py` | 关掉 `review` 或 `fact_check`，观察事件变化 |
| Skill | `backend/skills/deep-research/SKILL.md` | 改 Description/Workflow 一句话，观察规划/行为是否变化 |

**本周自检**：

- [ ] 知道如何用测试验证「我改坏了没有」  
- [ ] 理解 fact_check / review 不是必须，但是「质量闸门」  

---

### 阶段 4：前端 Agent UX（第 5 周，可选但推荐）

Agent 不只是后端：用户是否信任系统，取决于 **进度是否可见、是否可纠正、是否可中断**。

建议阅读：

```text
frontend/src/services/api.ts
frontend/src/composables/useResearchWorkflow.ts
frontend/src/components/ResearchBoard.vue
frontend/src/components/TimelinePanel.vue
frontend/src/components/PlanEditor.vue
```

**动手（选 1）**：

- 在 Timeline 某类事件上加一个更友好的展示文案  
- 或：理清「用户编辑 plan 后，哪些字段会传回 `/research/stream`」  

---

### 阶段 5：选定一个「下一层」方向（第 6 周起）

当你完成阶段 0～3 的自检后，**只选一条**深挖（详见 [agent_learning_roadmap.md](./agent_learning_roadmap.md)）：

| 方向 | 适合你如果… | 本项目练手切入点 |
|------|-------------|------------------|
| **A. 记忆 / RAG** | 关心「复用历史报告、减少重复搜索」 | 历史 report 向量化 → plan 前检索 |
| **B. 工具标准化 / MCP** | 关心「工具可插拔、跨项目复用」 | 用 MCP 包装搜索，TaskExecutor 走 MCP |
| **C. 平台化运行** | 关心「关浏览器任务仍跑、多用户」 | 任务队列 + job_id 查询 |
| **D. 多 Agent 协作** | 关心「角色动态派工、辩论评审」 | Supervisor / 双评审 |
| **E. 评估与成本** | 关心「改 prompt 是否变好、token 账单」 | 扩展 evals、记 token 到 run_store |

**仓库当前优先级建议**（与 README 一致）：

1. 若你偏产品/检索：优先 **A RAG**  
2. 若你偏工程/部署：优先 **C 任务队列**  
3. 若你偏协议/生态：优先 **B MCP**  

更细的 12 周进阶与外部资源表见 [agent_learning_roadmap.md](./agent_learning_roadmap.md)。

---

## 5. 推荐阅读顺序（文档导航）

按 **从易到难** 阅读，不要一次打开全部 docs。

| 顺序 | 文档 | 适合时机 | 你收获什么 |
|:----:|------|----------|------------|
| 1 | 本文 `beginner_agent_guide.md` | 现在 | 概念 + 学习计划 |
| 2 | [README.md](../README.md) | 环境搭建 | 怎么跑起来 |
| 3 | [topic_call_chain.md](./topic_call_chain.md) | 跑通之后 | 端到端调用链 |
| 4 | [project.md](./project.md) | 想看架构图 | SSE / 工具链路图 |
| 5 | [tool_call_event.md](./tool_call_event.md) | 理解工具 | Tool Use 可观测 |
| 6 | [run_store.md](./run_store.md) | 理解持久化 | run 时间线 |
| 7 | [cancellation.md](./cancellation.md) | 理解长任务 | 取消与分布式广播 |
| 8 | [learning.md](./learning.md) | 想做具体改造 | 项目内练习与交付物 |
| 9 | [agent_learning_roadmap.md](./agent_learning_roadmap.md) | 完成基础自检后 | 生态对照与进阶方向 |

**与已有文档的分工**：

| 文档 | 定位 |
|------|------|
| **本文** | 零基础：概念、顺序、6 周入门、自检 |
| **learning.md** | 已懂主链路：具体改代码的练习清单 |
| **agent_learning_roadmap.md** | 进阶：Agent 知识全景、RAG/MCP/平台化 |

---

## 6. 代码阅读路径（初学者版）

### 第一遍：鸟瞰（约 45 分钟）

```text
main.py → agent.py → research_services_factory.py → stream_runner.py
```

目标：谁创建谁、入口在哪。

### 第二遍：一次任务如何完成（约 1 小时）

```text
task_executor.py → search.py → summarizer.py
```

目标：搜索结果如何变成 summary。

### 第三遍：契约（约 40 分钟）

```text
stream_events.py  ↔  frontend/src/types/research.ts
```

目标：前后端对「事件长什么样」的约定。

### 第四遍：可靠性（约 40 分钟）

```text
cancellation.py → run_cancellation_registry.py → stream_runner 中 stop_event
```

目标：长任务如何安全停下。

更完整的五遍路径见 [learning.md §6](./learning.md)。

---

## 7. 每周学习节奏模板（可复制）

```text
周一  读概念 / 文档 30～60 分钟（只读一个主题）
周二  打开对应源码，写「输入 / 输出 / 不变量」笔记
周三  小改动 or 读一个测试文件（2 小时内可完成）
周四  手动验证：curl / 前端 / pytest 三选一
周五  写 5～10 行复盘（可追加到本文件个人笔记区）
周末  可选：看一篇外部文章，填「本项目是否已覆盖」对照表
```

**原则**：

1. **先跑通再扩展** —— 没跑通就改架构 = 空中楼阁  
2. **先测试再重构** —— 至少能跑现有 pytest  
3. **一次只学一个概念** —— 对照本项目一个模块即可  
4. **每个概念要有交付物** —— 笔记、测试、或一次可演示的改动  

---

## 8. 初学者最小动手练习库（由易到难）

完成阶段 0～2 后，可从下表选题；更重的工程题见 [learning.md](./learning.md)。

| 难度 | 练习 | 验证方式 |
|:----:|------|----------|
| ★ | 改 `status` 文案或前端展示文案 | UI 可见变化 |
| ★ | 新增 `evals/cases.jsonl` 一条 topic | `run_eval` 能跑 |
| ★★ | 阅读并解释一个 `tests/test_*.py` | 口头讲清 fixture 在测什么 |
| ★★ | 开关 `RESEARCH_PIPELINE` 某阶段 | SSE 事件集合变化 |
| ★★ | 修改 Skill 的 Workflow 描述 | 规划质量有可观察差异 |
| ★★★ | 新增一种 SSE 事件字段并前后端对齐 | 单测 + 前端展示 |
| ★★★ | 为超时/失败路径补一个单测 | `pytest` 绿 |
| ★★★★ | 历史报告简单关键词检索（RAG 雏形） | plan 前能注入相关片段 |

---

## 9. 自检清单

### 9.1 入门毕业（建议全部勾选后再学框架）

- [ ] 本地完整跑通一次 deep 研究  
- [ ] 能画 topic → report 的调用链  
- [ ] 能列举 ≥6 种 SSE 事件  
- [ ] 能解释 Tool 与 Agent 的区别  
- [ ] 能完成一次取消并查看 run 状态  
- [ ] 会运行后端测试（至少相关子集）  

### 9.2 工程入门（勾 4 项以上可进 roadmap 阶段 B/C）

- [ ] 读懂 `StreamRunner` 主循环与 worker 关系  
- [ ] 读懂 `stream_events` 与前端类型的对应  
- [ ] 能修改配置影响行为（模式、pipeline、并发等）  
- [ ] 理解 `run_store` 存了什么、用来干什么  
- [ ] 知道 fact_check / review / Skill 各自解决什么问题  
- [ ] 能对照外部概念填「本项目 vs 新框架」表  

### 9.3 常见卡点与处理

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 规划成功但任务全 failed | 搜索 API / 网络 / Key | 先固定 `SEARCH_API=duckduckgo`，看后端日志 |
| 前端无进度 | SSE 解析、CORS、API 地址 | 用 curl `-N` 确认后端有事件 |
| 取消后仍在跑 | 未走 cancel API 或旧代码路径 | 对照 [cancellation.md](./cancellation.md) |
| 一改就全红 | 未 mock LLM/搜索 | 学习现有 tests 的 fixture 写法 |
| 学了框架不会用 | 没有锚点 | 回到本文 §3 能力表，逐项对照 |

---

## 10. 外部资源（初学者精简清单）

只保留与本项目 **强相关** 的入口；完整表见 roadmap。

| 资源类型 | 学什么 | 怎么用 |
|----------|--------|--------|
| OpenAI / 任意厂商 Function Calling 文档 | 工具调用协议 | 对照本项目「搜索/笔记如何被 Agent 使用」 |
| SSE / EventSource 简介 | 流式协议 | 对照 `api.ts` 的 buffer 切分 |
| FastAPI StreamingResponse | 后端流式 | 对照 `main.py` |
| LangGraph **概念页**（状态图） | 编排抽象 | 只对照 `StreamRunner` 阶段，不急着迁移 |
| MCP Quickstart | 工具标准化 | 完成阶段 0～3 后再看 |
| DeepEval / RAGAS 入门 | 评估 | 扩展 `backend/evals/` |

**刻意少做的事**：

- 同时开 3 个 Agent 框架教程  
- 不读本仓库代码直接复制 LangChain 模板  
- 只追新模型发布、不关心取消/评估/可观测  

---

## 11. 文档索引与后续沉淀建议

本仓库已有文档分层：

```text
docs/
  beginner_agent_guide.md   ← 你在这里（零基础）
  topic_call_chain.md       ← 端到端链路
  project.md                ← 架构图
  tool_call_event.md        ← 工具事件
  run_store.md              ← 运行存储
  cancellation.md           ← 取消
  learning.md               ← 项目内动手清单
  agent_learning_roadmap.md ← 进阶全景
```

**建议你个人持续沉淀的方式**（可选，不强制提交）：

1. 每周在 `docs/notes/` 或自己的笔记库写「本周对照表：概念 ↔ 文件 ↔ 验证命令」  
2. 每完成一个动手点，在 PR 或笔记中写：触发条件 / 数据契约 / 失败模式 / 如何验证  
3. 进阶题目优先回写 `learning.md` 风格的「最小可验证交付」  

---

## 12. 一句话总结

> **不要从框架学 Agent，要从「一个能跑的深度研究系统」学 Agent。**  
> GdylAgents_DR 已经具备规划、工具、并发、流式、取消、评估、Skill 等完整拼图。  
> 作为初学者：先跑通、再顺藤摸瓜读主链路、再补测试与取消等工程能力，最后只选一条进阶线（RAG / MCP / 队列 / 多 Agent）深挖——用本仓库把「听说过」变成「改得动、讲得清、验得到」。

---

## 附录 A：关键路径速查

| 路径 | 说明 |
|------|------|
| `backend/src/main.py` | HTTP / SSE 入口 |
| `backend/src/agent.py` | Agent 门面 |
| `backend/src/services/stream_runner.py` | 流式主编排 |
| `backend/src/services/task_executor.py` | 单任务执行 |
| `backend/src/services/stream_events.py` | 事件契约 |
| `backend/src/models.py` | 核心状态模型 |
| `backend/src/config.py` | 配置 |
| `backend/skills/` | Skill 知识包 |
| `backend/evals/` | 离线评估 |
| `backend/tests/` | 单测 |
| `frontend/src/services/api.ts` | SSE 客户端 |
| `frontend/src/composables/useResearchWorkflow.ts` | 研究工作流状态 |

## 附录 B：6 周进度打卡表（可打印）

| 周 | 主题 | 完成日 | 备注 |
|----|------|--------|------|
| 1 | 概念 + 跑通 + 调用链草图 | | |
| 2 | StreamRunner / TaskExecutor 精读 | | |
| 3 | 工具事件 + 取消 + run_store | | |
| 4 | 测试 + pipeline + Skill | | |
| 5 | 前端 UX 或补漏洞周 | | |
| 6 | 选定进阶方向并做最小 demo | | |
