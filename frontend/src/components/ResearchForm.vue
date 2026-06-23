<template>
  <section class="panel panel-form panel-centered">
    <header class="panel-head">
      <div class="logo">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 2.5c-.7 0-1.4.2-2 .6L4.6 7C3.6 7.6 3 8.7 3 9.9v4.2c0 1.2.6 2.3 1.6 2.9l5.4 3.9c1.2.8 2.8.8 4 0l5.4-3.9c1-.7 1.6-1.7 1.6-2.9V9.9c0-1.2-.6-2.3-1.6-2.9L14 3.1a3.6 3.6 0 0 0-2-.6Z"
          />
        </svg>
      </div>
      <div>
        <h1>深度研究助手</h1>
        <p>结合多轮智能检索与总结，实时呈现洞见与引用。</p>
      </div>
    </header>

    <form class="form" @submit.prevent="$emit('submit')">
      <label class="field">
        <span>研究主题</span>
        <textarea
          :value="topic"
          placeholder="例如：探索多模态模型在 2025 年的关键突破"
          rows="4"
          required
          @input="$emit('update:topic', ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </label>

      <section class="options">
        <label class="field option">
          <span>研究模式</span>
          <select
            :value="researchMode"
            @change="$emit('update:researchMode', ($event.target as HTMLSelectElement).value as 'deep' | 'quick')"
          >
            <option value="deep">深度研究（规划 + 多任务）</option>
            <option value="quick">快速浏览（单次搜索总结）</option>
          </select>
        </label>

        <label class="field option">
          <span>搜索引擎</span>
          <select
            :value="searchApi"
            @change="$emit('update:searchApi', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">沿用后端配置</option>
            <option v-for="option in searchOptions" :key="option" :value="option">
              {{ option }}
            </option>
          </select>
        </label>
      </section>

      <div class="form-actions">
        <button class="submit" type="submit" :disabled="loading">
          <span class="submit-label">
            <svg v-if="loading" class="spinner" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke-width="3" />
            </svg>
            {{
              loading
                ? "处理中..."
                : researchMode === "quick"
                  ? planReady
                    ? "重新开始快速研究"
                    : "开始快速研究"
                  : planReady
                    ? "重新生成计划"
                    : "生成研究计划"
            }}
          </span>
        </button>
        <button
          type="button"
          class="submit history-submit-btn"
          style="margin-left: auto;"
          :disabled="loading"
          @click="$emit('open-history')"
        >
          历史记录
          <span v-if="historyCount" class="history-badge-inline">{{ historyCount }}</span>
        </button>
        <button v-if="loading" type="button" class="secondary-btn" @click="$emit('cancel')">
          {{ planning ? "取消规划" : "取消研究" }}
        </button>
      </div>
    </form>

    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{
  topic: string;
  searchApi: string;
  researchMode: "deep" | "quick";
  searchOptions: string[];
  loading: boolean;
  planning: boolean;
  planReady: boolean;
  historyCount: number;
}>();

defineEmits<{
  submit: [];
  cancel: [];
  'open-history': [];
  'update:topic': [value: string];
  'update:searchApi': [value: string];
  'update:researchMode': [value: "deep" | "quick"];
}>();
</script>
