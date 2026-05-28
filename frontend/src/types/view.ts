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
  noteId: string | null;
  notePath: string | null;
  timestamp: number;
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
  toolCalls: ToolCallLog[];
}

export interface PlannedTaskView {
  localId: number;
  title: string;
  intent: string;
  query: string;
}
