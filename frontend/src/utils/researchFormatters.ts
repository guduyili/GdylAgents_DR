const TASK_STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  in_progress: "进行中",
  completed: "已完成",
  skipped: "已跳过",
  failed: "失败"
};

export function formatTaskStatus(status: string): string {
  return TASK_STATUS_LABEL[status] ?? status;
}

export function formatToolParameters(parameters: Record<string, unknown>): string {
  try {
    return JSON.stringify(parameters, null, 2);
  } catch (error) {
    console.warn("无法格式化工具参数", error, parameters);
    return Object.entries(parameters)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join("\n");
  }
}

export function formatToolResult(result: string): string {
  const trimmed = result.trim();
  const limit = 900;
  if (trimmed.length > limit) {
    return `${trimmed.slice(0, limit)}…`;
  }
  return trimmed;
}

export function formatEventTime(timestamp: unknown): string {
  if (typeof timestamp !== "string" || !timestamp.trim()) {
    return new Date().toLocaleTimeString();
  }
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp.trim();
  }
  return parsed.toLocaleTimeString();
}

export function ensureRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}