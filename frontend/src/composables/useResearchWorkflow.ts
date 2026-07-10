import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import {
  cancelResearchRun,
  planResearch,
  runResearchStream,
  type ResearchStreamEvent,
  type ResearchTodoItem
} from "../services/api";
import type { ResearchRunSnapshot } from "../types/research";
import type {
  PlannedTaskView,
  ReviewResultView,
  TimelineEventView,
  TodoTaskView
} from "../types/view";
import { resolveTaskForEvent, type TaskChannelEvent } from "../utils/taskChannel";
import { buildTimelineFromSnapshot } from "../utils/timelineReplay";
import { parseSources } from "../utils/parseSources";
import {
  ensureRecord,
  formatEventTime,
  formatTaskStatus,
  formatToolParameters,
  formatToolResult
} from "../utils/researchFormatters";

export interface ResearchFormState {
  topic: string;
  searchApi: string;
  researchMode: "deep" | "quick";
}

interface WorkflowOptions {
  onHistoryRefresh?: () => void;
}

export function useResearchWorkflow(form: ResearchFormState, options: WorkflowOptions = {}) {
  const loading = ref(false);
  const planning = ref(false);
  const error = ref("");
  const progressLogs = ref<string[]>([]);
  const currentRunId = ref<string | null>(null);
  const timelineEvents = ref<TimelineEventView[]>([]);
  const timelineFilter = ref<string>("all");
  const traceTaskFilter = ref<number | null>(null);
  const phaseDurations = ref<Record<string, number>>({});
  const logsCollapsed = ref(false);
  const isExpanded = ref(false);

  const todoTasks = ref<TodoTaskView[]>([]);
  const plannedTasks = ref<PlannedTaskView[]>([]);
  const activeTaskId = ref<number | null>(null);
  const reportMarkdown = ref("");
  const reviewResult = ref<ReviewResultView | null>(null);
  const skippedTaskIds = ref<Set<number>>(new Set());

  const summaryHighlight = ref(false);
  const sourcesHighlight = ref(false);
  const reportHighlight = ref(false);
  const toolHighlight = ref(false);
  const sourcesSummaryOpen = ref(false);

  let currentController: AbortController | null = null;
  let nextPlannedTaskId = 1;

  watch(
    () => activeTaskId.value,
    () => {
      sourcesSummaryOpen.value = false;
    }
  );

  const totalTasks = computed(() => todoTasks.value.length);
  const completedTasks = computed(
    () => todoTasks.value.filter((task) => task.status === "completed").length
  );
  const planReady = computed(() => plannedTasks.value.length > 0 && !isExpanded.value);
  const canStartResearch = computed(() =>
    plannedTasks.value.some(
      (task) => task.title.trim() && task.intent.trim() && task.query.trim()
    )
  );

  const currentTask = computed(() => {
    if (activeTaskId.value !== null) {
      return todoTasks.value.find((task) => task.id === activeTaskId.value) ?? null;
    }
    return todoTasks.value[0] ?? null;
  });

  const currentTaskSources = computed(() => currentTask.value?.sourceItems ?? []);
  const currentTaskSummary = computed(() => currentTask.value?.summary ?? "");
  const currentTaskTitle = computed(() => currentTask.value?.title ?? "");
  const currentTaskIntent = computed(() => currentTask.value?.intent ?? "");
  const currentTaskQuery = computed(() => currentTask.value?.query ?? "");
  const currentTaskNoteId = computed(() => currentTask.value?.noteId ?? "");
  const currentTaskNotePath = computed(() => currentTask.value?.notePath ?? "");
  const currentTaskToolCalls = computed(() => currentTask.value?.toolCalls ?? []);

  function pulse(flag: Ref<boolean>) {
    flag.value = false;
    requestAnimationFrame(() => {
      flag.value = true;
      window.setTimeout(() => {
        flag.value = false;
      }, 1200);
    });
  }

  function buildToolDetail(event: ResearchStreamEvent): string | null {
    if (event.type !== "tool_call") {
      return null;
    }
    try {
      return JSON.stringify(
        {
          parameters: event.parameters ?? null,
          result: event.result ?? null
        },
        null,
        2
      );
    } catch (toolError) {
      console.warn("无法序列化工具调用详情", toolError);
      return null;
    }
  }

  function trackStreamEvent(event: ResearchStreamEvent, message: string): void {
    if (typeof event.run_id === "string" && event.run_id.trim()) {
      currentRunId.value = event.run_id.trim();
    }
    const evtType = typeof event.type === "string" ? event.type : "status";
    const log = `[${formatEventTime(event.timestamp)}] ${message}`;
    progressLogs.value.push(log);
    timelineEvents.value.push({
      id: `${event.run_id || "run"}-${timelineEvents.value.length}`,
      type: evtType,
      message,
      log,
      timestamp: event.timestamp,
      runId: event.run_id || null,
      taskId: typeof event.task_id === "number" ? event.task_id : null,
      taskRunId: event.task_run_id || null,
      streamToken: event.stream_token || null,
      source: event.source || null,
      step: typeof event.step === "number" ? event.step : null,
      durationMs: typeof event.duration_ms === "number" ? event.duration_ms : null,
      phase: event.type === "phase_duration" ? event.phase : null,
      inputPreview: event.type === "tool_call" ? event.input_preview?.trim() || null : null,
      outputPreview: event.type === "tool_call" ? event.output_preview?.trim() || null : null,
      toolDetail: buildToolDetail(event)
    });
  }

  function replayTimelineFromSnapshot(snapshot: ResearchRunSnapshot): void {
    const replay = buildTimelineFromSnapshot(snapshot);
    timelineEvents.value = replay.timelineEvents;
    progressLogs.value = replay.progressLogs;
    phaseDurations.value = replay.phaseDurations;
    if (replay.runId) {
      currentRunId.value = replay.runId;
    }
    logsCollapsed.value = false;
  }

  function eventTimestampMs(event: ResearchStreamEvent): number {
    if (typeof event.timestamp !== "string") {
      return Date.now();
    }
    const parsed = new Date(event.timestamp).getTime();
    return Number.isNaN(parsed) ? Date.now() : parsed;
  }

  function applyNoteMetadata(
    task: TodoTaskView,
    noteIdValue: string | null | undefined,
    notePathValue?: string | null
  ): void {
    const noteId = noteIdValue?.trim();
    if (noteId) {
      task.noteId = noteId;
    }
    const notePath = notePathValue?.trim();
    if (notePath) {
      task.notePath = notePath;
    }
  }

  async function copyNotePath(path: string | null | undefined) {
    if (!path) {
      return;
    }

    try {
      await navigator.clipboard.writeText(path);
      progressLogs.value.push(`已复制笔记路径：${path}`);
    } catch (copyError) {
      console.warn("无法直接复制到剪贴板", copyError);
      window.prompt("复制以下笔记路径", path);
      progressLogs.value.push("请手动复制笔记路径");
    }
  }

  function resetWorkflowState() {
    todoTasks.value = [];
    activeTaskId.value = null;
    reportMarkdown.value = "";
    reviewResult.value = null;
    skippedTaskIds.value = new Set();
    progressLogs.value = [];
    currentRunId.value = null;
    timelineEvents.value = [];
    timelineFilter.value = "all";
    traceTaskFilter.value = null;
    phaseDurations.value = {};
    summaryHighlight.value = false;
    sourcesHighlight.value = false;
    reportHighlight.value = false;
    toolHighlight.value = false;
    logsCollapsed.value = false;
  }

  function clearPlannedTasks() {
    plannedTasks.value = [];
  }

  function findTaskForEvent(event: TaskChannelEvent): TodoTaskView | undefined {
    return resolveTaskForEvent(todoTasks.value, event);
  }

  function upsertTaskMetadata(
    task: TodoTaskView,
    payload: { title?: string | null; intent?: string | null; query?: string | null }
  ) {
    if (payload.title?.trim()) {
      task.title = payload.title.trim();
    }
    if (payload.intent?.trim()) {
      task.intent = payload.intent.trim();
    }
    if (payload.query?.trim()) {
      task.query = payload.query.trim();
    }
  }

  function createTaskView(item: Record<string, unknown>, index: number): TodoTaskView {
    const rawId =
      typeof item.id === "number"
        ? item.id
        : typeof item.id === "string"
          ? Number(item.id)
          : index + 1;
    const id = Number.isFinite(rawId) ? Number(rawId) : index + 1;
    const noteId =
      typeof item.note_id === "string" && item.note_id.trim() ? item.note_id.trim() : null;
    const notePath =
      typeof item.note_path === "string" && item.note_path.trim() ? item.note_path.trim() : null;

    return {
      id,
      title:
        typeof item.title === "string" && item.title.trim()
          ? item.title.trim()
          : `任务${id}`,
      intent:
        typeof item.intent === "string" && item.intent.trim()
          ? item.intent.trim()
          : "探索与主题相关的关键信息",
      query:
        typeof item.query === "string" && item.query.trim()
          ? item.query.trim()
          : form.topic.trim(),
      status:
        typeof item.status === "string" && item.status.trim()
          ? item.status.trim()
          : "pending",
      summary: "",
      sourcesSummary: "",
      sourceItems: [],
      notices: [],
      noteId,
      notePath,
      taskRunId:
        typeof item.task_run_id === "string" && item.task_run_id.trim()
          ? item.task_run_id.trim()
          : null,
      streamToken:
        typeof item.stream_token === "string" && item.stream_token.trim()
          ? item.stream_token.trim()
          : null,
    toolCalls: [],
    loadedSkills: [],
    factCheck: null,
    searchBackend: null
  };
}

  function setPlannedTasks(items: ResearchTodoItem[]) {
    plannedTasks.value = items.map((item, index) => ({
      localId: nextPlannedTaskId++,
      title: item.title?.trim() || `任务${index + 1}`,
      intent: item.intent?.trim() || "探索与主题相关的关键信息",
      query: item.query?.trim() || form.topic.trim()
    }));
  }

  function addPlannedTask() {
    const index = plannedTasks.value.length + 1;
    plannedTasks.value.push({
      localId: nextPlannedTaskId++,
      title: `补充任务${index}`,
      intent: "补充用户关心但规划未覆盖的关键问题",
      query: form.topic.trim()
    });
  }

  function removePlannedTask(index: number) {
    if (plannedTasks.value.length <= 1) {
      return;
    }
    plannedTasks.value.splice(index, 1);
  }

  function movePlannedTask(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= plannedTasks.value.length) {
      return;
    }
    const [task] = plannedTasks.value.splice(index, 1);
    plannedTasks.value.splice(target, 0, task);
  }

  function buildConfirmedTodoItems(): ResearchTodoItem[] {
    return plannedTasks.value
      .map((task, index) => ({
        id: index + 1,
        title: task.title.trim(),
        intent: task.intent.trim(),
        query: task.query.trim() || form.topic.trim()
      }))
      .filter((task) => task.title && task.intent && task.query);
  }

  function skipTask(taskId: number) {
    skippedTaskIds.value.add(taskId);
    const task = todoTasks.value.find((entry) => entry.id === taskId);
    if (task) {
      task.status = "skipped";
      progressLogs.value.push(`已本地跳过任务 ${taskId}：${task.title}`);
    }
  }

  function processResearchStreamEvent(event: ResearchStreamEvent): void {
    switch (event.type) {
      case "status": {
        const message = event.message.trim() || "流程状态更新";
        trackStreamEvent(event, message);
        const task = findTaskForEvent(event);
        if (task && message) {
          task.notices.push(message);
        }
        return;
      }

      case "todo_list": {
        todoTasks.value = event.tasks.map((item, index) =>
          createTaskView(
            {
              id: item.id ?? undefined,
              title: item.title,
              intent: item.intent,
              query:
                "query" in item && typeof item.query === "string"
                  ? item.query
                  : form.topic.trim(),
              status: item.status ?? undefined,
              note_id: item.note_id ?? undefined,
              note_path: item.note_path ?? undefined,
              task_run_id: item.task_run_id ?? undefined,
              stream_token: item.stream_token ?? undefined
            },
            index
          )
        );

        if (todoTasks.value.length) {
          activeTaskId.value = todoTasks.value[0].id;
          trackStreamEvent(event, "已生成任务清单");
        } else {
          trackStreamEvent(event, "未生成任务清单，使用默认任务继续");
        }
        return;
      }

      case "task_status": {
        const task = findTaskForEvent(event);
        if (!task || skippedTaskIds.value.has(task.id)) {
          return;
        }

        upsertTaskMetadata(task, event);
        applyNoteMetadata(task, event.note_id, event.note_path);
        const status = event.status.trim() || task.status;
        task.status = status;

        if (status === "in_progress") {
        task.summary = "";
        task.sourcesSummary = "";
        task.sourceItems = [];
        task.notices = [];
        task.loadedSkills = [];
        task.factCheck = null;
        task.searchBackend = null;
          activeTaskId.value = task.id;
          trackStreamEvent(event, `开始执行任务：${task.title}`);
        } else if (status === "completed") {
          if (event.summary?.trim()) {
            task.summary = event.summary.trim();
          }
          if (event.sources_summary?.trim()) {
            task.sourcesSummary = event.sources_summary.trim();
            task.sourceItems = parseSources(task.sourcesSummary);
          }
          trackStreamEvent(event, `完成任务：${task.title}`);
          if (activeTaskId.value === task.id) {
            pulse(summaryHighlight);
            pulse(sourcesHighlight);
          }
        } else if (status === "skipped") {
          trackStreamEvent(event, `任务跳过：${task.title}`);
        } else if (status === "failed") {
          trackStreamEvent(
            event,
            `任务失败：${task.title}${event.error ? `（${event.error}）` : ""}`
          );
        } else if (status === "cancelled") {
          trackStreamEvent(
            event,
            `任务已取消：${task.title}${event.error ? `（${event.error}）` : ""}`
          );
        }
        return;
      }

      case "sources": {
        const task = findTaskForEvent(event);
        if (!task || skippedTaskIds.value.has(task.id)) {
          return;
        }

        const latestText = [event.latest_sources, event.raw_context ?? ""]
          .map((value) => value.trim())
          .find((value) => value);

        if (latestText) {
          task.sourcesSummary = latestText;
          task.sourceItems = parseSources(latestText);
          if (activeTaskId.value === task.id) {
            pulse(sourcesHighlight);
          }
          trackStreamEvent(event, `已更新任务来源：${task.title}`);
        }

        if (event.backend?.trim()) {
          task.searchBackend = event.backend.trim();
          trackStreamEvent(event, `当前使用搜索后端：${event.backend.trim()}`);
        }

        applyNoteMetadata(task, event.note_id, event.note_path);
        return;
      }

      case "task_summary_chunk": {
        const task = findTaskForEvent(event);
        if (!task || skippedTaskIds.value.has(task.id)) {
          return;
        }
        task.summary += event.content;
        applyNoteMetadata(task, event.note_id);
        if (activeTaskId.value === task.id) {
          pulse(summaryHighlight);
        }
        return;
      }

      case "tool_call": {
        const eventId = typeof event.event_id === "number" ? event.event_id : Date.now();
        const agent = event.agent?.trim() || "Agent";
        const tool = event.tool.trim() || "tool";
        const parameters = ensureRecord(event.parameters);
        const result = typeof event.result === "string" ? event.result : "";
        const noteId = event.note_id?.trim() || null;
        const notePath = event.note_path?.trim() || null;

        const task = findTaskForEvent(event);
        if (task && !skippedTaskIds.value.has(task.id)) {
          task.toolCalls.push({
            eventId,
            agent,
            tool,
            parameters,
            result,
            inputPreview: event.input_preview?.trim() || null,
            outputPreview: event.output_preview?.trim() || null,
            noteId,
            notePath,
            timestamp: eventTimestampMs(event),
            durationMs: typeof event.duration_ms === "number" ? event.duration_ms : null
          });
          if (noteId) {
            task.noteId = noteId;
          }
          if (notePath) {
            task.notePath = notePath;
          }
          const logSummary = noteId
            ? `${agent} 调用了 ${tool}（任务 ${task.id}，笔记 ${noteId}）`
            : `${agent} 调用了 ${tool}（任务 ${task.id}）`;
          trackStreamEvent(event, logSummary);
          if (activeTaskId.value === task.id) {
            pulse(toolHighlight);
          }
        } else {
          trackStreamEvent(event, `${agent} 调用了 ${tool}`);
        }
        return;
      }

      case "report_note": {
        const noteMessage = event.title?.trim()
          ? `报告笔记已保存：${event.title.trim()}`
          : "报告笔记已保存";
        trackStreamEvent(event, noteMessage);
        return;
      }

      case "phase_duration": {
        if (typeof event.duration_ms === "number") {
          phaseDurations.value = {
            ...phaseDurations.value,
            [event.phase]: event.duration_ms
          };
        }
        const phaseLabels: Record<string, string> = {
          planning: "规划",
          search: "搜索",
          summary: "总结",
          report: "报告",
          total: "全流程"
        };
        const phaseLabel = phaseLabels[event.phase] || event.phase;
        trackStreamEvent(event, `阶段耗时 ${phaseLabel}：${event.duration_ms ?? 0}ms`);
        return;
      }

      case "final_report": {
        const report = event.report.trim();
        reportMarkdown.value = report || "报告生成失败，未获得有效内容";
        pulse(reportHighlight);
        trackStreamEvent(event, "最终报告已生成");
        options.onHistoryRefresh?.();
        return;
      }

      case "review_result": {
        reviewResult.value = {
          passed: event.passed,
          score: event.score,
          issues: event.issues ?? [],
          suggestions: event.suggestions ?? []
        };
        const verdict = event.passed ? "通过" : "需改进";
        trackStreamEvent(event, `报告评审${verdict}（得分 ${event.score}）`);
        return;
      }

      case "fact_check_result": {
        const task = findTaskForEvent(event);
        if (task) {
          task.factCheck = {
            passed: event.passed,
            score: event.score,
            matchedSources: event.matched_sources ?? [],
            warnings: event.warnings ?? [],
            missingTerms: event.missing_terms ?? []
          };
        }
        const verdict = event.passed ? "通过" : "需留意";
        trackStreamEvent(event, `事实核对${verdict}（得分 ${event.score}）`);
        return;
      }

      case "skill_loaded": {
        const task = findTaskForEvent(event);
        if (task) {
          task.loadedSkills.push({
            name: event.skill_name,
            description: event.skill_description?.trim() || "",
            preview: event.preview?.trim() || ""
          });
          trackStreamEvent(event, `已加载 Skill：${event.skill_name}`);
        }
        return;
      }

      case "done": {
        trackStreamEvent(event, "研究流程已完成");
        return;
      }

      case "cancelled": {
        progressLogs.value.push(event.message.trim() || "研究已取消");
        trackStreamEvent(event, event.message.trim() || "研究已取消");
        return;
      }

      case "error": {
        const detail = event.detail.trim() || "研究过程中发生错误";
        error.value = detail;
        trackStreamEvent(event, "研究失败，已停止流程");
        return;
      }
    }
  }

  async function runResearch(payload: {
    topic: string;
    search_api?: string;
    mode?: "deep" | "quick";
    todo_items?: ResearchTodoItem[];
  }) {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }

    const controller = new AbortController();
    currentController = controller;

    try {
      await runResearchStream(payload, processResearchStreamEvent, {
        signal: controller.signal,
        onRunStarted: (runId) => {
          currentRunId.value = runId;
        }
      });
      if (!reportMarkdown.value) {
        reportMarkdown.value = "暂无生成的报告";
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        progressLogs.value.push("已取消当前研究任务");
      } else {
        error.value = err instanceof Error ? err.message : "请求失败";
      }
    } finally {
      loading.value = false;
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  async function handleSubmit() {
    if (!form.topic.trim()) {
      error.value = "请输入研究主题";
      return;
    }

    if (form.researchMode === "quick") {
      await startQuickResearch();
      return;
    }

    if (currentController) {
      currentController.abort();
      currentController = null;
    }

    loading.value = true;
    planning.value = true;
    error.value = "";
    resetWorkflowState();

    const controller = new AbortController();
    currentController = controller;

    try {
      const plan = await planResearch(
        {
          topic: form.topic.trim(),
          search_api: form.searchApi || undefined
        },
        { signal: controller.signal }
      );
      setPlannedTasks(plan.todo_items);
      if (!plannedTasks.value.length) {
        error.value = "未生成有效任务规划，请调整主题后重试";
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        progressLogs.value.push("已取消研究规划");
      } else {
        error.value = err instanceof Error ? err.message : "研究规划失败";
      }
    } finally {
      loading.value = false;
      planning.value = false;
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  async function startQuickResearch() {
    loading.value = true;
    planning.value = false;
    error.value = "";
    isExpanded.value = true;
    resetWorkflowState();
    clearPlannedTasks();

    await runResearch({
      topic: form.topic.trim(),
      search_api: form.searchApi || undefined,
      mode: "quick"
    });
  }

  async function startResearchFromPlan() {
    if (!form.topic.trim()) {
      error.value = "请输入研究主题";
      return;
    }

    const confirmedTasks = buildConfirmedTodoItems();
    if (!confirmedTasks.length) {
      error.value = "请至少保留一个完整任务";
      return;
    }

    loading.value = true;
    planning.value = false;
    error.value = "";
    isExpanded.value = true;
    resetWorkflowState();

    todoTasks.value = confirmedTasks.map((item, index) => createTaskView({ ...item }, index));
    if (todoTasks.value.length) {
      activeTaskId.value = todoTasks.value[0].id;
    }

    await runResearch({
      topic: form.topic.trim(),
      search_api: form.searchApi || undefined,
      mode: form.researchMode,
      todo_items: confirmedTasks
    });
  }

  async function retryTask(taskId: number) {
    const task = todoTasks.value.find((entry) => entry.id === taskId);
    if (!task || loading.value) {
      return;
    }

    skippedTaskIds.value.delete(taskId);
    task.status = "pending";
    task.summary = "";
    task.sourcesSummary = "";
    task.sourceItems = [];
    task.toolCalls = [];
    task.notices = [];
    activeTaskId.value = taskId;
    loading.value = true;
    error.value = "";

    await runResearch({
      topic: form.topic.trim(),
      search_api: form.searchApi || undefined,
      mode: form.researchMode,
      todo_items: [
        {
          id: task.id,
          title: task.title,
          intent: task.intent,
          query: task.query
        }
      ]
    });
  }

  function downloadReport() {
    if (!reportMarkdown.value) {
      return;
    }
    const blob = new Blob([reportMarkdown.value], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `report_${form.topic.slice(0, 20).replace(/\s+/g, "_")}_${Date.now()}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function cancelResearch() {
    if (!loading.value || !currentController) {
      return;
    }
    progressLogs.value.push(
      planning.value ? "正在取消研究规划…" : "正在尝试取消当前研究任务…"
    );

    if (!planning.value && currentRunId.value) {
      try {
        const result = await cancelResearchRun(currentRunId.value);
        if (result.cancelled) {
          progressLogs.value.push(result.message);
        }
      } catch (err) {
        console.warn("显式取消 API 调用失败，将回退为断开 SSE", err);
      }
    }

    currentController.abort();
  }

  function goBack() {
    if (loading.value) {
      return;
    }
    isExpanded.value = false;
  }

  function startNewResearch() {
    if (loading.value) {
      cancelResearch();
    }
    resetWorkflowState();
    clearPlannedTasks();
    isExpanded.value = false;
    form.topic = "";
    form.searchApi = "";
    form.researchMode = "deep";
  }

  onBeforeUnmount(() => {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
  });

  return {
    loading,
    planning,
    error,
    progressLogs,
    currentRunId,
    timelineEvents,
    timelineFilter,
    traceTaskFilter,
    phaseDurations,
    logsCollapsed,
    isExpanded,
    todoTasks,
    plannedTasks,
    activeTaskId,
    reportMarkdown,
    reviewResult,
    summaryHighlight,
    sourcesHighlight,
    reportHighlight,
    toolHighlight,
    sourcesSummaryOpen,
    totalTasks,
    completedTasks,
    planReady,
    canStartResearch,
    currentTask,
    currentTaskSources,
    currentTaskSummary,
    currentTaskTitle,
    currentTaskIntent,
    currentTaskQuery,
    currentTaskNoteId,
    currentTaskNotePath,
    currentTaskToolCalls,
    formatTaskStatus,
    formatToolParameters,
    formatToolResult,
    copyNotePath,
    replayTimelineFromSnapshot,
    addPlannedTask,
    removePlannedTask,
    movePlannedTask,
    handleSubmit,
    startResearchFromPlan,
    startQuickResearch,
    retryTask,
    skipTask,
    downloadReport,
    cancelResearch,
    goBack,
    startNewResearch
  };
}