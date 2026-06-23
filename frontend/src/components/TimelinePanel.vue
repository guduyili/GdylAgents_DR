<template>
  <section class="timeline-card workspace-card" v-show="!collapsed && events.length">
    <div class="card-title-row">
      <div>
        <p class="card-kicker">Timeline</p>
        <h3>流程动态</h3>
      </div>
      <span class="status-meta">{{ visibleEvents.length }} 条记录</span>
    </div>

    <div v-if="phaseRows.length" class="phase-duration-row">
      <span
        v-for="row in phaseRows"
        :key="row.phase"
        class="phase-duration-chip"
      >{{ row.label }}：{{ row.labelValue }}</span>
    </div>

    <div class="timeline-filters">
      <button
        v-for="opt in TIMELINE_FILTER_OPTIONS"
        :key="opt.value"
        :class="['filter-chip', { active: filter === opt.value }]"
        @click="$emit('update:filter', opt.value)"
      >{{ opt.label }}</button>
    </div>
    <div class="timeline-wrapper">
      <transition-group name="timeline" tag="ul" class="timeline">
        <TimelineEventItem
          v-for="event in events"
          :key="event.id"
          :event="event"
          :visible="timelineEventVisible(event)"
        />
      </transition-group>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TimelineEventItem from "./TimelineEventItem.vue";
import type { TimelineEventView } from "../types/view";

const props = defineProps<{
  events: TimelineEventView[];
  filter: string;
  collapsed: boolean;
  taskFilter: number | null;
  phaseDurations: Record<string, number>;
}>();

defineEmits<{
  "update:filter": [filter: string];
}>();

const TIMELINE_FILTER_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "task_status", label: "任务" },
  { value: "tool_call", label: "工具" },
  { value: "sources", label: "来源" },
  { value: "final_report", label: "报告" },
  { value: "phase_duration", label: "耗时" },
] as const;

const PHASE_LABELS: Record<string, string> = {
  planning: "规划",
  search: "搜索",
  summary: "总结",
  report: "报告",
  total: "全流程"
};

const phaseRows = computed(() => {
  const order = ["planning", "search", "summary", "report", "total"] as const;
  return order
    .filter((phase) => typeof props.phaseDurations[phase] === "number")
    .map((phase) => ({
      phase,
      label: PHASE_LABELS[phase],
      labelValue: formatDuration(props.phaseDurations[phase])
    }));
});

const visibleEvents = computed(() =>
  props.events.filter((event) => timelineEventVisible(event))
);

function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

function timelineEventTypeMatches(eventType: string, filter: string): boolean {
  if (filter === "all") return true;
  if (filter === "task_status") {
    return ["task_status", "status", "todo_list"].includes(eventType);
  }
  if (filter === "tool_call") return eventType === "tool_call";
  if (filter === "sources") return eventType === "sources";
  if (filter === "final_report") return ["final_report", "report_note"].includes(eventType);
  if (filter === "phase_duration") return eventType === "phase_duration";
  return true;
}

function timelineEventVisible(event: TimelineEventView): boolean {
  if (props.taskFilter !== null && event.taskId !== null && event.taskId !== props.taskFilter) {
    return false;
  }
  return timelineEventTypeMatches(event.type, props.filter);
}
</script>