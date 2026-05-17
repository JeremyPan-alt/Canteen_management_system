<template>
  <main class="page">
    <header class="header">
      <div>
        <p class="eyebrow">Canteen Intake Capture</p>
        <h1>食材进货自动录入</h1>
      </div>
    </header>

    <section class="model-toolbar">
      <label>
        <span>目标检测模型</span>
        <select v-model="selectedDetectionModel">
          <option v-for="model in detectionModels" :key="model.id" :value="model.id">
            {{ model.name }}
          </option>
        </select>
      </label>
      <label>
        <span>OCR 模型</span>
        <select v-model="selectedOcrModel">
          <option v-for="model in ocrModels" :key="model.id" :value="model.id">
            {{ model.name }}
          </option>
        </select>
      </label>
      <button class="primary" :disabled="capturing" @click="startCapture">
        {{ capturing ? '检测中...' : '开始录入' }}
      </button>
    </section>

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

    <section v-if="lastBatch?.progress_logs?.length" class="progress-card">
      <div class="result-header">
        <h2>检测进度</h2>
        <span class="pill">{{ lastBatch.status }}</span>
      </div>
      <ul class="progress-list">
        <li v-for="(log, index) in lastBatch.progress_logs" :key="`${log.time}-${index}`">
          <span>{{ log.time }}</span>
          <p>{{ log.message }}</p>
        </li>
      </ul>
    </section>

    <section class="data-grid">
      <article class="result-card">
        <div class="result-header">
          <h2>本次待上传 SQLite 数据</h2>
          <div class="button-row">
            <button class="danger" @click="clearLocalCache">清除数据库缓存</button>
            <button class="secondary" :disabled="!localRecords.length" @click="uploadLocalRecords">
              数据入库
            </button>
          </div>
        </div>
        <p v-if="localMessage && !localRecords.length" class="empty-text">{{ localMessage }}</p>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>菜品</th>
                <th>重量</th>
                <th>记录人</th>
                <th>入库时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="record in localRecords" :key="record.id">
                <td>{{ record.product_name || '待补充' }}</td>
                <td>{{ record.weight ?? '-' }} {{ record.unit }}</td>
                <td>{{ record.recorder }}</td>
                <td>{{ record.intake_datetime }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="result-card">
        <div class="result-header">
          <h2>MySQL 已有数据</h2>
          <input v-model="mysqlDate" type="date" @change="loadMysqlRecords" />
        </div>
        <p v-if="mysqlMessage && !mysqlRecords.length" class="empty-text">{{ mysqlMessage }}</p>
        <div v-else class="table-wrap scroll-table">
          <table>
            <thead>
              <tr>
                <th>菜品</th>
                <th>重量</th>
                <th>记录人</th>
                <th>入库时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="record in mysqlRecords" :key="record.id">
                <td>{{ record.product_name }}</td>
                <td>{{ record.weight ?? '-' }} {{ record.unit }}</td>
                <td>{{ record.recorder }}</td>
                <td>{{ record.intake_datetime }}</td>
                <td>
                  <button class="link-button" @click="openMysqlEdit(record)">编辑</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>

    <div v-if="confirmVisible" class="modal-backdrop">
      <div class="confirm-modal">
        <div class="result-header">
          <h2>确认录入数据</h2>
          <span class="pill">{{ lastBatch?.status }}</span>
        </div>
        <div class="form-grid">
          <label>
            <span>菜品名称</span>
            <input v-model="confirmRecord.product_name" placeholder="请输入菜品名称" />
          </label>
          <label>
            <span>重量</span>
            <input v-model="confirmRecord.weight" type="number" step="0.01" placeholder="请输入重量" />
          </label>
          <label>
            <span>单位</span>
            <input v-model="confirmRecord.unit" />
          </label>
          <label>
            <span>记录人</span>
            <input v-model="confirmRecord.recorder" />
          </label>
          <label>
            <span>入库时间</span>
            <input v-model="confirmRecord.intake_datetime" type="datetime-local" />
          </label>
          <label>
            <span>备注</span>
            <input v-model="confirmRecord.notes" placeholder="可选" />
          </label>
        </div>
        <pre class="raw-preview">{{ detectionPreview }}</pre>
        <div class="modal-actions">
          <button class="secondary" @click="confirmVisible = false">取消</button>
          <button class="primary" @click="saveConfirmedRecord">确认录入 SQLite</button>
        </div>
      </div>
    </div>

    <div v-if="mysqlEditVisible" class="modal-backdrop">
      <div class="confirm-modal">
        <div class="result-header">
          <h2>修改 MySQL 入库数据</h2>
          <span class="pill">ID {{ mysqlEditRecord.id }}</span>
        </div>
        <div class="form-grid">
          <label>
            <span>菜品名称</span>
            <input v-model="mysqlEditRecord.product_name" placeholder="请输入菜品名称" />
          </label>
          <label>
            <span>重量</span>
            <input v-model="mysqlEditRecord.weight" type="number" step="0.01" placeholder="请输入重量" />
          </label>
          <label>
            <span>单位</span>
            <input v-model="mysqlEditRecord.unit" />
          </label>
          <label>
            <span>记录人</span>
            <input v-model="mysqlEditRecord.recorder" />
          </label>
          <label>
            <span>入库时间</span>
            <input v-model="mysqlEditRecord.intake_datetime" type="datetime-local" />
          </label>
          <label>
            <span>备注</span>
            <input v-model="mysqlEditRecord.notes" placeholder="可选" />
          </label>
        </div>
        <p class="modal-hint">如果修改了入库日期，保存后该条目会从当前日期列表中消失，并出现在新的日期查询结果中。</p>
        <div class="modal-actions">
          <button class="secondary" @click="mysqlEditVisible = false">取消</button>
          <button class="primary" @click="saveMysqlRecord">保存修改</button>
        </div>
      </div>
    </div>
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
const detectionModels = ref([{ id: 'yolov11', name: 'YOLOv11' }])
const ocrModels = ref([{ id: 'paddleocr', name: 'PaddleOCR' }])
const selectedDetectionModel = ref('yolov11')
const selectedOcrModel = ref('paddleocr')
const confirmVisible = ref(false)
const confirmRecord = reactive({})
const localRecords = ref([])
const localMessage = ref('本地数据库暂无待上传数据')
const mysqlRecords = ref([])
const mysqlMessage = ref('')
const mysqlDate = ref(new Date().toISOString().slice(0, 10))
const mysqlEditVisible = ref(false)
const mysqlEditRecord = reactive({})
let pollTimer = null
let batchTimer = null

const detectionPreview = computed(() => JSON.stringify(lastBatch.value?.result || {}, null, 2))

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
        detection_model: selectedDetectionModel.value,
        ocr_model: selectedOcrModel.value,
      }),
    })
    const payload = await response.json()
    lastBatch.value = payload.batch
    watchBatch(payload.batch.batch_id)
  } catch (error) {
    window.alert(`启动检测失败：${error}`)
    capturing.value = false
  }
}

