<template>
  <article class="report-block report-card workspace-card" :class="{ 'block-highlight': highlight }">
    <div class="card-title-row report-viewer-head">
      <div>
        <p class="card-kicker">Final Report</p>
        <h3>最终报告</h3>
      </div>
      <div class="report-actions">
        <button type="button" class="secondary-btn" :disabled="!markdown" @click="copyPlainText">
          复制纯文本
        </button>
        <button type="button" class="secondary-btn" :disabled="!markdown" @click="$emit('download')">
          下载 .md
        </button>
      </div>
    </div>

    <div class="report-viewer-layout">
      <nav v-if="headings.length" class="report-toc" aria-label="报告目录">
        <p class="report-toc-title">目录</p>
        <button
          v-for="heading in headings"
          :key="heading.id"
          type="button"
          class="report-toc-link"
          :class="`level-${heading.level}`"
          @click="scrollToHeading(heading.id)"
        >
          {{ heading.text }}
        </button>
      </nav>

      <div ref="contentRef" class="block-pre md-body report-content" v-html="renderedHtml"></div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { extractReportHeadings, renderReportHtml } from "../utils/reportMarkdown";

const props = defineProps<{
  markdown: string;
  highlight?: boolean;
}>();

defineEmits<{
  download: [];
}>();

const contentRef = ref<HTMLElement | null>(null);
const headings = computed(() => extractReportHeadings(props.markdown));
const renderedHtml = computed(() => renderReportHtml(props.markdown));

async function copyPlainText() {
  if (!props.markdown.trim()) {
    return;
  }
  try {
    await navigator.clipboard.writeText(props.markdown);
  } catch (error) {
    console.warn("无法复制报告文本", error);
    window.prompt("复制以下报告内容", props.markdown);
  }
}

function scrollToHeading(id: string) {
  const root = contentRef.value;
  if (!root) {
    return;
  }
  const target = root.querySelector<HTMLElement>(`#${CSS.escape(id)}`);
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}
</script>