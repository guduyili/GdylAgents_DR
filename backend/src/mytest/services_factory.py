"""研究服务装配工厂：集中创建 DeepResearchAgent 需要的全部服务。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool

from config import Configuration
from services.agent_factory import AgentFactory
from services.final_report_generator import FinalReportGenerator
from services.llm_factory import create_llm
from services.plan_runner import PlanRunner
from services.planner import PlanningService
from services.report_persistence import ReportPersistence
from services.reporter import ReportingService
from services.research_run_store import InMemoryResearchRunStore, ResearchRunStore, SQLiteResearchRunStore
from services.stream_runner import StreamRunner
from services.summarizer import SummarizationService
from services.sync_runner import SyncRunner
from services.task_executor import TaskExecutor
from services.task_serializer import serialize_task
from services.tool_event_bridge import ToolEventBridge
from services.tool_events import ToolCallTracker
from services.tool_registry_factory import create_tooling

    我已阅读 G:\Learning\GdylAgents_DR，也就是 WSL 下的：

    /mnt/g/Learning/GdylAgents_DR

    重点看了：

    - README.md
    - docs/project.md
    - docs/learning.md
    - docs/topic_call_chain.md
    - docs/tool_call_event.md
    - docs/run_store.md
    - backend/src/main.py
    - backend/src/agent.py
    - backend/src/services/research_services_factory.py
    - backend/src/services/stream_runner.py
    - backend/src/services/task_executor.py
    - backend/src/services/search.py
    - backend/src/config.py
    - backend/src/models.py
    - frontend/src/App.vue
    - frontend/src/components/ResearchBoard.vue
    - frontend/src/services/api.ts
    - frontend/src/types/research.ts
    - 部分后端测试

    我也做了验证：

    - frontend 构建成功：
      npm run build
      结果：vue-tsc --noEmit && vite build 成功，产物生成在 frontend/dist。
    - backend 测试没跑通，原因不是代码失败，而是当前 WSL 环境缺少 uv，并且 python3 -m venv 失败：
      uv: command not found
      ensurepip is not available，需要安装 python3.14-venv 或改用项目可用的 uv 环境。

    整体判断：

    这个项目已经不是早期 demo 了。docs 里提到的很多重构方向已经实际推进了：agent.py 已经很薄，LLM factory、agent_factory、tool_registry_factory、stream_runner、task_executor、report_persistence、run_store 等都已经抽出来了。后续重点不应再泛泛地说“拆 agent.py”，而应该进入“协议稳定、运行可靠性、评估闭环、部署卫生”的阶段。

    下面是我建议的后续优化路线，按优先级排序。

    1. 第一优先级：工程卫生与仓库清理

    当前 git status 显示大量运行产物/本地文件处于 modified 状态，尤其是：

    - backend/src/note/note_*.md 大量笔记产物
    - frontend/dist 构建产物
    - frontend/.env.local
    - 各类 lock / config / src 测试文件变动
    - .gitignore 本身也处于修改状态

    这会严重影响后续开发判断，因为每次改代码都混在运行产物里。

    建议立即做：

    1. 明确哪些是源码，哪些是运行数据。
       运行数据建议迁移到：
       backend/data/notes
       backend/data/research_runs.sqlite3

    2. notes_workspace 默认值不要继续是：
       ./note

       建议改为：
       ./data/notes

       当前 main.py 的历史接口仍然硬编码：
       Path(file).parent / "note" / "notes_index.json"

       这和 config.notes_workspace / ReportPersistence 的配置化方向不一致。建议把 notes 读取也统一走配置或 ReportPersistence/ReportStore。

    3. .gitignore 应覆盖：
       backend/src/note/
       backend/data/
       frontend/dist/
       frontend/.env.local
       .pytest_cache/
       pycache/
       *.pyc
       .venv/
       node_modules/

    4. 把已提交或已跟踪的运行产物从 git 索引移除：
       git rm --cached backend/src/note/*.md
       git rm --cached backend/src/note/notes_index.json
       git rm --cached -r frontend/dist

       注意：只从索引移除，不一定删除本地文件。

    为什么这是第一优先级：
    否则你后续做任何重构、测试、提交，diff 都会被运行产物污染，无法判断真实改动。

    2. 第二优先级：补齐后端可重复测试环境

    README 推荐：

    cd backend
    uv run --extra dev python -m pytest -q

    但当前机器上 uv 不存在。python3 -m venv 也因为 ensurepip 缺失失败。

    建议二选一：

    方案 A：安装 uv，推荐。
    在 WSL 中：

    curl -LsSf https://astral.sh/uv/install.sh | sh
    cd /mnt/g/Learning/GdylAgents_DR/backend
    uv sync --extra dev
    uv run python -m pytest -q

    方案 B：安装 venv 支持。
    由于当前 Python 是 3.14.4，错误提示需要：

    sudo apt install python3.14-venv

    然后：

    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
    python -m pytest -q

    另外建议在仓库加一个统一脚本：

    backend/scripts/test.sh

    内容类似：

    #!/usr/bin/env bash
    set -euo pipefail
    cd "$(dirname "$0")/.."
    if command -v uv >/dev/null 2>&1; then
      uv run --extra dev python -m pytest -q
    else
      python -m pytest -q
    fi

    这样后续不用每次猜命令。

    3. 第三优先级：SSE 事件强类型化

    当前 docs 反复提到“强类型 SSE 协议”，代码中还没完成：

    frontend/src/types/research.ts 仍是：

    export interface ResearchStreamEvent {
      type: string;
      [key: string]: unknown;
    }

    frontend/src/services/api.ts 也定义了一份类似类型，存在重复。

    建议下一步做成前后端事件契约。

    后端新增：

    backend/src/services/stream_events.py

    定义 Pydantic 模型：

    - BaseStreamEvent
      - type
      - run_id
      - timestamp
      - step?
      - task_id?
      - task_run_id?
      - stream_token?

    具体事件：

    - StatusEvent
    - TodoListEvent
    - SourcesEvent
    - TaskSummaryChunkEvent
    - TaskStatusEvent
    - ToolCallEvent
    - ReportNoteEvent
    - FinalReportEvent
    - DoneEvent
    - ErrorEvent

    然后 StreamRunner._emit() 在输出前做一次校验/规范化。

    前端则把 ResearchStreamEvent 改成 union type：

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

    收益：

    - App.vue 里大量 event as Record<string, unknown> 可以减少。
    - 字段名不一致会在开发期暴露。
    - 后续加 Timeline / Debug 面板更稳。

    建议同时消除重复类型定义：
    frontend/src/services/api.ts 不再重复定义 ResearchRequest、ResearchTodoItem、ResearchStreamEvent，而是统一从 frontend/src/types/research.ts import。

    4. 第四优先级：并发限制、timeout、取消机制

    当前 StreamRunner._run_task_workers() 是每个任务直接启动一个 Thread：

    for task in state.todo_items:
        thread = Thread(...)
        thread.start()

    这对小任务可以，但任务数多时会失控。

    建议增加配置：

    - max_concurrent_tasks: int = 3
    - search_timeout_seconds: int = 30
    - summary_timeout_seconds: int = 120
    - report_timeout_seconds: int = 180

    环境变量：

    - MAX_CONCURRENT_TASKS
    - SEARCH_TIMEOUT_SECONDS
    - SUMMARY_TIMEOUT_SECONDS
    - REPORT_TIMEOUT_SECONDS

    实现建议：

    1. StreamRunner 用 ThreadPoolExecutor(max_workers=config.max_concurrent_tasks) 替代手动无限 Thread。
    2. TaskExecutor 的 search_dispatcher 和 summarizer 增加 timeout 包装。
    3. 前端 AbortController 取消后，后端现在大概率仍然继续跑完线程。建议后端引入 cancellation token：
       - StreamRunner 创建 stop_event
       - event_iterator 捕获客户端断开/生成器关闭时设置 stop_event
       - worker 在搜索前、总结 chunk 循环中检查 stop_event
    4. run_store 增加 cancelled/failed 状态。

    这会显著提升稳定性。

    5. 第五优先级：run_store 从“能查 run”升级为“能管理 run”

    docs/run_store.md 已经指出后续方向：

    - started_at
    - completed_at
    - error
    - fail_run
    - 分页查询 events
    - 按 topic/status 查询历史 run 列表
    - PostgreSQL store

    我建议优先实现这几个接口：

    ResearchRunStore:
    - start_run(run_id, topic)
    - record_event(run_id, event)
    - complete_run(run_id)
    - fail_run(run_id, error)
    - cancel_run(run_id)
    - list_runs(limit=50, status=None, topic_query=None)
    - get_events(run_id, limit=200, offset=0)

    当前 API 只有：

    GET /research/runs/{run_id}

    建议新增：

    GET /research/runs
    GET /research/runs/{run_id}/events?limit=200&offset=0

    前端 HistoryPage 现在主要看 notes/reports，后续可以变成两个视角：

    - 报告历史：最终产物
    - 运行历史：过程 Timeline

    这会让调试和产品体验都更好。

    6. 第六优先级：搜索质量与 fallback

    backend/src/services/search.py 当前已经对 DuckDuckGo 做了国内环境适配，这是好点。但还有几个问题：

    1. SearchAPI 枚举里有拼写问题：
       SEAGXNG = "searxng"

       建议改成：
       SEARXNG = "searxng"

       旧名称可以兼容，但新代码别继续写错。

    2. dispatch_search 非 duckduckgo 后端异常时直接 raise。
       建议支持 fallback chain，例如：
       SEARCH_FALLBACKS=tavily,duckduckgo,searxng

    3. 搜索结果需要结构化评分：
       每条 source 增加：
       - title
       - url
       - snippet/content
       - backend
       - rank
       - score?
       - fetched_at?

    4. 增加 query rewriting：
       规划任务时生成 query 只是第一步，真正搜索前可以扩展：
       - 中文 query
       - 英文 query
       - site/domain 限定
       - 近一年/官方文档优先

    5. 增加去重和来源质量过滤：
       - URL normalize
       - 同域名限额
       - 低质量站点过滤
       - 优先官方、论文、文档、权威媒体

    这部分会直接提升报告质量。

    7. 第七优先级：Agent eval 体系

    docs 已经规划 backend/evals，目前代码里我没看到成熟 eval 目录。

    建议新增：

    backend/evals/cases.jsonl

    每行：

    {
      "id": "case_001",
      "topic": "对比 LangGraph 和 AutoGen 的多 Agent 编排能力",
      "expected_sections": ["背景", "架构", "优缺点", "适用场景"],
      "min_sources": 3,
      "max_duration_seconds": 300
    }

    backend/evals/run_eval.py

    最小指标：

    - 是否收到 done
    - 是否生成 final_report
    - completed/skipped/failed 数量
    - sources 数量
    - 空摘要数量
    - error 事件数量
    - 总耗时
    - 报告长度
    - 是否包含 expected_sections

    先不需要复杂 LLM judge。先用规则指标就很有价值。

    后续再加：

    - LLM judge: factuality / coverage / citation quality
    - regression baseline: 保存每次 prompt/model/search 改动前后的指标

    8. 第八优先级：前端状态管理继续拆分

    App.vue 已经拆了不少组件，但仍有 966 行，主要问题是：

    - SSE 事件分发逻辑全在 App.vue
    - parseSources、formatToolResult、trackStreamEvent、createTaskView 等工具逻辑混在页面里
    - ResearchBoard props 很多，父子组件耦合偏强

    建议拆成：

    frontend/src/composables/useResearchWorkflow.ts
    负责：
    - loading/planning/error
    - handleSubmit
    - startResearchFromPlan
    - cancelResearch
    - runResearchStream 事件处理

    frontend/src/composables/useResearchEvents.ts
    负责：
    - applyResearchEvent(event)
    - task_status/sources/tool_call/final_report 的分发

    frontend/src/utils/sources.ts
    负责：
    - parseSources

    frontend/src/utils/markdown.ts
    负责：
    - renderMd

    frontend/src/types/research.ts
    统一所有 API 类型和事件类型。

    ResearchBoard 的 props 可以用一个 view model 减少：

    <ResearchBoard
      :state="boardState"
      :actions="boardActions"
    />

    或者至少拆出：
    - TimelinePanel.vue
    - TaskCards.vue
    - TaskDetail.vue
    - SourcesPanel.vue
    - ToolCallsPanel.vue
    - ReportViewer.vue

    9. 第九优先级：HTTP 层继续瘦身

    main.py 当前仍有一些业务/文件逻辑：

    - _strip_report_heading
    - _titles_match
    - list_reports 直接读 notes_index.json
    - get_report 直接拼 Path(file).parent / "note"
    - report frontmatter 解析

    建议抽到：

    backend/src/services/report_store.py

    提供：

    - list_reports()
    - get_report(note_id)
    - parse_note_frontmatter()
    - strip_duplicate_heading()

    main.py 只保留：

    @app.get("/notes/reports")
    def list_reports():
        return report_store.list_reports()

    这样 main.py 更符合 docs 里说的“HTTP 边界”。

    10. 第十优先级：配置与部署安全

    当前 create_app 中 CORS 是：

    allow_origins=["*"]
    allow_credentials=True

    这在浏览器规范和安全上都不理想。生产环境建议：

    配置：

    CORS_ORIGINS=http://localhost:5173,https://your-domain.com

    代码：

    allow_origins=config.cors_origins
    allow_credentials=False 或仅在明确 origin 时 True

    另外建议：

    - 增加 /config/public 接口，只返回前端可展示配置，如 search backend 列表、max tasks，不返回 key。
    - Docker compose 中确认 volumes：
      - notes
      - sqlite run store
    - 不要把 frontend/.env.local 提交。
    - README 区分 dev/prod 启动方式。

    推荐下一步执行顺序：

    第 1 步：仓库清理
    - 修 .gitignore
    - notes/data/dist/env.local 从 git 索引移除
    - notes_workspace 改为 data/notes
    - main.py 历史报告读取改用配置路径

    第 2 步：测试环境
    - 安装 uv 或修复 venv
    - 跑通 backend pytest
    - 保留 frontend npm run build 作为前端验证

    第 3 步：SSE 强类型协议
    - 后端 Pydantic event models
    - 前端 union types
    - api.ts 去掉重复类型
    - App.vue 减少 unknown cast

    第 4 步：并发和 timeout
    - MAX_CONCURRENT_TASKS
    - search/summary/report timeout
    - fallback
    - cancellation

    第 5 步：run 管理和 eval
    - list_runs
    - paged events
    - fail/cancel status
    - backend/evals 最小评估脚本

    一句话总结：

    项目当前最有价值的优化，不是继续堆 Agent 功能，而是把“运行产物隔离、测试可复现、SSE 协议强类型、并发 timeout 可控、run/eval 可追踪”补齐。这样它会从“能跑的深度研究 demo”升级成“可维护、可调试、可评估的 Agent 工程项目”。