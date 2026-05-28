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

export interface ResearchStreamEvent {
  type: string;
  [key: string]: unknown;
}

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
