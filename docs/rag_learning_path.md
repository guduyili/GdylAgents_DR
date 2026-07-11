# RAG 进阶学习与实现路径（GdylAgents_DR）

> 你已选择 **RAG（Retrieval-Augmented Generation）** 作为进阶主线。  
> 本文把「通用 RAG 知识」锚到本仓库的 **历史研究报告**，按周交付、可验证。  
> 前置：完成 [beginner_agent_guide.md](./beginner_agent_guide.md) 入门自检；建议读过 [topic_call_chain.md](./topic_call_chain.md)。

---

## 1. 为什么本项目适合用 RAG 进阶

### 1.1 痛点（没有 RAG 时）

| 现象 | 原因 |
|------|------|
| 相近 topic 重复全网搜索 | 只靠实时 search，不用本地历史 |
| 规划任务「从零瞎拆」 | Planner 看不到过去报告结论 |
| 报告互相矛盾、重复劳动 | 无「相似研究」对照 |
| Token 与时间成本高 | 每次 deep 模式都走完整流水线 |

### 1.2 本项目的天然语料

系统已经在本地持久化 **conclusion 研究报告**：

```text
NOTES_WORKSPACE/          # 如 ./data/notes 或 ./note
  notes_index.json        # 笔记元数据（type=conclusion 等）
  {note_id}.md            # 报告 Markdown 正文
```

相关代码：

| 模块 | 职责 |
|------|------|
| `report_persistence.py` | 写最终报告到 NoteTool |
| `main.py` `/notes/reports*` | 列表与读取历史报告 |
| `planner.py` | 规划阶段（**RAG 注入点 A**） |
| `summarizer.py` / `search.py` | 总结上下文（**RAG 注入点 B，进阶**） |
| `backend/evals/` | 对比「有/无 RAG」效果（**验证点**） |

### 1.3 目标形态（你最终要建成的）

```text
用户 topic
    │
    ▼
┌───────────────────┐
│ Report RAG 检索    │  ← 历史报告 chunk 库（先关键词，后向量）
│ top-k 相关片段     │
└─────────┬─────────┘
          │ 注入 prior_research_context
          ▼
    PlanningService（更好的任务拆解）
          │
          ▼
    搜索 / 总结 / 报告（可选：总结阶段二次检索）
          │
          ▼
    新报告落盘 → 增量写入 RAG 语料
```

**一句话**：RAG 不是替换搜索，而是 **「先查本地记忆，再决定怎么搜、怎么写」**。

---

## 2. RAG 最小知识清单（1～2 天）

先弄清 5 个词，再写代码：

| 概念 | 含义 | 本项目对应 |
|------|------|------------|
| **Corpus（语料）** | 可检索的文档集合 | 历史 `conclusion` 报告 |
| **Chunk（分块）** | 长文切成可检索片段 | 按字符/标题切 Markdown |
| **Embed / Index** | 把 chunk 变成可相似度比较的表示 | Phase1=关键词索引；Phase2=向量索引 |
| **Retrieve** | 按 query 取 top-k | `topic` 或 task.query |
| **Augment** | 把检索结果塞进 Prompt | `prior_research_context` |

推荐外部精读（只读这些即可，避免并行三套框架）：

1. 任意一篇「Naive RAG 流水线」图文（Load → Chunk → Index → Retrieve → Generate）  
2. 一篇「Chunk 策略」短文（按标题 vs 固定长度 vs 重叠）  
3. （Phase2 再读）OpenAI Embeddings 或本地 `sentence-transformers` 入门  

**对照学习表（建议手写填一次）**：

| 维度 | 通用 RAG | 本项目 Phase1 | 本项目 Phase2 |
|------|----------|---------------|---------------|
| 语料 | PDF/网页 | 本地报告 md | 同左 |
| 表示 | embedding | 词项重叠 / 字符 bigram | 向量 + 余弦 |
| 存储 | Vector DB | 内存 / JSON | Chroma/FAISS/sqlite-vss |
| 生成侧 | 回答问题 | **规划 Agent** 优先 | 规划 + 总结双注入 |
| 评估 | 命中率/ faithfulness | 规划质量 + eval | LLM-as-Judge |

---

## 3. 分阶段实现路线（推荐 4 周）

> 原则：**先可检索、再可注入、再向量化、再评估**。  
> 仓库内已提供 **Phase1 骨架**（见 §5），你按周加深即可。

### 第 1 周：吃透语料与「无向量」检索

**目标**：不引入 embedding 依赖，也能按 topic 找回相关历史段落。

