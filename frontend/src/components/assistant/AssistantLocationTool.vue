<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'

const AssistantMiniMap = defineAsyncComponent(() => import('./AssistantMiniMap.vue'))

const emit = defineEmits(['open-surveyor'])
import { API_BASE } from '../../apiBase.js'
const API = API_BASE
const open = ref(false)
const query = ref('')
const matches = ref([])
const home = ref(null)
const selectedIndex = ref(0)
const loading = ref(false)
const error = ref('')
const selected = computed(() => matches.value[selectedIndex.value] || null)

async function resolve() {
  if (!query.value.trim()) return
  loading.value = true; error.value = ''; matches.value = []; selectedIndex.value = 0
  try {
    const response = await fetch(`${API}/api/places/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: query.value.trim() }) })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || 'Could not locate that address')
    matches.value = body.matches || []; home.value = body.home
    if (!matches.value.length) error.value = 'No matching places found. Try adding the town or ZIP code.'
  } catch (cause) { error.value = cause.message }
  finally { loading.value = false }
}

function handoff() { if (selected.value && home.value) emit('open-surveyor', { ...selected.value, displayName: selected.value.display_name, home: home.value }) }
function openTool() { open.value = true }
function onGlobalLocate(event) {
  open.value = true
  const detail = event.detail || {}
  if (detail.latitude != null && detail.longitude != null && detail.home) {
    query.value = detail.displayName || detail.query || ''
    home.value = detail.home
    matches.value = [{ display_name: query.value || 'Candidate location', latitude: detail.latitude, longitude: detail.longitude,
      precision: detail.precision || 'place', distance_miles: detail.distance_miles ?? 0, bearing_degrees: detail.bearing_degrees ?? 0,
      bearing_label: detail.bearing_label || 'HOME' }]
    selectedIndex.value = 0
    return
  }
  query.value = detail.query || ''
  if (query.value) resolve()
}
onMounted(() => window.addEventListener('archie:locate', onGlobalLocate))
onBeforeUnmount(() => window.removeEventListener('archie:locate', onGlobalLocate))
</script>

<template>
  <div class="assistant-location-root">
    <button class="locate-address-trigger" type="button" @click="openTool">📍 Locate an address</button>
    <div v-if="open" class="assistant-location-backdrop" @click.self="open=false">
      <section class="assistant-location-dialog" role="dialog" aria-modal="true" aria-label="Locate an address relative to home">
        <header><div><p class="eyebrow">QUICK TOOL</p><h2>Locate an address</h2><p>See its straight-line distance and direction from home.</p></div><button aria-label="Close" @click="open=false">×</button></header>
        <form class="assistant-location-search" @submit.prevent="resolve"><label for="place-query">Address or place</label><div><input id="place-query" v-model="query" placeholder="64 Dollar Road, Chapel Hill, NC" autocomplete="street-address" /><button class="primary" :disabled="loading || query.trim().length < 3">{{ loading ? 'Searching…' : 'Locate' }}</button></div></form>
        <p v-if="error" class="assistant-location-error" role="status">{{ error }}</p>
        <div v-if="matches.length" class="assistant-location-results">
          <label v-if="matches.length > 1">Choose a match <select v-model.number="selectedIndex"><option v-for="(match, index) in matches" :key="`${match.latitude}:${match.longitude}`" :value="index">{{ match.display_name }}</option></select></label>
          <article v-if="selected" class="assistant-location-card"><AssistantMiniMap v-if="home" :home="home" :match="selected" /><div class="assistant-location-copy"><p class="eyebrow">{{ selected.precision }} · STRAIGHT-LINE</p><h3>{{ selected.display_name }}</h3><strong>{{ selected.distance_miles }} mi {{ selected.bearing_label }} of home</strong><p>Approximate bearing {{ selected.bearing_degrees }}°</p><button class="primary" @click="handoff">Open in Surveyor</button></div></article>
        </div>
      </section>
    </div>
  </div>
</template>
