<template>
  <li v-show="visible">
    <span class="timeline-node"></span>
    <p>{{ event.log }}</p>
    <div class="timeline-event-meta">
      <span v-if="event.step !== null && event.step !== undefined">step {{ event.step }}</span>
      <span v-if="event.taskRunId">{{ event.taskRunId }}</span>
      <span v-if="event.streamToken">{{ event.streamToken }}</span>
      <span v-if="event.phase">{{ event.phase }}</span>
      <span v-if="event.durationMs !== null && event.durationMs !== undefined">{{ event.durationMs }}ms</span>
    </div>

    <div v-if="event.type === 'tool_call' && (event.inputPreview || event.outputPreview)" class="timeline-tool-preview">
      <p v-if="event.inputPreview" class="tool-preview-line">
        <strong>输入预览：</strong>{{ event.inputPreview }}
      </p>
      <p v-if="event.outputPreview" class="tool-preview-line">
        <strong>输出预览：</strong>{{ event.outputPreview }}
      </p>
      <button
        v-if="event.toolDetail"
        class="link-btn"
        type="button"
        @click="expanded = !expanded"
      >{{ expanded ? "收起详情" : "展开详情" }}</button>
      <pre v-if="expanded && event.toolDetail" class="tool-preview-full">{{ event.toolDetail }}</pre>
    </div>
  </li>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { TimelineEventView } from "../types/view";

defineProps<{
  event: TimelineEventView;
  visible: boolean;
}>();

const expanded = ref(false);
</script>