| 任务 | 做法 | 验收 |
|------|------|------|
| 读代码 | `report_persistence.py` + `/notes/reports` | 能说明报告如何落盘 |
| 跑 Phase1 | 配置 `ENABLE_REPORT_RAG=true`，有历史报告时规划 | 日志/SSE 出现「历史报告检索」类 status |
| 读实现 | `services/report_rag.py` | 能解释 chunk 与 score 规则 |
| 补语料 | 先手动跑 2～3 次不同但相关的研究 | `NOTES_WORKSPACE` 下有多份 conclusion |
| 写笔记 | 记录 3 个 topic 的 top-k 命中是否「看起来相关」 | 个人对照表 |

**动手练习**：

1. 改 `rag_chunk_size` / `rag_top_k`，观察命中变化  
2. 为 `tokenize()` 增加停用词过滤（的/了/和/研究…）  
3. 写单测：固定 2 篇 md，query 只应命中其中一篇  

### 第 2 周：注入规划 Prompt + 可观测

**目标**：检索结果真正影响任务拆解，而不是「查了但没用」。

| 任务 | 做法 | 验收 |
|------|------|------|
| Prompt | `prompts.py` 中 `prior_research_context` | 有/无历史时规划任务差异可感知 |
| 注入点 | `PlanningService.plan_todo_list` | 单元测试 mock 上下文 |
| 事件 | `status` 或专用 `rag_hits` 事件 | 前端 Timeline 可见「引用了哪些 note」 |
| API | `POST /research/plan` 同样走检索 | curl plan 时行为一致 |

**动手练习**：

1. 新增 SSE 类型 `rag_context`（后端 Pydantic + 前端类型对齐）  
2. 在 `PlanEditor` 旁展示「参考历史：note_xxx 标题」  
3. Prompt 增加约束：「优先覆盖历史未解决的问题，避免重复已有结论」  

### 第 3 周：向量检索（真正的 Embedding RAG）

**目标**：语义相似（「大模型 Agent」≈「LLM 智能体工程」）也能命中。

推荐技术选型（二选一，不要全上）：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A. OpenAI-compatible embeddings** | 与现有 `LLM_BASE_URL` 一致 | 依赖外网/Key |
| **B. 本地 sentence-transformers + FAISS/Chroma** | 可离线 | 体积大、部署重 |

建议实现接口（保持 Phase1 可替换）：

```python
class ReportRetriever(Protocol):
    def retrieve(self, query: str, *, top_k: int) -> list[ReportChunk]: ...
    def upsert_report(self, note_id: str, title: str, content: str) -> None: ...
```

| 任务 | 验收 |
|------|------|
| `EmbeddingReportRetriever` | 同义 topic 比纯关键词更稳 |
| 索引落盘 | 重启服务后无需全量重算（或可 rebuild 命令） |
| 报告落盘后 `upsert` | 新报告下次研究立即可检索 |
| 配置开关 | `RAG_BACKEND=lexical|embedding` |

**动手练习**：

1. CLI：`python -m services.report_rag_cli rebuild` 全量重建索引  
2. 对比表：10 个 query × lexical vs embedding 的 top-1 是否合理  
3. 可选：hybrid = `0.4 * lexical + 0.6 * vector`  

### 第 4 周：评估、总结侧注入与产品化

**目标**：证明 RAG「有用」，并避免拖垮主链路。

| 任务 | 做法 | 验收 |
|------|------|------|
| Eval | `evals/cases.jsonl` 增加「有历史语料」场景 | `run_eval` 对比开关 |
| 总结侧 | task 执行前对 `task.query` 二次检索 | 可选配置 `RAG_INJECT_STAGES=plan,summarize` |
| 降级 | 检索失败不影响主流程 | try/except + 空上下文 |
| 成本 | 限制 max_context_chars | Prompt 不爆窗 |
| 文档 | 更新本文件「已完成」勾选 | 可演示 demo |

**最小评估指标（建议）**：

1. 检索命中：人工标注 top-3 是否相关（P@3）  
2. 规划质量：任务是否减少与历史重复  
3. 效率：有 RAG 时 deep 模式总耗时 / 搜索次数是否下降（可选）  
4. 回归：关闭 RAG 时行为与旧版一致  

---

## 4. 架构设计（实现时遵守）

### 4.1 模块边界

```text
services/report_rag.py          # 语料加载、分块、检索、格式化（核心）
config.py                       # ENABLE_REPORT_RAG / RAG_* 配置
planner.py / plan_runner.py     # 消费 prior_context
stream_runner.py / sync_runner  # 规划前触发 retrieve + status
report_persistence.py           # （Phase2+）落盘后 upsert
main.py                         # 可选 GET /notes/rag/search?q=
```

**不要做的事**：

- 把向量库逻辑写进 `main.py`  
- 检索失败时让整个 research 500  
- 把整篇历史报告无截断塞进 prompt  

### 4.2 注入策略

