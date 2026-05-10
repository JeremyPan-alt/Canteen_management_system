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
  { id: 'entrance', name: '进货区摄像头' },
  { id: 'scale', name: '秤面长焦摄像头' },
]

const statusById = reactive({})
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
