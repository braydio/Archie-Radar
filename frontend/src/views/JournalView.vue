<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { eventLabel } from '../surveyor/eventLabels.js'

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const entries = ref([])
const filter = ref('all')
const loading = ref(true)
const error = ref('')
const brief = ref(null)
const tonightMedia = ref([])
const FILTER_TYPES = {
  searches: ['search_started', 'search_completed'],
  observations: ['object_created'],
  cameras: ['camera_moved', 'camera_aimed', 'camera_created', 'camera_placement_saved', 'camera_deactivated'],
  links: ['object_linked', 'object_link_created', 'object_link_updated', 'object_link_deleted'],
  evidence: ['evidence_added', 'evidence_resolved', 'evidence_reopened', 'attachment_deleted'],
  candidates: ['candidate_reviewed', 'candidate_linked'],
  access: ['access_created', 'access_updated', 'access_archived'], wildlife: ['wildlife_observed'],
  followups: ['task_created', 'task_completed', 'task_reopened', 'task_dismissed']
}
const visibleEntries = computed(() => {
  if (filter.value === 'all') return entries.value
  if (filter.value !== 'unresolved') return entries.value.filter(item => (FILTER_TYPES[filter.value] || []).includes(item.event_type))
  const latest = new Map()
  for (const item of entries.value) {
    const key = `${item.entity_type}:${item.entity_id}`
    if (!latest.has(key) && (item.event_type.startsWith('evidence_') || item.event_type.startsWith('task_'))) latest.set(key, item)
  }
  return [...latest.values()].filter(item => item.entity_type === 'task'
    ? item.event_type === 'task_created' || item.event_type === 'task_reopened'
    : item.event_type !== 'evidence_resolved')
})
const groupedEntries = computed(() => {
  const groups = new Map()
  for (const event of visibleEntries.value) {
    const date = new Date(event.occurred_at).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
    if (!groups.has(date)) groups.set(date, [])
    groups.get(date).push(event)
  }
  return [...groups.entries()]
})

async function loadEvents() {
  loading.value = true
  try {
    const response = await fetch(`${API}/api/surveyor/events?limit=2000`)
    if (!response.ok) throw new Error('Journal history is unavailable')
    entries.value = await response.json(); error.value = ''
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}

async function loadBrief() {
  try { const response = await fetch(`${API}/api/surveyor/brief`); if (response.ok) brief.value = await response.json() }
  catch { brief.value = null }
}

async function loadTonightMedia() {
  try {
    const response = await fetch(`${API}/api/surveyor/media?limit=2000`)
    if (!response.ok) return
    const cutoff = Date.now() - 12 * 60 * 60 * 1000
    tonightMedia.value = (await response.json()).filter(item => new Date(item.observed_at || item.created_at).getTime() >= cutoff)
  } catch { tonightMedia.value = [] }
}

onMounted(() => { loadEvents(); loadBrief(); loadTonightMedia() })
</script>

<template>
  <main class="journal-page"><p class="eyebrow">ARCHIE RADAR · FIELD JOURNAL</p><h1>Journal</h1><p class="journal-intro">Search sessions, field observations, camera changes, and candidate reviews in one chronological record.</p>
    <section v-if="brief" class="field-brief"><p class="eyebrow">TODAY · FIELD BRIEF</p><div><span><strong>{{ brief.open_tasks }}</strong> follow-ups</span><span><strong>{{ brief.due_today }}</strong> due today</span><span><strong>{{ brief.overdue_tasks }}</strong> overdue</span><span><strong>{{ brief.needs_search_zones }}</strong> areas need search</span><span><strong>{{ brief.needs_recheck_zones + brief.stale_search_zones }}</strong> areas need re-check</span><span><strong>{{ brief.unresolved_evidence }}</strong> unresolved evidence</span><span><strong>{{ brief.active_cameras }}</strong> active cameras</span></div></section>
    <section v-if="tonightMedia.length" class="journal-tonight-media"><div><p class="eyebrow">TONIGHT'S MEDIA</p><strong>{{ tonightMedia.filter(item=>item.attachment_type==='image').length }} photos · {{ tonightMedia.filter(item=>item.attachment_type==='video').length }} videos · {{ tonightMedia.filter(item=>item.attachment_type==='audio').length }} audio</strong></div><RouterLink to="/media?period=tonight">Export all ↗</RouterLink></section>
    <div class="journal-controls"><label>Show<select v-model="filter"><option value="all">All activity</option><option value="searches">Searches</option><option value="observations">Sightings and evidence</option><option value="evidence">Evidence</option><option value="cameras">Cameras</option><option value="links">Object links</option><option value="candidates">Candidates</option><option value="access">Access</option><option value="followups">Follow-ups</option><option value="unresolved">Unresolved</option><option value="wildlife">Wildlife</option></select></label><div><RouterLink to="/media">Open Media Vault ↗</RouterLink> · <RouterLink to="/surveyor">Open Surveyor map ↗</RouterLink></div></div>
    <p v-if="error" class="surveyor-error">{{ error }}</p><p v-else-if="loading">Loading field journal…</p>
    <div v-else-if="groupedEntries.length" class="journal-days"><section v-for="[date, dayEntries] in groupedEntries" :key="date"><h2>{{ date }}</h2><div class="journal-list"><article v-for="entry in dayEntries" :key="entry.id"><time>{{ new Date(entry.occurred_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) }}</time><h3>{{ eventLabel(entry) }}</h3><p v-if="entry.notes">{{ entry.notes }}</p><pre v-else-if="entry.event_type === 'search_completed' && entry.after?.result_summary">{{ entry.after.result_summary }}</pre><RouterLink v-if="entry.entity_type === 'map_object'" :to="`/surveyor?object=${entry.entity_id}`">View on Surveyor ↗</RouterLink><RouterLink v-else-if="entry.entity_type === 'search_session'" :to="`/surveyor?session=${entry.entity_id}`">View search ↗</RouterLink><RouterLink v-else-if="entry.entity_type === 'task' && entry.after?.map_object_id" :to="`/surveyor?object=${entry.after.map_object_id}`">View field object ↗</RouterLink></article></div></section></div>
    <p v-else-if="!loading" class="journal-empty">No activity in this filter yet. Add a field marker or start a search session from Surveyor.</p>
  </main>
</template>
