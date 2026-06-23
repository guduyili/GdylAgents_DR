export interface TaskChannelRef {
  id: number;
  taskRunId: string | null;
  streamToken: string | null;
}

export interface TaskChannelEvent {
  task_id?: number | null;
  task_run_id?: string | null;
  stream_token?: string | null;
}

export function resolveTaskForEvent<T extends TaskChannelRef>(
  tasks: T[],
  event: TaskChannelEvent
): T | undefined {
  const streamToken = event.stream_token?.trim();
  if (streamToken) {
    const byToken = tasks.find((task) => task.streamToken === streamToken);
    if (byToken) {
      return byToken;
    }
  }

  const taskRunId = event.task_run_id?.trim();
  if (taskRunId) {
    const byRunId = tasks.find((task) => task.taskRunId === taskRunId);
    if (byRunId) {
      return byRunId;
    }
  }

  const taskId = event.task_id;
  if (typeof taskId === "number" && Number.isFinite(taskId)) {
    return tasks.find((task) => task.id === taskId);
  }

  return undefined;
}