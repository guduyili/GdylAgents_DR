<template>
  <section class="plan-editor">
    <div class="plan-editor-head">
      <div>
        <h2>确认研究计划</h2>
        <p>可以调整任务标题、目标和检索 query；确认后才会开始执行。</p>
      </div>
      <span>{{ plannedTasks.length }} 个任务</span>
    </div>

    <ol class="plan-task-list">
      <li v-for="(task, index) in plannedTasks" :key="task.localId" class="plan-task-card">
        <div class="plan-task-meta">
          <strong>任务 {{ index + 1 }}</strong>
          <div class="plan-task-actions">
            <button type="button" class="mini-btn" :disabled="index === 0" @click="$emit('move-task', index, -1)">上移</button>
            <button type="button" class="mini-btn" :disabled="index === plannedTasks.length - 1" @click="$emit('move-task', index, 1)">下移</button>
            <button type="button" class="mini-btn danger" :disabled="plannedTasks.length <= 1" @click="$emit('remove-task', index)">删除</button>
          </div>
        </div>
        <label class="field compact">
          <span>标题</span>
          <input v-model="task.title" placeholder="任务标题" />
        </label>
        <label class="field compact">
          <span>目标</span>
          <textarea v-model="task.intent" placeholder="该任务要解决的问题" rows="2"></textarea>
        </label>
        <label class="field compact">
          <span>检索 query</span>
          <input v-model="task.query" placeholder="用于搜索的关键词" />
        </label>
      </li>
    </ol>

    <div class="plan-actions">
      <button type="button" class="secondary-btn" @click="$emit('add-task')">新增任务</button>
      <button type="button" class="submit" :disabled="loading || !canStartResearch" @click="$emit('start')">
        <span class="submit-label">
          <svg v-if="loading" class="spinner" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9" stroke-width="3" />
          </svg>
          {{ loading ? "研究进行中..." : "确认并开始研究" }}
        </span>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { PlannedTaskView } from "../types/view";

defineProps<{
  plannedTasks: PlannedTaskView[];
  loading: boolean;
  canStartResearch: boolean;
}>();

defineEmits<{
  'add-task': [];
  'remove-task': [index: number];
  'move-task': [index: number, direction: -1 | 1];
  start: [];
}>();
</script>
