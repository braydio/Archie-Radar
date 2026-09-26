<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const entries = ref([])
const filter = ref('all')
const loading = ref(true)
const error = ref('')
const FILTER_TYPES = {
  searches: ['search_started', 'search_completed'],
  observations: ['object_created'],
  cameras: ['camera_moved', 'camera_aimed', 'camera_created'],
  candidates: ['candidate_reviewed', 'candidate_linked'],
  access: ['access_updated'], wildlife: ['wildlife_observed']
}
const visibleEntries = computed(() => filter.value === 'all' ? entries.value : entries.value.filter(item => (FILTER_TYPES[filter.value] || []).includes(item.event_type)))
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

onMounted(loadEvents)
watch(filter, loadEvents)
</script>

<template>
  <main class="journal-page"><p class="eyebrow">ARCHIE RADAR · FIELD JOURNAL</p><h1>Journal</h1><p class="journal-intro">Search sessions, field observations, camera changes, and candidate reviews in one chronological record.</p>
    <div class="journal-controls"><label>Show<select v-model="filter"><option value="all">All activity</option><option value="searches">Searches</option><option value="observations">Sightings and evidence</option><option value="cameras">Cameras</option><option value="candidates">Candidates</option><option value="access">Access</option><option value="wildlife">Wildlife</option></select></label><RouterLink to="/surveyor">Open Surveyor map ↗</RouterLink></div>
    <p v-if="error" class="surveyor-error">{{ error }}</p><p v-else-if="loading">Loading field journal…</p>
    <div v-else-if="groupedEntries.length" class="journal-days"><section v-for="[date, dayEntries] in groupedEntries" :key="date"><h2>{{ date }}</h2><div class="journal-list"><article v-for="entry in dayEntries" :key="entry.id"><time>{{ new Date(entry.occurred_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) }}</time><h3>{{ entry.action }}</h3><p v-if="entry.notes">{{ entry.notes }}</p><pre v-else-if="entry.event_type === 'search_completed' && entry.after?.result_summary">{{ entry.after.result_summary }}</pre><RouterLink v-if="entry.entity_type === 'map_object'" :to="`/surveyor?object=${entry.entity_id}`">View on Surveyor ↗</RouterLink><RouterLink v-else-if="entry.entity_type === 'search_session'" :to="`/surveyor?session=${entry.entity_id}`">View search ↗</RouterLink></article></div></section></div>
    <p v-else-if="!loading" class="journal-empty">No activity in this filter yet. Add a field marker or start a search session from Surveyor.</p>
  </main>
</template>
