const baseURL =
  import.meta.env.VITE_API_BASE_URL || "";
  // "http://localhost:8000";

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

export async function runResearchStream(
  payload: ResearchRequest,
  onEvent: (event: ResearchStreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  const response = await fetch(`${baseURL}/research/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream"
    },
    body: JSON.stringify(payload),
    signal: options.signal
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(
      errorText || `研究请求失败，状态码：${response.status}`
    );
  }

  const body = response.body;
  if (!body) {
    throw new Error("浏览器不支持流式响应，无法获取研究进度");
  }

  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);

      if (rawEvent.startsWith("data:")) {
        const dataPayload = rawEvent.slice(5).trim();
        if (dataPayload) {
          try {
            const event = JSON.parse(dataPayload) as ResearchStreamEvent;
            onEvent(event);

            if (event.type === "error" || event.type === "done") {
              return;
            }
          } catch (error) {
            console.error("解析流式事件失败：", error, dataPayload);
          }
        }
      }

      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      if (buffer.trim()) {
        const rawEvent = buffer.trim();
        if (rawEvent.startsWith("data:")) {
          const dataPayload = rawEvent.slice(5).trim();
          if (dataPayload) {
            try {
              const event = JSON.parse(dataPayload) as ResearchStreamEvent;
              onEvent(event);
            } catch (error) {
              console.error("解析流式事件失败：", error, dataPayload);
            }
          }
        }
      }
      break;
    }
  }
}

export async function planResearch(
  payload: ResearchRequest,
  options: StreamOptions = {}
): Promise<ResearchPlanResponse> {
  const response = await fetch(`${baseURL}/research/plan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal: options.signal
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(
      errorText || `研究规划失败，状态码：${response.status}`
    );
  }

  return response.json();
}

/** 获取所有历史研究报告列表（conclusion 类型笔记） */
export async function listReports(): Promise<ReportItem[]> {
  const res = await fetch(`${baseURL}/notes/reports`);
  if (!res.ok) return [];
  return res.json();
}

/** 获取单条报告的完整 Markdown 内容 */
export async function getReport(noteId: string): Promise<ReportDetail> {
  const res = await fetch(`${baseURL}/notes/reports/${encodeURIComponent(noteId)}`);
  if (!res.ok) throw new Error("报告不存在");
  return res.json();
}
