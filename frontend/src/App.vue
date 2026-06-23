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
        v-model:research-mode="form.researchMode"
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
        :trace-task-filter="traceTaskFilter"
        :phase-durations="phaseDurations"
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
        :review-result="reviewResult"
        :sources-summary-open="sourcesSummaryOpen"
        :summary-highlight="summaryHighlight"
        :sources-highlight="sourcesHighlight"
        :report-highlight="reportHighlight"
        :tool-highlight="toolHighlight"
        :format-task-status="formatTaskStatus"
        :format-tool-parameters="formatToolParameters"
        :format-tool-result="formatToolResult"
        :copy-note-path="copyNotePath"
        @toggle-logs="logsCollapsed = !logsCollapsed"
        @update:timeline-filter="timelineFilter = $event"
        @download-report="downloadReport"
        @select-task="activeTaskId = $event"
        @toggle-sources-summary="sourcesSummaryOpen = !sourcesSummaryOpen"
        @update:trace-task-filter="traceTaskFilter = $event"
        @replay-timeline="replayTimelineFromSnapshot"
        @skip-task="skipTask"
        @retry-task="retryTask"
      />
    </div>
  </main>
</template>

<script lang="ts" setup>
import { onMounted, reactive } from "vue";
import "./styles/app.css";
import ResearchForm from "./components/ResearchForm.vue";
import PlanEditor from "./components/PlanEditor.vue";
import HistoryPage from "./components/HistoryPage.vue";
import ResearchSidebar from "./components/ResearchSidebar.vue";
import ResearchBoard from "./components/ResearchBoard.vue";
import { useHistoryReports } from "./composables/useHistoryReports";
import { useResearchWorkflow } from "./composables/useResearchWorkflow";
import { renderReportHtml } from "./utils/reportMarkdown";

const form = reactive({
  topic: "",
  searchApi: "",
  researchMode: "deep" as "deep" | "quick"
});

const {
  historyReports,
  historyLoading,
  selectedReport,
  historyPageOpen,
  loadHistory,
  openHistoryPage,
  closeHistoryPage,
  openReport
} = useHistoryReports();

const {
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
  downloadReport,
  cancelResearch,
  goBack,
  startNewResearch,
  skipTask,
  retryTask
} = useResearchWorkflow(form, { onHistoryRefresh: loadHistory });

const searchOptions = ["advanced", "duckduckgo", "tavily", "perplexity", "searxng"];

function renderMd(src: string): string {
  return renderReportHtml(src);
}

onMounted(() => {
  void loadHistory();
});
</script>