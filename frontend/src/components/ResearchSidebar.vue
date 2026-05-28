<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <button class="back-btn" @click="$emit('back')" :disabled="loading">
        <svg viewBox="0 0 24 24" width="20" height="20">
          <path d="M19 12H5M12 19l-7-7 7-7" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        返回
      </button>
      <h2>🔍 深度研究助手</h2>
    </div>

    <div class="research-info">
      <div class="info-item">
        <label>研究主题</label>
        <p class="topic-display">{{ topic }}</p>
      </div>

      <div class="info-item" v-if="searchApi">
        <label>搜索引擎</label>
        <p>{{ searchApi }}</p>
      </div>

      <div class="info-item" v-if="totalTasks > 0">
        <label>研究进度</label>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${(completedTasks / totalTasks) * 100}%` }"></div>
        </div>
        <p class="progress-text">{{ completedTasks }} / {{ totalTasks }} 任务完成</p>
      </div>
    </div>

    <div class="sidebar-actions">
      <button class="new-research-btn" @click="$emit('new-research')">
        <svg viewBox="0 0 24 24" width="18" height="18">
          <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
        </svg>
        开始新研究
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  topic: string;
  searchApi: string;
  totalTasks: number;
  completedTasks: number;
  loading: boolean;
}>();

defineEmits<{
  back: [];
  'new-research': [];
}>();
</script>
