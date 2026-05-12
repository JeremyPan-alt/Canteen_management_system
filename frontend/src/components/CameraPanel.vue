<template>
  <article class="camera-card">
    <div class="video-box">
      <img class="stream" :class="{ hidden: !online }" :src="streamUrl" :alt="displayName" />
      <div v-if="!online" class="stream-error">视频流读取异常请检查</div>
    </div>
    <div class="camera-meta">
      <div class="camera-title-row">
        <div class="camera-title-picker">
          <button
            class="title-button"
            :class="{ selectable }"
            type="button"
            :disabled="!selectable"
            @click="toggleSourceMenu"
          >
            {{ displayName }}
            <span v-if="selectable" class="chevron">▾</span>
          </button>
          <div v-if="selectable && menuOpen" class="source-menu">
            <button
              v-for="option in sourceOptions"
              :key="option.id"
              class="source-option"
              type="button"
              @click="selectSource(option)"
            >
              <span>{{ option.label }}</span>
              <small>{{ option.description || option.source_label }}</small>
            </button>
            <div v-if="sourceLoading" class="source-menu-empty">正在识别摄像头...</div>
            <div v-else-if="!sourceOptions.length" class="source-menu-empty">未发现可用视频源</div>
          </div>
        </div>
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
import { ref } from 'vue'

const props = defineProps({
  camera: { type: Object, required: true },
  status: { type: Object, default: null },
  streamUrl: { type: String, required: true },
  selectable: { type: Boolean, default: false },
  sourceOptions: { type: Array, default: () => [] },
  sourceLoading: { type: Boolean, default: false },
})

const emit = defineEmits(['request-sources', 'select-source'])
const menuOpen = ref(false)

const online = computed(() => Boolean(props.status && props.status.online))
const statusText = computed(() => (online.value ? '在线' : '离线'))
const displayName = computed(() => props.status?.name || props.camera.name)
const sourceLabel = computed(() => props.status?.source_label || '未知视频源')

function toggleSourceMenu() {
  if (!props.selectable) return
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) {
    emit('request-sources', props.camera.id)
  }
}

function selectSource(option) {
  menuOpen.value = false
  emit('select-source', props.camera.id, option)
}
</script>
