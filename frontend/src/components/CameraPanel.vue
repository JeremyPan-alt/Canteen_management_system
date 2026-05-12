<template>
  <article class="camera-card">
    <div class="video-box">
      <img class="stream" :class="{ hidden: !online }" :src="streamUrl" :alt="displayName" />
      <div v-if="!online" class="stream-error">视频流读取异常请检查</div>
    </div>
    <div class="camera-meta">
      <div class="camera-title-row">
        <h2>{{ displayName }}</h2>
        <span class="source-status" :class="{ online }">
          <span class="status-dot" :class="{ online }"></span>
          {{ statusText }} · {{ sourceLabel }}
        </span>
      </div>
      <p v-if="status?.last_error">最近错误：{{ status.last_error }}</p>
      <p v-else>只显示最新实时帧；摄像头异常时自动重连。</p>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  camera: { type: Object, required: true },
  status: { type: Object, default: null },
  streamUrl: { type: String, required: true },
})

const online = computed(() => Boolean(props.status && props.status.online))
const statusText = computed(() => (online.value ? '在线' : '离线'))
const displayName = computed(() => props.status?.name || props.camera.name)
const sourceLabel = computed(() => props.status?.source_label || '未知视频源')
</script>
