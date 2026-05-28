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

function applyNoteMetadata(
  task: TodoTaskView,
  payload: Record<string, unknown>
): void {
  const noteId = extractOptionalString(payload.note_id);
  if (noteId) {
    task.noteId = noteId;
  }
  const notePath = extractOptionalString(payload.note_path);
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

function upsertTaskMetadata(task: TodoTaskView, payload: Record<string, unknown>) {
  if (typeof payload.title === "string" && payload.title.trim()) {
    task.title = payload.title.trim();
  }
  if (typeof payload.intent === "string" && payload.intent.trim()) {
    task.intent = payload.intent.trim();
  }
  if (typeof payload.query === "string" && payload.query.trim()) {
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
        if (event.type === "status") {
          const message =
            typeof event.message === "string" && event.message.trim()
              ? event.message
              : "流程状态更新";
          progressLogs.value.push(message);

          const payload = event as Record<string, unknown>;
          const task = findTask(payload.task_id);
          if (task && message) {
            task.notices.push(message);
            applyNoteMetadata(task, payload);
          }
          return;
        }

        if (event.type === "todo_list") {
          const tasks = Array.isArray(event.tasks)
            ? (event.tasks as Record<string, unknown>[])
            : [];

          todoTasks.value = tasks.map((item, index) => createTaskView(item, index));

          if (todoTasks.value.length) {
            activeTaskId.value = todoTasks.value[0].id;
            progressLogs.value.push("已生成任务清单");
          } else {
            progressLogs.value.push("未生成任务清单，使用默认任务继续");
          }
          return;
        }

        if (event.type === "task_status") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }

          upsertTaskMetadata(task, payload);
          applyNoteMetadata(task, payload);
          const status =
            typeof event.status === "string" && event.status.trim()
              ? event.status.trim()
              : task.status;
          task.status = status;

          if (status === "in_progress") {
            task.summary = "";
            task.sourcesSummary = "";
            task.sourceItems = [];
            task.notices = [];
            activeTaskId.value = task.id;
            progressLogs.value.push(`开始执行任务：${task.title}`);
          } else if (status === "completed") {
            if (typeof event.summary === "string" && event.summary.trim()) {
              task.summary = event.summary.trim();
            }
            if (
              typeof event.sources_summary === "string" &&
              event.sources_summary.trim()
            ) {
              task.sourcesSummary = event.sources_summary.trim();
              task.sourceItems = parseSources(task.sourcesSummary);
            }
            progressLogs.value.push(`完成任务：${task.title}`);
            if (activeTaskId.value === task.id) {
              pulse(summaryHighlight);
              pulse(sourcesHighlight);
            }
          } else if (status === "skipped") {
            progressLogs.value.push(`任务跳过：${task.title}`);
          }
          return;
        }

        if (event.type === "sources") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }

          const textCandidates = [
            payload.latest_sources,
            payload.sources_summary,
            payload.raw_context
          ];
          const latestText = textCandidates
            .map((value) => (typeof value === "string" ? value.trim() : ""))
            .find((value) => value);

          if (latestText) {
            task.sourcesSummary = latestText;
            task.sourceItems = parseSources(latestText);
            if (activeTaskId.value === task.id) {
              pulse(sourcesHighlight);
            }
            progressLogs.value.push(`已更新任务来源：${task.title}`);
          }

          if (typeof payload.backend === "string") {
            progressLogs.value.push(
              `当前使用搜索后端：${payload.backend}`
            );
          }

          applyNoteMetadata(task, payload);

          return;
        }

        if (event.type === "task_summary_chunk") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }
          const chunk =
            typeof event.content === "string" ? event.content : "";
          task.summary += chunk;
          applyNoteMetadata(task, payload);
          if (activeTaskId.value === task.id) {
            pulse(summaryHighlight);
          }
          return;
        }

        if (event.type === "tool_call") {
          const payload = event as Record<string, unknown>;
          const eventId =
            typeof payload.event_id === "number"
              ? payload.event_id
              : Date.now();
          const agent =
            typeof payload.agent === "string" && payload.agent.trim()
              ? payload.agent.trim()
              : "Agent";
          const tool =
            typeof payload.tool === "string" && payload.tool.trim()
              ? payload.tool.trim()
              : "tool";
          const parameters = ensureRecord(payload.parameters);
          const result =
            typeof payload.result === "string" ? payload.result : "";
          const noteId = extractOptionalString(payload.note_id);
          const notePath = extractOptionalString(payload.note_path);

          const task = findTask(payload.task_id);
          if (task) {
            task.toolCalls.push({
              eventId,
              agent,
              tool,
              parameters,
              result,
              noteId,
              notePath,
              timestamp: Date.now()
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
            progressLogs.value.push(logSummary);
            if (activeTaskId.value === task.id) {
              pulse(toolHighlight);
            }
          } else {
            progressLogs.value.push(`${agent} 调用了 ${tool}`);
          }
          return;
        }

        if (event.type === "final_report") {
          const report =
            typeof event.report === "string" && event.report.trim()
              ? event.report.trim()
              : "";
          reportMarkdown.value = report || "报告生成失败，未获得有效内容";
          pulse(reportHighlight);
          progressLogs.value.push("最终报告已生成");
          // 报告写入 note 后刷新历史列表
          loadHistory();
          return;
        }

        if (event.type === "error") {
          const detail =
            typeof event.detail === "string" && event.detail.trim()
              ? event.detail
              : "研究过程中发生错误";
          error.value = detail;
          progressLogs.value.push("研究失败，已停止流程");
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
