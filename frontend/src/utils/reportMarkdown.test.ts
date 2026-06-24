import { describe, expect, it } from "vitest";
import {
  computeContainerScrollTop,
  extractReportHeadings,
  renderReportHtml
} from "./reportMarkdown";

describe("reportMarkdown", () => {
  it("extracts nested headings for table of contents", () => {
    const headings = extractReportHeadings("# 报告\n\n## 背景\n\n### 细节");

    expect(headings).toHaveLength(3);
    expect(headings[0].text).toBe("报告");
    expect(headings[1].level).toBe(2);
    expect(headings[2].level).toBe(3);
  });

  it("renders markdown links as clickable anchors", () => {
    const html = renderReportHtml("参考 [示例](https://example.com)");

    expect(html).toContain('href="https://example.com"');
    expect(html).toContain("target=\"_blank\"");
    expect(html).toContain("示例");
  });

  it("computes in-container scroll offset without moving ancestor panels", () => {
    expect(computeContainerScrollTop(0, 0, 180, 10)).toBe(170);
    expect(computeContainerScrollTop(40, 100, 120, 12)).toBe(48);
  });
});