import { marked } from "marked";
import DOMPurify from "dompurify";

export interface ReportHeading {
  id: string;
  level: number;
  text: string;
}

function slugifyHeading(text: string, used: Map<string, number>): string {
  const base =
    text
      .toLowerCase()
      .replace(/[^\w\u4e00-\u9fff]+/g, "-")
      .replace(/^-+|-+$/g, "") || "section";
  const count = used.get(base) ?? 0;
  used.set(base, count + 1);
  return count === 0 ? base : `${base}-${count}`;
}

export function extractReportHeadings(markdown: string): ReportHeading[] {
  const headings: ReportHeading[] = [];
  const used = new Map<string, number>();

  for (const line of markdown.split("\n")) {
    const match = /^(#{1,3})\s+(.+)$/.exec(line.trim());
    if (!match) {
      continue;
    }
    const text = match[2].trim();
    headings.push({
      id: slugifyHeading(text, used),
      level: match[1].length,
      text
    });
  }

  return headings;
}

export function renderReportHtml(markdown: string): string {
  if (!markdown.trim()) {
    return "";
  }

  const headings = extractReportHeadings(markdown);
  let headingIndex = 0;

  const renderer = new marked.Renderer();
  renderer.heading = ({ text, depth }) => {
    const heading = headings[headingIndex];
    headingIndex += 1;
    const id = heading?.id ?? `section-${headingIndex}`;
    return `<h${depth} id="${id}">${text}</h${depth}>`;
  };

  renderer.link = ({ href, title, text }) => {
    const safeHref = href?.trim() || "#";
    const titleAttr = title ? ` title="${title}"` : "";
    return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
  };

  const raw = marked.parse(markdown, {
    async: false,
    renderer
  }) as string;

  if (typeof window === "undefined" || typeof DOMPurify.sanitize !== "function") {
    return raw;
  }

  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ["target", "rel", "id"]
  });
}

export function computeContainerScrollTop(
  containerScrollTop: number,
  containerRectTop: number,
  targetRectTop: number,
  offset = 12
): number {
  return Math.max(0, containerScrollTop + (targetRectTop - containerRectTop) - offset);
}

/** Scroll a target element inside a scrollable container without moving ancestor panels. */
export function scrollElementIntoContainer(
  container: HTMLElement,
  target: HTMLElement,
  options?: { offset?: number; behavior?: ScrollBehavior }
): void {
  const offset = options?.offset ?? 12;
  const behavior = options?.behavior ?? "smooth";
  const containerRect = container.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const nextTop = computeContainerScrollTop(
    container.scrollTop,
    containerRect.top,
    targetRect.top,
    offset
  );

  container.scrollTo({
    top: nextTop,
    behavior
  });
}