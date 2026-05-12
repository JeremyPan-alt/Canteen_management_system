<template>
  <main class="page">
    <header class="header">
      <div>
        <p class="eyebrow">Canteen Intake Capture</p>
        <h1>食材进货自动录入</h1>
      </div>
      <button class="primary" :disabled="capturing" @click="startCapture">
        {{ capturing ? '录入中...' : '开始录入' }}
      </button>
    </header>

    <section class="camera-grid">
      <CameraPanel
        v-for="camera in cameras"
        :key="camera.id"
        :camera="camera"
        :status="statusById[camera.id]"
        :stream-url="`${apiBase}/api/cameras/${camera.id}/stream`"
        selectable
        :source-options="sourceOptionsById[camera.id] || []"
        :source-loading="Boolean(sourceLoadingById[camera.id])"
        @request-sources="loadVideoSources"
        @select-source="handleSourceSelection"
      />
    </section>

    <section class="result-card">
      <div class="result-header">
        <h2>最近录入批次</h2>
        <span v-if="lastBatch" class="pill">{{ lastBatch.status }}</span>
      </div>
      <pre>{{ formattedBatch }}</pre>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import CameraPanel from './components/CameraPanel.vue'

const apiBase = import.meta.env.VITE_API_BASE || ''
const cameras = [
  { id: 'entrance', name: '进货区实时画面' },
  { id: 'scale', name: '秤面长焦摄像头' },
]

const statusById = reactive({})
const sourceOptionsById = reactive({})
const sourceLoadingById = reactive({})
const capturing = ref(false)
const lastBatch = ref(null)
let pollTimer = null
let batchTimer = null

const formattedBatch = computed(() => {
  if (!lastBatch.value) {
    return '点击“开始录入”后，将同时抓取左右两路最新画面，并提交给 YOLO/OCR 接口。'
  }
  return JSON.stringify(lastBatch.value, null, 2)
})

async function refreshStatus() {
  try {
    const response = await fetch(`${apiBase}/api/cameras/status`, { cache: 'no-store' })
    const payload = await response.json()
    for (const camera of payload.cameras || []) {
      statusById[camera.camera_id] = camera
    }
  } catch (error) {
    for (const camera of cameras) {
      statusById[camera.id] = {
        camera_id: camera.id,
        name: camera.name,
        online: false,
        source_label: '未知视频源',
        last_error: String(error),
      }
    }
  }
}

async function startCapture() {
  capturing.value = true
  try {
    const response = await fetch(`${apiBase}/api/capture/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        trigger_type: 'manual',
        recorder: 'web',
      }),
    })
    const payload = await response.json()
    lastBatch.value = payload.batch
    watchBatch(payload.batch.batch_id)
  } finally {
    capturing.value = false
  }
}

async function loadVideoSources(cameraId) {
  sourceLoadingById[cameraId] = true
  try {
    const response = await fetch(
      `${apiBase}/api/video-sources?camera_id=${encodeURIComponent(cameraId)}`,
      { cache: 'no-store' },
    )
    const payload = await response.json()
    sourceOptionsById[cameraId] = payload.sources || []
  } finally {
    sourceLoadingById[cameraId] = false
  }
}

async function handleSourceSelection(cameraId, option) {
  let source = option.source
  if (option.source_type === 'rtsp') {
    source = window.prompt('请输入 RTSP 视频流地址', 'rtsp://')
    if (!source) return
  }

  const response = await fetch(`${apiBase}/api/cameras/${cameraId}/source`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_type: option.source_type,
      source,
      source_label: option.source_label,
    }),
  })
  const payload = await response.json()
  if (!response.ok) {
    window.alert(payload.error || '切换视频源失败')
    return
  }
  statusById[cameraId] = payload.camera
  await refreshStatus()
}

function watchBatch(batchId) {
  if (batchTimer) {
    clearInterval(batchTimer)
  }
  batchTimer = setInterval(async () => {
    const response = await fetch(`${apiBase}/api/capture/${batchId}`, { cache: 'no-store' })
    const payload = await response.json()
    lastBatch.value = payload.batch
    if (['completed', 'failed'].includes(payload.batch.status)) {
      clearInterval(batchTimer)
      batchTimer = null
    }
  }, 800)
}

onMounted(() => {
  refreshStatus()
  pollTimer = setInterval(refreshStatus, 2000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (batchTimer) clearInterval(batchTimer)
})
</script>
