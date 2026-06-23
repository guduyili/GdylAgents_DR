<template>
  <section class="panel panel-result research-board" v-if="todoTasks.length || reportMarkdown || progressLogs.length">
    <header class="status-bar board-hero">
      <div>
        <p class="card-kicker">Research Workspace</p>
        <h2>卡片化研究工作台</h2>
        <p class="board-subtitle">任务、来源、笔记、工具调用与报告按研究阶段拆分展示。</p>
        <p v-if="currentRunId" class="run-id-chip">Run ID：{{ currentRunId }}</p>
      </div>
      <div class="status-controls">
        <div class="status-chip" :class="{ active: loading }">
          <span class="dot"></span>
          {{ loading ? "研究进行中" : "研究流程完成" }}
        </div>
        <button class="secondary-btn" @click="$emit('toggle-logs')">
          {{ logsCollapsed ? "展开流程" : "收起流程" }}
        </button>

      </div>
    </header>

    <section class="research-overview-grid">
      <article class="metric-card primary">
        <span>任务进度</span>
        <strong>{{ completedTasks }} / {{ totalTasks || todoTasks.length || 1 }}</strong>
        <p>已完成任务</p>
      </article>
      <article class="metric-card">
        <span>流程记录</span>
        <strong>{{ progressLogs.length }}</strong>
        <p>实时事件</p>
      </article>
      <article class="metric-card">
        <span>当前任务</span>
        <strong>{{ currentTaskTitle || "等待中" }}</strong>
        <p>{{ currentTask ? formatTaskStatus(currentTask.status) : "未开始" }}</p>
      </article>
      <article class="metric-card">
        <span>报告状态</span>
        <strong>{{ reportMarkdown ? "已生成" : loading ? "生成中" : "待生成" }}</strong>
        <p>{{ searchApi || "后端默认搜索" }}</p>
      </article>
    </section>

    <TracePanel
      :run-id="currentRunId"
      :events="timelineEvents"
      :task-options="taskFilterOptions"
      :task-filter="traceTaskFilter"
      @update:task-filter="$emit('update:trace-task-filter', $event)"
      @replay="$emit('replay-timeline', $event)"
    />

    <TimelinePanel
      :events="timelineEvents"
      :filter="timelineFilter"
      :collapsed="logsCollapsed"
      :task-filter="traceTaskFilter"
      :phase-durations="phaseDurations"
      @update:filter="$emit('update:timeline-filter', $event)"
    />

    <section class="task-card-board" v-if="todoTasks.length">
      <button
        v-for="task in todoTasks"
        :key="task.id"
        type="button"
        :class="['task-card', task.status, { active: task.id === activeTaskId }]"
        @click="$emit('select-task', task.id)"
      >
        <div class="task-card-head">
          <span class="task-index">任务 {{ task.id }}</span>
          <span class="task-status" :class="task.status">{{ formatTaskStatus(task.status) }}</span>
        </div>
        <h3>{{ task.title }}</h3>
        <p>{{ task.intent }}</p>
        <div class="task-query">Query：{{ task.query }}</div>
        <div class="task-card-meta">
          <span>{{ task.sourceItems.length }} 个来源</span>
          <span>{{ task.toolCalls.length }} 次工具</span>
          <span v-if="task.noteId">已写笔记</span>
        </div>
        <div class="task-card-actions" @click.stop>
          <button
            type="button"
            class="chip-action"
            :disabled="loading || task.status === 'in_progress'"
            @click="$emit('retry-task', task.id)"
          >
            重新执行
          </button>
          <button
            type="button"
            class="chip-action"
            :disabled="loading || task.status === 'completed' || task.status === 'skipped'"
            @click="$emit('skip-task', task.id)"
          >
            跳过
          </button>
        </div>
      </button>
    </section>

    <section class="focus-grid" v-if="currentTask">
      <article class="task-detail task-focus-card workspace-card">
        <header class="task-header">
          <div>
            <p class="card-kicker">Current Task</p>
            <h3>{{ currentTaskTitle || "当前任务" }}</h3>
            <p class="muted" v-if="currentTaskIntent">{{ currentTaskIntent }}</p>
          </div>
          <span class="task-status" :class="currentTask.status">{{ formatTaskStatus(currentTask.status) }}</span>
        </header>

        <div class="task-chip-group">
          <span class="task-label">查询：{{ currentTaskQuery || "" }}</span>
          <span v-if="currentTaskNoteId" class="task-label note-chip" :title="currentTaskNoteId">
            笔记：{{ currentTaskNoteId }}
          </span>
          <span v-if="currentTaskNotePath" class="task-label note-chip path-chip" :title="currentTaskNotePath">
            <span class="path-label">路径：</span>
            <span class="path-text">{{ currentTaskNotePath }}</span>
            <button class="chip-action" type="button" @click="copyNotePath(currentTaskNotePath)">复制</button>
          </span>
        </div>

        <section v-if="currentTask.notices.length" class="task-notices">
          <h4>系统提示</h4>
          <ul>
            <li v-for="(notice, idx) in currentTask.notices" :key="`${notice}-${idx}`">{{ notice }}</li>
          </ul>
        </section>

        <section v-if="currentTask.loadedSkills.length" class="skill-block workspace-card">
          <h4>已加载 Skill</h4>
          <ul class="skill-chip-list">
            <li v-for="skill in currentTask.loadedSkills" :key="skill.name" class="skill-chip">
              <strong>{{ skill.name }}</strong>
              <p v-if="skill.description" class="muted">{{ skill.description }}</p>
              <p v-if="skill.preview" class="skill-preview">{{ skill.preview }}</p>
            </li>
          </ul>
        </section>

        <section
          v-if="currentTask.factCheck"
          class="fact-check-card workspace-card"
          :class="{ passed: currentTask.factCheck.passed, failed: !currentTask.factCheck.passed }"
        >
          <div class="card-title-row">
            <h4>事实核对</h4>
            <span class="review-score">得分 {{ currentTask.factCheck.score }}</span>
          </div>
          <p>{{ currentTask.factCheck.passed ? "核对通过" : "建议复核以下项" }}</p>
          <ul v-if="currentTask.factCheck.warnings.length">
            <li v-for="(warning, idx) in currentTask.factCheck.warnings" :key="`warn-${idx}`">{{ warning }}</li>
          </ul>
          <ul v-if="currentTask.factCheck.missingTerms.length">
            <li v-for="(term, idx) in currentTask.factCheck.missingTerms" :key="`term-${idx}`">
              未在来源中匹配：{{ term }}
            </li>
          </ul>
        </section>

        <section class="summary-block" :class="{ 'block-highlight': summaryHighlight }">
          <div class="card-title-row">
            <div>
              <p class="card-kicker">Summary</p>
              <h3>任务总结</h3>
            </div>
          </div>
          <pre class="block-pre">{{ currentTaskSummary || "暂无可用信息" }}</pre>
        </section>
      </article>

      <aside class="focus-side">
        <section class="sources-block workspace-card" :class="{ 'block-highlight': sourcesHighlight }">
          <div class="card-title-row">
            <div>
              <p class="card-kicker">Sources</p>
              <h3>最新来源</h3>
            </div>
            <span class="status-meta">
              {{ currentTaskSources.length }} 条
              <template v-if="currentTask.searchBackend"> · {{ currentTask.searchBackend }}</template>
            </span>
          </div>
          <template v-if="currentTaskSources.length">
            <ul class="sources-list source-card-list">
              <li v-for="(item, index) in currentTaskSources" :key="`${item.title}-${index}`" class="source-item source-card">
                <a class="source-link" :href="item.url || '#'" target="_blank" rel="noopener noreferrer">
                  {{ item.title || item.url || `来源 ${index + 1}` }}
                </a>
                <p v-if="item.snippet" class="source-snippet">{{ item.snippet }}</p>
                <div v-if="item.raw" class="source-tooltip">
                  <p class="muted-text">{{ item.raw }}</p>
                </div>
              </li>
            </ul>
          </template>
          <p v-else class="muted">暂无可用来源</p>
        </section>

        <section v-if="currentTask.sourcesSummary" class="sources-summary-block workspace-card">
          <button class="collapsible-header" type="button" @click="$emit('toggle-sources-summary')">
            <span>来源摘要</span>
            <span>{{ sourcesSummaryOpen ? '▲' : '▼' }}</span>
          </button>
          <div v-show="sourcesSummaryOpen" class="collapsible-body">
            <pre class="block-pre">{{ currentTask.sourcesSummary }}</pre>
          </div>
        </section>

        <section class="tools-block workspace-card" :class="{ 'block-highlight': toolHighlight }" v-if="currentTaskToolCalls.length">
          <div class="card-title-row">
            <div>
              <p class="card-kicker">Tools</p>
              <h3>工具调用记录</h3>
            </div>
            <span class="status-meta">{{ currentTaskToolCalls.length }} 次</span>
          </div>
          <ul class="tool-list">
            <li v-for="entry in currentTaskToolCalls" :key="`${entry.eventId}-${entry.timestamp}`" class="tool-entry">
              <div class="tool-entry-header">
                <span class="tool-entry-title">#{{ entry.eventId }} {{ entry.agent }} → {{ entry.tool }}</span>
                <span v-if="entry.noteId" class="tool-entry-note">笔记：{{ entry.noteId }}</span>
              </div>
              <p v-if="entry.notePath" class="tool-entry-path">
                笔记路径：
                <button class="link-btn" type="button" @click="copyNotePath(entry.notePath)">复制</button>
                <span class="path-text">{{ entry.notePath }}</span>
              </p>
              <template v-if="entry.inputPreview || entry.outputPreview">
                <p v-if="entry.inputPreview" class="tool-subtitle">输入预览</p>
                <pre v-if="entry.inputPreview" class="tool-pre">{{ entry.inputPreview }}</pre>
                <p v-if="entry.outputPreview" class="tool-subtitle">输出预览</p>
                <pre v-if="entry.outputPreview" class="tool-pre">{{ entry.outputPreview }}</pre>
              </template>
              <p class="tool-subtitle">参数</p>
              <pre class="tool-pre">{{ formatToolParameters(entry.parameters) }}</pre>
              <template v-if="entry.result">
                <p class="tool-subtitle">执行结果</p>
                <pre class="tool-pre">{{ formatToolResult(entry.result) }}</pre>
              </template>
            </li>
          </ul>
        </section>
      </aside>
    </section>

    <article class="empty-card workspace-card" v-else>
      <p class="muted">等待任务规划或执行结果。</p>
    </article>

    <ReportViewer
      v-if="reportMarkdown"
      :markdown="reportMarkdown"
      :highlight="reportHighlight"
      @download="$emit('download-report')"
    />

    <article v-if="reviewResult" class="review-card workspace-card" :class="{ passed: reviewResult.passed, failed: !reviewResult.passed }">
      <div class="card-title-row">
        <div>
          <p class="card-kicker">Review</p>
          <h3>报告评审</h3>
        </div>
        <span class="review-score">得分 {{ reviewResult.score }}</span>
      </div>
      <p class="review-verdict">{{ reviewResult.passed ? "评审通过" : "评审建议改进" }}</p>
      <section v-if="reviewResult.issues.length" class="review-section">
        <h4>问题</h4>
        <ul>
          <li v-for="(issue, idx) in reviewResult.issues" :key="`issue-${idx}`">{{ issue }}</li>
        </ul>
      </section>
      <section v-if="reviewResult.suggestions.length" class="review-section">
        <h4>建议</h4>
        <ul>
          <li v-for="(suggestion, idx) in reviewResult.suggestions" :key="`suggestion-${idx}`">{{ suggestion }}</li>
        </ul>
      </section>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TimelinePanel from "./TimelinePanel.vue";
