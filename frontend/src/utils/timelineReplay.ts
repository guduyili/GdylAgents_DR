import type { ResearchRunSnapshot, ResearchStreamEvent } from "../types/research";
import type { TimelineEventView } from "../types/view";

const PHASE_LABELS: Record<string, string> = {
  planning: "规划",
  search: "搜索",
  summary: "总结",
  report: "报告",
  total: "全流程"
};

export function snapshotEventMessage(event: ResearchStreamEvent): string {
  switch (event.type) {
    case "status":
      return event.message.trim() || "流程状态更新";
    case "todo_list":
      return `任务清单（${event.tasks.length} 项）`;
    case "sources":
      return `来源更新（任务 ${event.task_id ?? "-"}）`;
    case "task_summary_chunk":
      return `摘要流式输出（任务 ${event.task_id ?? "-"}）`;
    case "task_status":
      return `任务 ${event.task_id ?? "-"} → ${event.status}`;
    case "tool_call":
      return `${event.agent?.trim() || "Agent"} 调用 ${event.tool}`;
    case "report_note":
      return event.title?.trim() ? `报告笔记：${event.title.trim()}` : "报告笔记已保存";
    case "final_report":
      return "最终报告已生成";
    case "phase_duration":
      return `阶段耗时 ${PHASE_LABELS[event.phase] || event.phase}：${event.duration_ms ?? 0}ms`;
    case "done":
      return "研究流程完成";
    case "error":
      return `错误：${event.detail}`;
    default:
      return "事件回放";
  }
}

export function buildTimelineFromSnapshot(snapshot: ResearchRunSnapshot): {
  timelineEvents: TimelineEventView[];
  progressLogs: string[];
  phaseDurations: Record<string, number>;
  runId: string | null;
} {
  const timelineEvents: TimelineEventView[] = [];
  const progressLogs: string[] = [];
  const phaseDurations: Record<string, number> = { ...(snapshot.phase_durations || {}) };

  snapshot.events.forEach((event, index) => {
    const message = snapshotEventMessage(event);
    const log = `[回放] ${message}`;
    progressLogs.push(log);
    timelineEvents.push({
      id: `${event.run_id || snapshot.run_id}-${index}`,
      type: event.type,
      message,
      log,
      timestamp: event.timestamp,
      runId: event.run_id || snapshot.run_id,
      taskId: typeof event.task_id === "number" ? event.task_id : null,
      taskRunId: event.task_run_id || null,
      streamToken: event.stream_token || null,
      source: event.source || null,
      step: typeof event.step === "number" ? event.step : null,
      durationMs: typeof event.duration_ms === "number" ? event.duration_ms : null,
      phase: event.type === "phase_duration" ? event.phase : null,
      inputPreview: event.type === "tool_call" ? event.input_preview || null : null,
      outputPreview: event.type === "tool_call" ? event.output_preview || null : null,
      toolDetail:
        event.type === "tool_call"
          ? JSON.stringify(
              { parameters: event.parameters ?? null, result: event.result ?? null },
              null,
              2
            )
          : null
    });

    if (event.type === "phase_duration" && typeof event.duration_ms === "number") {
      phaseDurations[event.phase] = event.duration_ms;
    }
  });

  return {
    timelineEvents,
    progressLogs,
    phaseDurations,
    runId: snapshot.run_id || null
  };
}

export function downloadJsonSnapshot(snapshot: ResearchRunSnapshot, filename?: string): void {
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || `research-run-${snapshot.run_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}