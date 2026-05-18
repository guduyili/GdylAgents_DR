
• 后续建议不要继续在 App.vue 里堆功能，下一步重点应从“能展示”升级到“结构清晰、可维护、可扩展”。

  优先级 1：组件拆分
  当前 frontend/src/App.vue 已经很大，后续应拆成：

  frontend/src/components/
    ResearchInputCard.vue
    PlanEditorCard.vue
    ResearchSidebar.vue
    ResearchBoard.vue
    MetricCard.vue
    TaskCard.vue
    TaskFocusCard.vue
    SourcesCard.vue
    ToolCallsCard.vue
    ReportCard.vue
    HistoryPage.vue

  这样后续加功能不会继续污染主文件。

  优先级 2：抽离研究状态逻辑
  把 SSE、任务状态更新、报告状态、工具调用处理从 App.vue 抽出去：

  frontend/src/composables/useResearchWorkflow.ts
  frontend/src/composables/useHistoryReports.ts
  frontend/src/utils/sourceParser.ts
  frontend/src/utils/markdown.ts

  目标是让 App.vue 只负责页面组装，而不是同时处理 UI、API、状态机、解析逻辑。

  优先级 3：卡片功能增强
  可以继续加这些产品能力：

  - 任务卡片支持“重新执行单个任务”
  - 任务卡片支持“暂停 / 跳过 / 标记完成”
  - 来源卡片支持收藏、复制链接、加入报告
  - 工具调用卡片支持折叠、过滤、只看失败调用
  - 报告卡片支持按章节重新生成
  - 任务卡片支持拖拽排序，但建议等组件拆分后再做

  优先级 4：后端会话化
  现在前端状态主要靠内存，刷新页面会丢失。后续可以加：

  ResearchSession
  ResearchTask
  ResearchEvent
  ResearchReport

  对应接口：

  POST /research/sessions
  GET /research/sessions
  GET /research/sessions/{id}
  POST /research/sessions/{id}/run
  POST /research/sessions/{id}/tasks/{task_id}/rerun

  这一步会让产品从“单次研究页面”升级成“可恢复的研究项目”。

  优先级 5：Skill 渐进式披露
  可以把之前讨论的 skill 加入研究流程：

  - 页面启动时只展示可用 skill 名称和描述
  - 模型需要时通过 SkillTool.read 加载完整 SKILL.md
  - 前端显示“已加载 Skill：xxx”的卡片事件
  - 任务卡片可展示该任务使用了哪些 skill

  这会让项目更接近 DeepAgents 的能力模型。

  我建议下一步按这个顺序做：

  1. 先拆 App.vue 组件。
  2. 再抽离 useResearchWorkflow。
  3. 然后做“单任务重新执行”。
  4. 最后做后端会话化和 Skill 动态加载。