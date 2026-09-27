<script setup>
import { computed, onMounted, ref } from 'vue'
import MediaTile from '../components/media/MediaTile.vue'
import MediaViewer from '../components/media/MediaViewer.vue'
import { downloadMediaBundle } from '../surveyor/mediaCapture.js'
import { useRoute } from 'vue-router'

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const route = useRoute()
const items = ref([])
const type = ref('all')
const period = ref('all')
const fromDate = ref('')
const toDate = ref('')
const session = ref('all')
const camera = ref('all')
const selectMode = ref(false)
const selectedIds = ref(new Set())
const viewer = ref(null)
const busy = ref(false)
const error = ref('')
const includeCoordinates = ref(true)
const now = Date.now()
const sessions = computed(() => [...new Set(items.value.map(item => item.search_session_id).filter(Boolean))])
const cameras = computed(() => [...new Map(items.value.filter(item => item.camera_name).map(item => [item.camera_name, item.camera_name])).values()])
const visible = computed(() => items.value.filter(item => {
  if (type.value !== 'all' && item.attachment_type !== type.value) return false
  if (session.value !== 'all' && String(item.search_session_id) !== session.value) return false
  if (camera.value !== 'all' && item.camera_name !== camera.value) return false
  const timestamp = new Date(item.observed_at || item.created_at).getTime()
  if (period.value === 'custom') {
    if (fromDate.value && timestamp < new Date(`${fromDate.value}T00:00:00`).getTime()) return false
    if (toDate.value && timestamp > new Date(`${toDate.value}T23:59:59.999`).getTime()) return false
  }
  if (period.value === 'tonight' && timestamp < now - 12 * 60 * 60 * 1000) return false
  if (period.value === 'today' && timestamp < new Date().setHours(0, 0, 0, 0)) return false
  if (period.value === '7d' && timestamp < now - 7 * 86400000) return false
  return true
}))
const selected = computed(() => visible.value.filter(item => selectedIds.value.has(item.id)))
const selectedBytes = computed(() => selected.value.reduce((sum, item) => sum + (item.file_size_bytes || 0), 0))
function formatSize(bytes) { return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB` }
async function load() {
  try { const response = await fetch(`${API}/api/surveyor/media?limit=2000`); if (!response.ok) throw new Error('Media library is unavailable'); items.value = await response.json() }
  catch (cause) { error.value = cause.message }
}
function toggle(item) { const next = new Set(selectedIds.value); next.has(item.id) ? next.delete(item.id) : next.add(item.id); selectedIds.value = next }
function mediaKind(itemsToExport) { return itemsToExport.reduce((acc, item) => { acc[item.attachment_type] = (acc[item.attachment_type] || 0) + 1; return acc }, {}) }
async function exportBundle(list = selected.value) {
  if (!list.length) return
  const counts = mediaKind(list)
  const breakdown = Object.entries(counts).map(([key, count]) => `${count} ${key}`).join(', ')
  if (!confirm(`Export ${list.length} items (${breakdown}), about ${formatSize(list.reduce((sum, item) => sum + (item.file_size_bytes || 0), 0))}? Private contact details are excluded.`)) return
  busy.value = true; error.value = ''
  try {
    await downloadMediaBundle(API, list.map(item => item.id), { include_exact_coordinates: includeCoordinates.value })
    selectMode.value = false; selectedIds.value = new Set()
  } catch (cause) { error.value = cause.message }
  finally { busy.value = false }
}
async function remove(item) {
  if (!confirm(`Delete ${item.original_filename}? This removes the stored original.`)) return
  const response = await fetch(`${API}/api/surveyor/attachments/${item.id}`, { method: 'DELETE' })
  if (!response.ok) { error.value = 'Media could not be deleted.'; return }
  items.value = items.value.filter(row => row.id !== item.id); viewer.value = null
}
onMounted(() => { if (['tonight','today','7d'].includes(route.query.period)) period.value = route.query.period; load() })
</script>

<template>
  <main class="media-vault-page">
    <p class="eyebrow">ARCHIE RADAR · FIELD MEDIA</p><h1>Media Vault</h1><p class="media-vault-intro">Photos, video, and audio captured during field work. Originals stay in their captured format.</p>
    <section class="media-vault-controls">
      <label>Type<select v-model="type"><option value="all">All media</option><option value="image">Photos</option><option value="video">Video</option><option value="audio">Audio</option><option value="document">Documents</option></select></label>
      <label>Date<select v-model="period"><option value="all">Any date</option><option value="tonight">Tonight · last 12 hours</option><option value="today">Today</option><option value="7d">Last 7 days</option><option value="custom">Custom range</option></select></label>
      <label v-if="period==='custom'">From<input v-model="fromDate" type="date" /></label><label v-if="period==='custom'">To<input v-model="toDate" type="date" /></label>
      <label>Search session<select v-model="session"><option value="all">All sessions</option><option v-for="id in sessions" :key="id" :value="String(id)">Search #{{ id }}</option></select></label>
      <label>Camera<select v-model="camera"><option value="all">All cameras</option><option v-for="name in cameras" :key="name" :value="name">{{ name }}</option></select></label>
      <label class="media-coordinate-setting"><input v-model="includeCoordinates" type="checkbox" /> Include exact coordinates</label>
      <button v-if="visible.length" class="secondary-button" :disabled="busy" @click="exportBundle(visible)">{{ busy ? 'Preparing…' : period==='tonight' ? `Export tonight (${visible.length})` : `Export filtered (${visible.length})` }}</button>
      <button class="secondary-button" @click="selectMode=!selectMode; selectedIds=new Set()">{{ selectMode ? 'Done selecting' : 'Select' }}</button>
    </section>
    <p v-if="period==='tonight'" class="media-vault-tonight">Tonight's media · {{ visible.filter(item=>item.attachment_type==='image').length }} photos · {{ visible.filter(item=>item.attachment_type==='video').length }} videos · {{ visible.filter(item=>item.attachment_type==='audio').length }} audio</p>
    <p v-if="error" class="surveyor-error" role="alert">{{ error }}</p><p v-else-if="!visible.length" class="journal-empty">No media matches these filters.</p>
    <div v-else class="media-vault-grid"><MediaTile v-for="item in visible" :key="item.id" :item="item" :api="API" :selectable="selectMode" :selected="selectedIds.has(item.id)" @open="viewer=$event" @toggle="toggle" /></div>
    <div v-if="selectMode && selected.length" class="media-export-bar"><strong>{{ selected.length }} selected · {{ formatSize(selectedBytes) }}</strong><button class="primary" :disabled="busy" @click="exportBundle()">{{ busy ? 'Preparing export…' : 'Export bundle' }}</button></div>
    <MediaViewer v-if="viewer" :item="viewer" :api="API" @close="viewer=null" @delete="remove" />
  </main>
</template>