async function loadModels() {
  const response = await fetch(`${apiBase}/api/models`, { cache: 'no-store' })
  const payload = await response.json()
  detectionModels.value = payload.detection_models || detectionModels.value
  ocrModels.value = payload.ocr_models || ocrModels.value
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
    if (payload.batch.status === 'completed') {
      prepareConfirmation(payload.batch)
      clearInterval(batchTimer)
      batchTimer = null
      capturing.value = false
    } else if (payload.batch.status === 'failed') {
      window.alert(payload.batch.error || '检测失败')
      clearInterval(batchTimer)
      batchTimer = null
      capturing.value = false
    }
  }, 800)
}

function prepareConfirmation(batch) {
  const suggested = batch.result?.suggested_record || {}
  Object.assign(confirmRecord, {
    batch_id: batch.batch_id,
    product_name: suggested.product_name || '',
    weight: suggested.weight ?? '',
    unit: suggested.unit || 'kg',
    recorder: batch.recorder || 'web',
    intake_datetime: formatDateTimeInput(new Date()),
    notes: suggested.notes || '',
    detection_model: batch.detection_model || selectedDetectionModel.value,
    ocr_model: batch.ocr_model || selectedOcrModel.value,
    trigger_type: batch.trigger_type || 'manual',
    frames: batch.frames || {},
    raw_result: batch.result || {},
  })
  confirmVisible.value = true
}

