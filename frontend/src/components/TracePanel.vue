<template>
  <section class="trace-panel workspace-card" v-if="runId || events.length">
    <div class="card-title-row">
      <div>
        <p class="card-kicker">Trace</p>
        <h3>链路追踪</h3>
      </div>
      <span class="status-meta">{{ filteredEvents.length }} / {{ events.length }} 个事件</span>
    </div>

    <dl class="trace-grid">
      <div>
        <dt>Run ID</dt>
        <dd>{{ runId || "-" }}</dd>
      </div>
      <div>
        <dt>Task Run</dt>
        <dd>{{ latestTaskRunId || "-" }}</dd>
      </div>
      <div>
        <dt>Stream Token</dt>
        <dd>{{ latestStreamToken || "-" }}</dd>
      </div>
      <div>
        <dt>总耗时</dt>
        <dd>{{ totalDurationLabel }}</dd>
      </div>
    </dl>

    <div class="trace-controls">
      <label class="trace-filter">
        <span>按任务过滤</span>
        <select :value="taskFilter ?? ''" @change="onTaskFilterChange">
          <option value="">全部任务</option>
          <option v-for="task in taskOptions" :key="task.id" :value="String(task.id)">
            任务 {{ task.id }} · {{ task.title }}
          </option>
        </select>
      </label>

      <div class="trace-actions">
        <button class="secondary-btn" type="button" :disabled="!runId || exporting" @click="exportSnapshot">
          {{ exporting ? "导出中…" : "导出 JSON" }}
        </button>
        <button class="secondary-btn" type="button" :disabled="!runId || replaying" @click="replayFromServer">
          {{ replaying ? "重放中…" : "重放运行" }}
        </button>
        <label class="secondary-btn trace-upload-btn">
          导入重放
          <input class="trace-upload-input" type="file" accept="application/json,.json" @change="onImportReplay" />
        </label>
      </div>
    </div>

    <p v-if="actionMessage" class="trace-action-message">{{ actionMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { getResearchRun } from "../services/api";
import type { ResearchRunSnapshot } from "../types/research";
import type { TimelineEventView } from "../types/view";
import { downloadJsonSnapshot } from "../utils/timelineReplay";

interface TaskOption {
  id: number;
  title: string;
}

const props = defineProps<{
  runId: string | null;
  events: TimelineEventView[];
  taskOptions: TaskOption[];
  taskFilter: number | null;
}>();

const emit = defineEmits<{
  "update:task-filter": [value: number | null];
  replay: [snapshot: ResearchRunSnapshot];
}>();

const exporting = ref(false);
const replaying = ref(false);
const actionMessage = ref("");

const filteredEvents = computed(() => {
  if (props.taskFilter === null) {
    return props.events;
  }
  return props.events.filter((event) => event.taskId === props.taskFilter);
});

const latestTaskRunId = computed(() => {
  for (let index = filteredEvents.value.length - 1; index >= 0; index -= 1) {
    const value = filteredEvents.value[index].taskRunId;
    if (value) return value;
  }
  return "";
});

const latestStreamToken = computed(() => {
  for (let index = filteredEvents.value.length - 1; index >= 0; index -= 1) {
    const value = filteredEvents.value[index].streamToken;
    if (value) return value;
  }
  return "";
});

const totalDurationLabel = computed(() => {
  const done = [...props.events].reverse().find((event) => event.type === "done" && typeof event.durationMs === "number");
  if (typeof done?.durationMs === "number") {
    return `${done.durationMs}ms`;
  }
  const totalPhase = [...props.events].reverse().find((event) => event.type === "phase_duration" && event.phase === "total");
  if (typeof totalPhase?.durationMs === "number") {
    return `${totalPhase.durationMs}ms`;
  }
  return "-";
});

function onTaskFilterChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  emit("update:task-filter", value ? Number(value) : null);
}

async function exportSnapshot() {
  if (!props.runId) {
    return;
  }
  exporting.value = true;
  actionMessage.value = "";
  try {
    const snapshot = await getResearchRun(props.runId);
    if (!snapshot) {
      actionMessage.value = "未找到可导出的运行记录。";
      return;
    }
    downloadJsonSnapshot(snapshot);
    actionMessage.value = "运行快照已导出。";
  } catch (error) {
    console.warn("导出运行快照失败", error);
    actionMessage.value = "导出失败，请稍后重试。";
  } finally {
    exporting.value = false;
  }
}

async function replayFromServer() {
  if (!props.runId) {
    return;
  }
  replaying.value = true;
  actionMessage.value = "";
  try {
    const snapshot = await getResearchRun(props.runId);
    if (!snapshot) {
      actionMessage.value = "未找到可重放的运行记录。";
      return;
    }
    emit("replay", snapshot);
    actionMessage.value = `已重放 ${snapshot.events.length} 条事件。`;
  } catch (error) {
    console.warn("重放运行失败", error);
    actionMessage.value = "重放失败，请稍后重试。";
  } finally {
    replaying.value = false;
  }
}

async function onImportReplay(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) {
    return;
  }

  actionMessage.value = "";
  try {
    const text = await file.text();
    const snapshot = JSON.parse(text) as ResearchRunSnapshot;
    if (!snapshot || !Array.isArray(snapshot.events)) {
      actionMessage.value = "导入文件不是有效的运行快照。";
      return;
    }
    emit("replay", snapshot);
    actionMessage.value = `已从文件重放 ${snapshot.events.length} 条事件。`;
  } catch (error) {
    console.warn("导入重放失败", error);
    actionMessage.value = "导入重放失败，请检查 JSON 文件。";
  }
}
</script>