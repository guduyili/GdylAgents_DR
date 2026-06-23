export interface SourceItem {
  title: string;
  url: string;
  snippet: string;
  raw: string;
}

export interface ToolCallLog {
  eventId: number;
  agent: string;
  tool: string;
  parameters: Record<string, unknown>;
  result: string;
  inputPreview: string | null;
  outputPreview: string | null;
  noteId: string | null;
  notePath: string | null;
  timestamp: number;
  durationMs?: number | null;
}

export interface ReviewResultView {
  passed: boolean;
  score: number;
  issues: string[];
  suggestions: string[];
}

export interface FactCheckResultView {
  passed: boolean;
  score: number;
  matchedSources: string[];
  warnings: string[];
  missingTerms: string[];
}

export interface LoadedSkillView {
  name: string;
  description: string;
  preview: string;
}

export interface TimelineEventView {
  id: string;
  type: string;
  message: string;
  log: string;
  timestamp: string;
  runId: string | null;
  taskId: number | null;
  taskRunId: string | null;
  streamToken: string | null;
  source: string | null;
  step: number | null;
  durationMs: number | null;
  phase: string | null;
  inputPreview: string | null;
  outputPreview: string | null;
  toolDetail: string | null;
}

export interface TodoTaskView {
  id: number;
  title: string;
  intent: string;
  query: string;
  status: string;
  summary: string;
  sourcesSummary: string;
  sourceItems: SourceItem[];
  notices: string[];
  noteId: string | null;
  notePath: string | null;
  taskRunId: string | null;
  streamToken: string | null;
  toolCalls: ToolCallLog[];
  loadedSkills: LoadedSkillView[];
  factCheck: FactCheckResultView | null;
  searchBackend: string | null;
}

export interface PlannedTaskView {
  localId: number;
  title: string;
  intent: string;
  query: string;
}
