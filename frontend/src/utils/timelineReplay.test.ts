import { describe, expect, it } from "vitest";

import { buildTimelineFromSnapshot } from "./timelineReplay";

describe("buildTimelineFromSnapshot", () => {
  it("rebuilds phase durations and tool previews from snapshot events", () => {
    const replay = buildTimelineFromSnapshot({
      run_id: "run-1",
      topic: "AI Agent",
      status: "completed",
      phase_durations: { planning: 100 },
      events: [
        {
          type: "phase_duration",
          phase: "search",
          duration_ms: 1200,
          run_id: "run-1",
          timestamp: "2026-06-13T12:00:00Z"
        },
        {
          type: "tool_call",
          event_id: 1,
          tool: "note",
          agent: "规划专家",
          input_preview: "preview-in",
          output_preview: "preview-out",
          parameters: { action: "create" },
          result: "ok",
          run_id: "run-1",
          timestamp: "2026-06-13T12:00:01Z"
        }
      ]
    });

    expect(replay.phaseDurations.search).toBe(1200);
    expect(replay.timelineEvents).toHaveLength(2);
    expect(replay.timelineEvents[1].inputPreview).toBe("preview-in");
    expect(replay.timelineEvents[1].toolDetail).toContain("create");
  });
});