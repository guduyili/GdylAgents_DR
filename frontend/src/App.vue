<template>
  <main class="app-shell" :class="{ expanded: isExpanded }">
    <div class="aurora" aria-hidden="true">
      <span></span>
      <span></span>
      <span></span>
    </div>

    <div v-if="!isExpanded" class="layout layout-centered">
      <ResearchForm
        v-model:topic="form.topic"
        v-model:search-api="form.searchApi"
        :search-options="searchOptions"
        :loading="loading"
        :planning="planning"
        :plan-ready="planReady"
        :history-count="historyReports.length"
        @submit="handleSubmit"
        @cancel="cancelResearch"
        @open-history="openHistoryPage"
      >
        <PlanEditor
          v-if="planReady"
          :planned-tasks="plannedTasks"
          :loading="loading"
          :can-start-research="canStartResearch"
          @add-task="addPlannedTask"
          @remove-task="removePlannedTask"
          @move-task="movePlannedTask"
          @start="startResearchFromPlan"
        />

        <p v-if="error" class="error-chip">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M10 3.2c-.3 0-.6.2-.8.5L3.4 15c-.4.7.1 1.6.8 1.6h11.6c.7 0 1.2-.9.8-1.6L10.8 3.7c-.2-.3-.5-.5-.8-.5Zm0 4.3c.4 0 .7.3.7.7v4c0 .4-.3.7-.7.7s-.7-.3-.7-.7V8.2c0-.4.3-.7.7-.7Zm0 6.6a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"
            />
          </svg>
          {{ error }}
        </p>
        <p v-else-if="loading" class="hint muted">正在收集线索与证据，实时进展见右侧区域。</p>
      </ResearchForm>
    </div>

    <HistoryPage
      v-if="historyPageOpen"
      :history-loading="historyLoading"
      :history-reports="historyReports"
      :selected-report="selectedReport"
      :render-md="renderMd"
      @close="closeHistoryPage"
      @open-report="openReport"
    />

    <div v-if="isExpanded" class="layout layout-fullscreen">
      <ResearchSidebar
        :topic="form.topic"
        :search-api="form.searchApi"
        :total-tasks="totalTasks"
        :completed-tasks="completedTasks"
        :loading="loading"
        @back="goBack"
        @new-research="startNewResearch"
      />

      <ResearchBoard
        :todo-tasks="todoTasks"
        :report-markdown="reportMarkdown"
        :progress-logs="progressLogs"
        :current-run-id="currentRunId"
        :timeline-events="timelineEvents"
        :timeline-filter="timelineFilter"
        :loading="loading"
        :logs-collapsed="logsCollapsed"
        :completed-tasks="completedTasks"
        :total-tasks="totalTasks"
        :current-task="currentTask"
        :current-task-title="currentTaskTitle"
        :current-task-intent="currentTaskIntent"
        :current-task-query="currentTaskQuery"
        :current-task-note-id="currentTaskNoteId"
        :current-task-note-path="currentTaskNotePath"
        :current-task-sources="currentTaskSources"
        :current-task-summary="currentTaskSummary"
        :current-task-tool-calls="currentTaskToolCalls"
        :active-task-id="activeTaskId"
        :search-api="form.searchApi"
        :sources-summary-open="sourcesSummaryOpen"
        :summary-highlight="summaryHighlight"
        :sources-highlight="sourcesHighlight"
        :report-highlight="reportHighlight"
        :tool-highlight="toolHighlight"
        :render-md="renderMd"
        :format-task-status="formatTaskStatus"
        :format-tool-parameters="formatToolParameters"
        :format-tool-result="formatToolResult"
        :copy-note-path="copyNotePath"
        @toggle-logs="logsCollapsed = !logsCollapsed"
        @update:timeline-filter="timelineFilter = $event"
        @download-report="downloadReport"
        @select-task="activeTaskId = $event"
        @toggle-sources-summary="sourcesSummaryOpen = !sourcesSummaryOpen"
      />
    </div>
  </main>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import "./styles/app.css";
import ResearchForm from "./components/ResearchForm.vue";
import PlanEditor from "./components/PlanEditor.vue";
import HistoryPage from "./components/HistoryPage.vue";
import ResearchSidebar from "./components/ResearchSidebar.vue";
import ResearchBoard from "./components/ResearchBoard.vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

