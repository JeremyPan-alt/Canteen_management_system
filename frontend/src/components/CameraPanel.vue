<template>
  <article class="camera-card">
    <div class="video-box">
      <img class="stream" :src="streamUrl" :alt="camera.name" />
      <span class="status" :class="{ online }">{{ statusText }}</span>
    </div>
    <div class="camera-meta">
      <h2>{{ camera.name }}</h2>
      <p v-if="status?.last_error">{{ status.last_error }}</p>
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
</script>
