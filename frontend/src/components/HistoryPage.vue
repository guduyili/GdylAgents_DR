<template>
  <div class="history-page">
    <div class="history-page-header">
      <button class="back-btn" @click="$emit('close')">
        <svg viewBox="0 0 24 24" width="20" height="20">
          <path d="M19 12H5M12 19l-7-7 7-7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        返回
      </button>
      <h2>📋 历史研究记录</h2>
    </div>

    <div class="history-page-body">
      <aside class="history-page-list">
        <p v-if="historyLoading" class="muted">加载中…</p>
        <p v-else-if="!historyReports.length" class="muted">暂无历史记录</p>
        <ul v-else class="history-list">
          <li v-for="report in historyReports" :key="report.id" class="history-item">
            <button
              class="history-btn"
              :class="{ active: selectedReport?.id === report.id }"
              type="button"
              @click="$emit('open-report', report.id)"
            >
              <span class="history-title">{{ report.title }}</span>
              <span class="history-date muted">{{ report.created_at.slice(0, 16).replace('T', ' ') }}</span>
            </button>
          </li>
        </ul>
      </aside>

      <article class="history-page-detail">
        <template v-if="selectedReport">
          <div class="history-detail-header">
            <h3>{{ selectedReport.title }}</h3>
          </div>
          <pre class="block-pre history-detail-content md-body" v-html="renderMd(selectedReport.content)"></pre>
        </template>
        <p v-else class="muted" style="padding:24px;"></p>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ReportDetail, ReportItem } from "../services/api";

defineProps<{
  historyLoading: boolean;
  historyReports: ReportItem[];
  selectedReport: ReportDetail | null;
  renderMd: (src: string) => string;
}>();

defineEmits<{
  close: [];
  'open-report': [noteId: string];
}>();
</script>