/** 将 Markdown 字符串渲染为安全的 HTML */
function renderMd(src: string): string {
  if (!src) return "";
  const raw = marked.parse(src, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}

import {
  planResearch,
  runResearchStream,
  listReports,
  getReport,
  type ResearchTodoItem,
  type ResearchStreamEvent,
  type ReportItem,
  type ReportDetail
} from "./services/api";
import type { PlannedTaskView, SourceItem, TodoTaskView } from "./types/view";


const form = reactive({
  topic: "",
  searchApi: ""
});

const loading = ref(false);
const planning = ref(false);
const error = ref("");
const progressLogs = ref<string[]>([]);
const currentRunId = ref<string | null>(null);
const timelineEvents = ref<{ type: string; message: string }[]>([]);
const timelineFilter = ref<string>("all");
const logsCollapsed = ref(false);
const isExpanded = ref(false);

const todoTasks = ref<TodoTaskView[]>([]);
const plannedTasks = ref<PlannedTaskView[]>([]);
const activeTaskId = ref<number | null>(null);
const reportMarkdown = ref("");

const summaryHighlight = ref(false);
const sourcesHighlight = ref(false);
const reportHighlight = ref(false);
const toolHighlight = ref(false);

let currentController: AbortController | null = null;
let nextPlannedTaskId = 1;

// ── 历史报告 ──────────────────────────────────────
const historyReports = ref<ReportItem[]>([]);
const historyLoading = ref(false);
const selectedReport = ref<ReportDetail | null>(null);
const historyPageOpen = ref(false);

async function loadHistory() {
  if (historyLoading.value) return; // 已在加载中，跳过
  historyLoading.value = true;
  try {
    historyReports.value = await listReports();
  } catch {
    // 服务不可用时静默失败
  } finally {
    historyLoading.value = false;
  }
}

function openHistoryPage() {
  historyPageOpen.value = true;
  selectedReport.value = null;
  loadHistory(); // 打开时刷新，确保数据最新
}

function closeHistoryPage() {
  historyPageOpen.value = false;
}

async function openReport(noteId: string) {
  try {
    selectedReport.value = await getReport(noteId);
  } catch (e) {
    console.error("加载报告失败", e);
  }
}

// ── 下载报告 ──────────────────────────────────────
function downloadReport() {
  if (!reportMarkdown.value) return;
  const blob = new Blob([reportMarkdown.value], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `report_${form.topic.slice(0, 20).replace(/\s+/g, "_")}_${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── sources_summary 折叠 ──────────────────────────
const sourcesSummaryOpen = ref(false);
watch(() => activeTaskId.value, () => {
  sourcesSummaryOpen.value = false;
});

const searchOptions = [
  "advanced",
  "duckduckgo",
  "tavily",
  "perplexity",
  "searxng"
];

const TASK_STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  in_progress: "进行中",
  completed: "已完成",
  skipped: "已跳过"
};

function formatTaskStatus(status: string): string {
  return TASK_STATUS_LABEL[status] ?? status;
}

const totalTasks = computed(() => todoTasks.value.length);
const completedTasks = computed(() =>
  todoTasks.value.filter((task) => task.status === "completed").length
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
const currentTaskToolCalls = computed(
  () => currentTask.value?.toolCalls ?? []
);

const pulse = (flag: typeof summaryHighlight) => {
  flag.value = false;
  requestAnimationFrame(() => {
    flag.value = true;
    window.setTimeout(() => {
      flag.value = false;
    }, 1200);
  });
};

function parseSources(raw: string): SourceItem[] {
  if (!raw) {
    return [];
  }

  const items: SourceItem[] = [];
  const lines = raw.split("\n");

  let current: SourceItem | null = null;
  const truncate = (value: string, max = 360) => {
    const trimmed = value.trim();
    return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
  };

  const flush = () => {
    if (!current) {
      return;
    }
    const normalized: SourceItem = {
      title: current.title?.trim() || "",
      url: current.url?.trim() || "",
      snippet: current.snippet ? truncate(current.snippet) : "",
      raw: current.raw ? truncate(current.raw, 420) : ""
    };

    if (
      normalized.title ||
      normalized.url ||
      normalized.snippet ||
      normalized.raw
    ) {
      if (!normalized.title && normalized.url) {
        normalized.title = normalized.url;
      }
      items.push(normalized);
    }
    current = null;
  };

  const ensureCurrent = () => {
    if (!current) {
      current = { title: "", url: "", snippet: "", raw: "" };
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    if (/^\*/.test(trimmed) && trimmed.includes(" : ")) {
      flush();
      const withoutBullet = trimmed.replace(/^\*\s*/, "");
      const [titlePart, urlPart] = withoutBullet.split(" : ");
      current = {
        title: titlePart?.trim() || "",
        url: urlPart?.trim() || "",
        snippet: "",
        raw: ""
      };
      continue;
    }

    if (/^(Source|信息来源)\s*:/.test(trimmed)) {
      flush();
      const [, titlePart = ""] = trimmed.split(/:\s*(.+)/);
      current = {
        title: titlePart.trim(),
        url: "",
        snippet: "",
        raw: ""
      };
      continue;
    }

    if (/^URL\s*:/.test(trimmed)) {
      ensureCurrent();
      const [, urlPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.url = urlPart.trim();
      continue;
    }

    if (
      /^(Most relevant content from source|信息内容)\s*:/.test(trimmed)
    ) {
      ensureCurrent();
      const [, contentPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.snippet = contentPart.trim();
      continue;
    }

    if (
      /^(Full source content limited to|信息内容限制为)\s*:/.test(trimmed)
    ) {
      ensureCurrent();
      const [, rawPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.raw = rawPart.trim();
      continue;
    }

    if (/^https?:\/\//.test(trimmed)) {
      ensureCurrent();
      if (!current!.url) {
        current!.url = trimmed;
        continue;
      }
    }

    ensureCurrent();
    current!.raw = current!.raw ? `${current!.raw}\n${trimmed}` : trimmed;
  }

  flush();
  return items;
}

function extractOptionalString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function ensureRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function formatEventTime(timestamp: unknown): string {
  if (typeof timestamp !== "string" || !timestamp.trim()) {
    return new Date().toLocaleTimeString();
  }
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp.trim();
  }
  return parsed.toLocaleTimeString();
}

function trackStreamEvent(event: ResearchStreamEvent, message: string): void {
  if (typeof event.run_id === "string" && event.run_id.trim()) {
    currentRunId.value = event.run_id.trim();
  }
  const evtType = typeof event.type === "string" ? event.type : "status";
  progressLogs.value.push(`[${formatEventTime(event.timestamp)}] ${message}`);
  timelineEvents.value.push({ type: evtType, message });
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

function formatToolParameters(parameters: Record<string, unknown>): string {
  try {
    return JSON.stringify(parameters, null, 2);
  } catch (error) {
    console.warn("无法格式化工具参数", error, parameters);
    return Object.entries(parameters)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join("\n");
  }
}

function formatToolResult(result: string): string {
  const trimmed = result.trim();
  const limit = 900;
  if (trimmed.length > limit) {
    return `${trimmed.slice(0, limit)}…`;
  }
  return trimmed;
}

async function copyNotePath(path: string | null | undefined) {
  if (!path) {
    return;
  }

  try {
    await navigator.clipboard.writeText(path);
    progressLogs.value.push(`已复制笔记路径：${path}`);
  } catch (error) {
    console.warn("无法直接复制到剪贴板", error);
    window.prompt("复制以下笔记路径", path);
    progressLogs.value.push("请手动复制笔记路径");
  }
}

function resetWorkflowState() {
  todoTasks.value = [];
  activeTaskId.value = null;
  reportMarkdown.value = "";
  progressLogs.value = [];
  currentRunId.value = null;
  timelineEvents.value = [];
  timelineFilter.value = "all";
  summaryHighlight.value = false;
  sourcesHighlight.value = false;
  reportHighlight.value = false;
  toolHighlight.value = false;
  logsCollapsed.value = false;
}

function clearPlannedTasks() {
  plannedTasks.value = [];
}

function findTask(taskId: unknown): TodoTaskView | undefined {
  const numeric =
    typeof taskId === "number"
      ? taskId
      : typeof taskId === "string"
      ? Number(taskId)
      : NaN;
  if (Number.isNaN(numeric)) {
    return undefined;
  }
  return todoTasks.value.find((task) => task.id === numeric);
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
    typeof item.note_id === "string" && item.note_id.trim()
      ? item.note_id.trim()
      : null;
  const notePath =
    typeof item.note_path === "string" && item.note_path.trim()
      ? item.note_path.trim()
      : null;

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
    toolCalls: []
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

const handleSubmit = async () => {
  if (!form.topic.trim()) {
    error.value = "请输入研究主题";
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

  const payload = {
    topic: form.topic.trim(),
    search_api: form.searchApi || undefined
  };

  try {
    const plan = await planResearch(payload, { signal: controller.signal });
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
};

const startResearchFromPlan = async () => {
  if (!form.topic.trim()) {
    error.value = "请输入研究主题";
    return;
  }

  const confirmedTasks = buildConfirmedTodoItems();
  if (!confirmedTasks.length) {
    error.value = "请至少保留一个完整任务";
    return;
  }

  if (currentController) {
    currentController.abort();
    currentController = null;
  }

  loading.value = true;
  planning.value = false;
  error.value = "";
  isExpanded.value = true;
  resetWorkflowState();

  todoTasks.value = confirmedTasks.map((item, index) =>
    createTaskView({ ...item }, index)
  );
  if (todoTasks.value.length) {
    activeTaskId.value = todoTasks.value[0].id;
  }

  const controller = new AbortController();
  currentController = controller;

  const payload = {
    topic: form.topic.trim(),
    search_api: form.searchApi || undefined,
    todo_items: confirmedTasks
  };

  try {
    await runResearchStream(
      payload,
      (event: ResearchStreamEvent) => {
        switch (event.type) {
          case "status": {
            const message = event.message.trim() || "流程状态更新";
            trackStreamEvent(event, message);

            const task = findTask(event.task_id);
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
                  query: "query" in item && typeof item.query === "string" ? item.query : form.topic.trim(),
                  status: item.status ?? undefined,
                  note_id: item.note_id ?? undefined,
                  note_path: item.note_path ?? undefined
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
            const task = findTask(event.task_id);
            if (!task) {
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
            }
            return;
          }

          case "sources": {
            const task = findTask(event.task_id);
            if (!task) {
              return;
            }

            const latestText = [
              event.latest_sources,
              event.raw_context ?? ""
            ]
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
              trackStreamEvent(event, `当前使用搜索后端：${event.backend.trim()}`);
            }

            applyNoteMetadata(task, event.note_id, event.note_path);
            return;
          }

          case "task_summary_chunk": {
            const task = findTask(event.task_id);
            if (!task) {
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
            const eventId =
              typeof event.event_id === "number" ? event.event_id : Date.now();
            const agent = event.agent?.trim() || "Agent";
            const tool = event.tool.trim() || "tool";
            const parameters = ensureRecord(event.parameters);
            const result = typeof event.result === "string" ? event.result : "";
            const noteId = event.note_id?.trim() || null;
            const notePath = event.note_path?.trim() || null;

            const task = findTask(event.task_id);
            if (task) {
              task.toolCalls.push({
                eventId,
                agent,
                tool,
                parameters,
                result,
                noteId,
                notePath,
                timestamp: eventTimestampMs(event)
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

          case "final_report": {
            const report = event.report.trim();
            reportMarkdown.value = report || "报告生成失败，未获得有效内容";
            pulse(reportHighlight);
            trackStreamEvent(event, "最终报告已生成");
            loadHistory();
            return;
          }

          case "done": {
            trackStreamEvent(event, "研究流程已完成");
            return;
          }

          case "error": {
            const detail = event.detail.trim() || "研究过程中发生错误";
            error.value = detail;
            trackStreamEvent(event, "研究失败，已停止流程");
            return;
          }
        }
      },
      { signal: controller.signal }
    );

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
};

const cancelResearch = () => {
  if (!loading.value || !currentController) {
    return;
  }
  progressLogs.value.push(planning.value ? "正在取消研究规划…" : "正在尝试取消当前研究任务…");
  currentController.abort();
};

const goBack = () => {
  if (loading.value) {
    return; // 研究进行中不允许返回
  }
  isExpanded.value = false;
};

const startNewResearch = () => {
  if (loading.value) {
    cancelResearch();
  }
  resetWorkflowState();
  clearPlannedTasks();
  isExpanded.value = false;
  form.topic = "";
  form.searchApi = "";
};

onBeforeUnmount(() => {
  if (currentController) {
    currentController.abort();
    currentController = null;
  }
});

onMounted(() => {
  loadHistory();
});
</script>