async function saveConfirmedRecord() {
  const response = await fetch(`${apiBase}/api/records/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(confirmRecord),
  })
  if (!response.ok) {
    window.alert('保存 SQLite 失败')
    return
  }
  confirmVisible.value = false
  await loadLocalRecords()
}

async function loadLocalRecords() {
  const response = await fetch(`${apiBase}/api/records/local/session`, { cache: 'no-store' })
  const payload = await response.json()
  localRecords.value = payload.records || []
  localMessage.value = payload.message || ''
}

async function uploadLocalRecords() {
  const response = await fetch(`${apiBase}/api/records/upload-mysql`, { method: 'POST' })
  const payload = await response.json()
  if (!response.ok) {
    window.alert(payload.error || 'MySQL 入库失败')
    return
  }
  localMessage.value = payload.message
  await loadLocalRecords()
  await loadMysqlRecords()
}

async function clearLocalCache() {
  const confirmed = window.confirm('确认清除本地数据库缓存吗？该操作会直接删除 SQLite 中所有内容，且不可恢复。')
  if (!confirmed) return
  const response = await fetch(`${apiBase}/api/records/local/cache`, { method: 'DELETE' })
  const payload = await response.json()
  if (!response.ok) {
    window.alert(payload.error || '清除本地数据库缓存失败')
    return
  }
  localMessage.value = payload.message
  await loadLocalRecords()
}

async function loadMysqlRecords() {
  const response = await fetch(`${apiBase}/api/records/mysql?date=${mysqlDate.value}`, { cache: 'no-store' })
  const payload = await response.json()
  mysqlRecords.value = payload.records || []
  mysqlMessage.value = payload.message || (mysqlRecords.value.length ? '' : '所选日期暂无 MySQL 数据')
}

function openMysqlEdit(record) {
  Object.assign(mysqlEditRecord, {
    id: record.id,
    product_name: record.product_name || '',
    weight: record.weight ?? '',
    unit: record.unit || 'kg',
    recorder: record.recorder || '',
    intake_datetime: toDateTimeInput(record.intake_datetime),
    notes: record.notes || '',
  })
  mysqlEditVisible.value = true
}

async function saveMysqlRecord() {
  const response = await fetch(`${apiBase}/api/records/mysql/${mysqlEditRecord.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(mysqlEditRecord),
  })
  const payload = await response.json()
  if (!response.ok) {
    window.alert(payload.error || '修改 MySQL 数据失败')
    return
  }
  mysqlEditVisible.value = false
  await loadMysqlRecords()
}

function formatDateTimeInput(date) {
  const offset = date.getTimezoneOffset()
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 16)
}

function toDateTimeInput(value) {
  if (!value) return formatDateTimeInput(new Date())
  if (typeof value === 'string') {
    const normalized = value.replace('T', ' ')
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(normalized)) {
      return normalized.slice(0, 16).replace(' ', 'T')
    }
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return formatDateTimeInput(new Date())
  return formatDateTimeInput(date)
}

onMounted(() => {
  loadModels()
  loadLocalRecords()
  loadMysqlRecords()
  refreshStatus()
  pollTimer = setInterval(refreshStatus, 2000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (batchTimer) clearInterval(batchTimer)
})
</script>
