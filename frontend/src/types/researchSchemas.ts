import { z } from "zod";

const streamBaseSchema = z.object({
  type: z.string(),
  run_id: z.string(),
  timestamp: z.string(),
  step: z.number().nullable().optional(),
  task_id: z.number().nullable().optional(),
  task_run_id: z.string().nullable().optional(),
  stream_token: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
  duration_ms: z.number().nullable().optional()
});

const todoTaskEventItemSchema = z
  .object({
    id: z.number().nullable().optional(),
    title: z.string(),
    intent: z.string(),
    status: z.string().nullable().optional(),
    summary: z.string().nullable().optional(),
    sources_summary: z.string().nullable().optional(),
    notices: z.array(z.string()).nullable().optional(),
    note_id: z.string().nullable().optional(),
    note_path: z.string().nullable().optional(),
    task_run_id: z.string().nullable().optional(),
    stream_token: z.string().nullable().optional()
  })
  .passthrough();

export const statusEventSchema = streamBaseSchema.extend({
  type: z.literal("status"),
  message: z.string()
});

export const todoListEventSchema = streamBaseSchema.extend({
  type: z.literal("todo_list"),
  tasks: z.array(todoTaskEventItemSchema)
});

export const sourcesEventSchema = streamBaseSchema.extend({
  type: z.literal("sources"),
  latest_sources: z.string(),
  raw_context: z.string().nullable().optional(),
  backend: z.string().nullable().optional(),
  note_id: z.string().nullable().optional(),
  note_path: z.string().nullable().optional()
});

export const taskSummaryChunkEventSchema = streamBaseSchema.extend({
  type: z.literal("task_summary_chunk"),
  content: z.string(),
  note_id: z.string().nullable().optional()
});

export const taskStatusEventSchema = streamBaseSchema.extend({
  type: z.literal("task_status"),
  status: z.enum(["pending", "in_progress", "completed", "skipped", "failed"]),
  title: z.string().nullable().optional(),
  intent: z.string().nullable().optional(),
  summary: z.string().nullable().optional(),
  sources_summary: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  note_id: z.string().nullable().optional(),
  note_path: z.string().nullable().optional()
});

export const toolCallEventSchema = streamBaseSchema.extend({
  type: z.literal("tool_call"),
  event_id: z.union([z.number(), z.string()]),
  agent: z.string().nullable().optional(),
  tool: z.string(),
  parameters: z
    .union([z.record(z.string(), z.unknown()), z.array(z.unknown()), z.string()])
    .nullable()
    .optional(),
  result: z.unknown().optional(),
  input_preview: z.string().nullable().optional(),
  output_preview: z.string().nullable().optional(),
  note_id: z.string().nullable().optional(),
  note_path: z.string().nullable().optional()
});

export const phaseDurationEventSchema = streamBaseSchema.extend({
  type: z.literal("phase_duration"),
  phase: z.enum(["planning", "search", "summary", "report", "total"])
});

export const reportNoteEventSchema = streamBaseSchema.extend({
  type: z.literal("report_note"),
  note_id: z.string(),
  title: z.string().nullable().optional(),
  content: z.string().nullable().optional(),
  note_path: z.string().nullable().optional()
});

export const finalReportEventSchema = streamBaseSchema.extend({
  type: z.literal("final_report"),
  report: z.string(),
  note_id: z.string().nullable().optional(),
  note_path: z.string().nullable().optional()
});

export const reviewResultEventSchema = streamBaseSchema.extend({
  type: z.literal("review_result"),
  passed: z.boolean(),
  score: z.number().min(0).max(100),
  issues: z.array(z.string()).optional(),
  suggestions: z.array(z.string()).optional()
});

export const factCheckResultEventSchema = streamBaseSchema.extend({
  type: z.literal("fact_check_result"),
  passed: z.boolean(),
  score: z.number().min(0).max(100),
  matched_sources: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
  missing_terms: z.array(z.string()).optional()
});

export const skillLoadedEventSchema = streamBaseSchema.extend({
  type: z.literal("skill_loaded"),
  skill_name: z.string(),
  skill_description: z.string().nullable().optional(),
  preview: z.string().nullable().optional()
});

export const doneEventSchema = streamBaseSchema.extend({
  type: z.literal("done")
});

export const errorEventSchema = streamBaseSchema.extend({
  type: z.literal("error"),
  detail: z.string()
});

export const researchStreamEventSchema = z.discriminatedUnion("type", [
  statusEventSchema,
  todoListEventSchema,
  sourcesEventSchema,
  taskSummaryChunkEventSchema,
  taskStatusEventSchema,
  toolCallEventSchema,
  reportNoteEventSchema,
  finalReportEventSchema,
  reviewResultEventSchema,
  factCheckResultEventSchema,
  skillLoadedEventSchema,
  phaseDurationEventSchema,
  doneEventSchema,
  errorEventSchema
]);

export type ParsedResearchStreamEvent = z.infer<typeof researchStreamEventSchema>;

export function parseResearchStreamEvent(payload: unknown): ParsedResearchStreamEvent | null {
  const result = researchStreamEventSchema.safeParse(payload);
  if (!result.success) {
    console.warn("SSE 事件校验失败：", result.error.flatten(), payload);
    return null;
  }
  return result.data;
}