| 阶段 | 注入内容 | 目的 |
|------|----------|------|
| **plan（优先）** | top-k 片段摘要 + 来源 note_id | 更好拆任务、避开重复 |
| summarize（可选） | 与 task 相关的历史要点 | 交叉验证、补全 |
| report（可选） | 「历史结论对照」小节 | 报告写「与既往研究关系」 |

### 4.3 安全与质量

- 只读 `NOTES_WORKSPACE` 内路径，防路径穿越（对齐 `get_report`）  
- 对检索片段做长度截断与敏感信息最小化  
- Prompt 写明：**历史片段可能过时，以新搜索为准**  
- 记录 `note_id` + score，便于审计（进 run_store）  

---

## 5. 仓库已提供的 Phase1 骨架

| 项 | 说明 |
|----|------|
| 模块 | `backend/src/services/report_rag.py` |
| 后端 | **Lexical（关键词 / CJK bigram 重叠）**，零额外依赖 |
| 开关 | `ENABLE_REPORT_RAG=true`（默认 `false`，不影响现有行为） |
| 注入 | 规划 Prompt 字段 `prior_research_context` |
| 测试 | `backend/tests/test_report_rag.py` |

### 5.1 环境变量

```bash
# backend/.env
ENABLE_REPORT_RAG=true
RAG_TOP_K=4
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=80
RAG_MAX_CONTEXT_CHARS=3000
# 与笔记目录一致
NOTES_WORKSPACE=./data/notes
```

### 5.2 快速验证

```bash
# 1) 先积累至少 1 份历史报告（跑一次 deep 研究，或手工放 conclusion md）
# 2) 开启 RAG 后调用 plan
curl -X POST http://localhost:8000/research/plan \
  -H "Content-Type: application/json" \
  -d "{\"topic\": \"与历史报告相近的主题\"}"

# 3) 单测
cd backend
uv run --extra dev python -m pytest tests/test_report_rag.py -q
```

### 5.3 你从骨架出发的扩展清单

- [ ] Phase1：停用词、标题加权、仅 `type=conclusion`  
- [ ] Phase1.5：`GET /notes/rag/search` 调试接口  
- [ ] Phase2：`RAG_BACKEND=embedding` + upsert 索引  
- [ ] Phase2：报告落盘自动增量索引  
- [ ] Phase3：`rag_context` SSE + 前端展示  
- [ ] Phase4：eval 有/无 RAG 对比 + 文档复盘  

---

## 6. 每周节奏模板（RAG 专用）

```text
周一  读 1 个 RAG 概念（chunk / embedding / eval 轮换）
周二  对照本仓库模块，更新「对照表」
周三  实现最小改动（ retriever / prompt / 测试 三选一主攻）
周四  用 2 个真实 topic 手工验命中
周五  写 10 行复盘：命中了什么、错在哪、下周改什么
```

**完成定义（Definition of Done）**：每一周结束时，必须有：

1. 可运行的代码或配置变化  
2. 至少 1 个自动化测试或可重复的 curl 步骤  
3. 笔记中 3 条「成功/失败案例」  

---

## 7. 自检清单

### 7.1 Phase1 毕业

- [ ] 能解释 chunk 边界如何影响检索  
- [ ] 能在关闭/开启 RAG 时对比规划结果  
- [ ] 检索异常时研究流程仍成功  
- [ ] `pytest tests/test_report_rag.py` 通过  

### 7.2 Phase2 毕业

- [ ] 同义 topic 向量检索明显优于纯关键词  
- [ ] 索引可重建、可增量  
- [ ] 新报告无需重启即可被检索（或有明确 rebuild 流程）  

### 7.3 Phase4 毕业

- [ ] eval 有量化或半量化对比  
- [ ] 前端或 API 可展示引用的历史 note  
- [ ] 文档写明降级策略与配置  

---

## 8. 与其他文档的关系

| 文档 | 关系 |
|------|------|
| [beginner_agent_guide.md](./beginner_agent_guide.md) | 入门；§阶段5 指向本路径 |
| [agent_learning_roadmap.md](./agent_learning_roadmap.md) | §4.3 记忆与 RAG 总览；细节以本文为准 |
| [learning.md](./learning.md) | 通用工程练习；RAG 专题练本文件 |
| [run_store.md](./run_store.md) | 运行时间线；可把 rag hits 记入 timeline |

---

## 9. 一句话总结

> 在 GdylAgents_DR 上做 RAG，不是另起一个 ChatPDF，而是让 **深度研究 Agent 拥有「读过自己写过的报告」的记忆**：先用无依赖的关键词检索跑通闭环，再换成向量检索，最后用 eval 证明变好——始终锚在 `NOTES_WORKSPACE`、规划注入与可观测上。