import TracePanel from "./TracePanel.vue";
import ReportViewer from "./ReportViewer.vue";
import type { ResearchRunSnapshot } from "../types/research";
import type { ReviewResultView, SourceItem, TimelineEventView, TodoTaskView, ToolCallLog } from "../types/view";

const props = defineProps<{
  todoTasks: TodoTaskView[];
  reportMarkdown: string;
  reviewResult: ReviewResultView | null;
  progressLogs: string[];
  currentRunId: string | null;
  timelineEvents: TimelineEventView[];
  timelineFilter: string;
  traceTaskFilter: number | null;
  phaseDurations: Record<string, number>;
  loading: boolean;
  logsCollapsed: boolean;
  completedTasks: number;
  totalTasks: number;
  currentTask: TodoTaskView | null;
  currentTaskTitle: string;
  currentTaskIntent: string;
  currentTaskQuery: string;
  currentTaskNoteId: string;
  currentTaskNotePath: string;
  currentTaskSources: SourceItem[];
  currentTaskSummary: string;
  currentTaskToolCalls: ToolCallLog[];
  activeTaskId: number | null;
  searchApi: string;
  sourcesSummaryOpen: boolean;
  summaryHighlight: boolean;
  sourcesHighlight: boolean;
  reportHighlight: boolean;
  toolHighlight: boolean;
  formatTaskStatus: (status: string) => string;
  formatToolParameters: (parameters: Record<string, unknown>) => string;
  formatToolResult: (result: string) => string;
  copyNotePath: (path: string | null | undefined) => Promise<void>;
}>();

defineEmits<{
  "toggle-logs": [];
  "download-report": [];
  "select-task": [taskId: number];
  "toggle-sources-summary": [];
  "update:timeline-filter": [filter: string];
  "update:trace-task-filter": [taskId: number | null];
  "replay-timeline": [snapshot: ResearchRunSnapshot];
  "skip-task": [taskId: number];
  "retry-task": [taskId: number];
}>();

const taskFilterOptions = computed(() =>
  props.todoTasks.map((task) => ({
    id: task.id,
    title: task.title
  }))
);
</script>
