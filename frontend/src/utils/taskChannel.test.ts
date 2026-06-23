import { describe, expect, it } from "vitest";

import { resolveTaskForEvent } from "./taskChannel";

describe("resolveTaskForEvent", () => {
  const tasks = [
    { id: 1, taskRunId: "run-1:task:1", streamToken: "task_1" },
    { id: 2, taskRunId: "run-1:task:2", streamToken: "task_2" },
    { id: 3, taskRunId: "run-1:task:3", streamToken: "task_3" }
  ];

  it("prefers stream_token over task_id when ids collide across runs", () => {
    const resolved = resolveTaskForEvent(tasks, {
      task_id: 1,
      task_run_id: "run-1:task:2",
      stream_token: "task_2"
    });

    expect(resolved?.id).toBe(2);
  });

  it("falls back to task_run_id when stream_token is missing", () => {
    const resolved = resolveTaskForEvent(tasks, {
      task_id: 1,
      task_run_id: "run-1:task:3"
    });

    expect(resolved?.id).toBe(3);
  });

  it("falls back to task_id when channel fields are absent", () => {
    const resolved = resolveTaskForEvent(tasks, { task_id: 2 });

    expect(resolved?.id).toBe(2);
  });

  it("routes concurrent chunks to distinct tasks by stream_token", () => {
    const chunks = [
      { task_id: 1, stream_token: "task_1", content: "A" },
      { task_id: 2, stream_token: "task_2", content: "B" },
      { task_id: 1, stream_token: "task_1", content: "C" }
    ];

    const summaries = new Map<number, string>();
    for (const chunk of chunks) {
      const task = resolveTaskForEvent(tasks, chunk);
      expect(task).toBeDefined();
      summaries.set(task!.id, `${summaries.get(task!.id) || ""}${chunk.content}`);
    }

    expect(summaries.get(1)).toBe("AC");
    expect(summaries.get(2)).toBe("B");
  });
});