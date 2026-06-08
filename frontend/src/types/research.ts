export interface ResearchRequest {
  topic: string;
  search_api?: string;
  todo_items?: ResearchTodoItem[];
}

export interface ResearchTodoItem {
  id?: number;
  title: string;
  intent: string;
  query: string;
}

export interface ResearchPlanResponse {
  topic: string;
  todo_items: ResearchTodoItem[];
}

export interface StreamBaseEvent {
  type: string;
  run_id: string;
  timestamp: string;
  step?: number | null;
  task_id?: number | null;
  task_run_id?: string | null;
  stream_token?: string | null;
}

export interface StatusEvent extends StreamBaseEvent {
  type: "status";
  message: string;
}

export interface TodoTaskEventItem {
  id?: number | null;
  title: string;
  intent: string;
  status?: string | null;
  summary?: string | null;
  sources_summary?: string | null;
  notices?: string[] | null;
  note_id?: string | null;
  note_path?: string | null;
  task_run_id?: string | null;
  stream_token?: string | null;
}

export interface TodoListEvent extends StreamBaseEvent {
  type: "todo_list";
  tasks: TodoTaskEventItem[];
}

export interface SourcesEvent extends StreamBaseEvent {
  type: "sources";
  latest_sources: string;
  raw_context?: string | null;
  backend?: string | null;
  note_id?: string | null;
  note_path?: string | null;
}

export interface TaskSummaryChunkEvent extends StreamBaseEvent {
  type: "task_summary_chunk";
  content: string;
  note_id?: string | null;
}

export interface TaskStatusEvent extends StreamBaseEvent {
  type: "task_status";
  status: "pending" | "in_progress" | "completed" | "skipped" | "failed";
  title?: string | null;
  intent?: string | null;
  summary?: string | null;
  sources_summary?: string | null;
  error?: string | null;
  note_id?: string | null;
  note_path?: string | null;
}

export interface ToolCallEvent extends StreamBaseEvent {
  type: "tool_call";
  event_id: number | string;
  agent?: string | null;
  tool: string;
  parameters?: Record<string, unknown> | unknown[] | string | null;
  result?: unknown;
  note_id?: string | null;
  note_path?: string | null;
}

export interface ReportNoteEvent extends StreamBaseEvent {
  type: "report_note";
  note_id: string;
  title?: string | null;
  content?: string | null;
  note_path?: string | null;
}

export interface FinalReportEvent extends StreamBaseEvent {
  type: "final_report";
  report: string;
  note_id?: string | null;
  note_path?: string | null;
}

export interface DoneEvent extends StreamBaseEvent {
  type: "done";
}

export interface ErrorEvent extends StreamBaseEvent {
  type: "error";
  detail: string;
}

export type ResearchStreamEvent =
  | StatusEvent
  | TodoListEvent
  | SourcesEvent
  | TaskSummaryChunkEvent
  | TaskStatusEvent
  | ToolCallEvent
  | ReportNoteEvent
  | FinalReportEvent
  | DoneEvent
  | ErrorEvent;

export interface StreamOptions {
  signal?: AbortSignal;
}

export interface ReportItem {
  id: string;
  title: string;
  created_at: string;
  tags: string[];
}

export interface ReportDetail {
  id: string;
  title: string;
  content: string;
}

export interface ResearchRunSnapshot {
  run_id: string;
  topic: string;
  status: string;
  events: ResearchStreamEvent[];
}
