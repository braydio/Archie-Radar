<script setup>
import { onMounted, ref } from 'vue'
const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const entries = ref([])
const loading = ref(true)
const error = ref('')
onMounted(async () => {
  try {
    const response = await fetch(`${API}/api/surveyor/objects`)
    if (!response.ok) throw new Error('Field records are unavailable')
    entries.value = await response.json()
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
})
</script>

<template>
  <main class="journal-page"><p class="eyebrow">ARCHIE RADAR · FIELD JOURNAL</p><h1>Journal</h1><p class="journal-intro">A chronological view of the field record. Search sessions and event history will appear here as those tools are added.</p><p v-if="error" class="surveyor-error">{{ error }}</p><p v-else-if="loading">Loading field records…</p><section v-else-if="entries.length" class="journal-list"><article v-for="entry in entries" :key="entry.id"><time>{{ new Date(entry.occurred_at || entry.created_at).toLocaleString() }}</time><h2>{{ entry.name || entry.subtype || entry.object_type }}</h2><p>{{ entry.notes || 'No notes recorded.' }}</p><RouterLink :to="`/surveyor?object=${entry.id}`">View on Surveyor ↗</RouterLink></article></section><p v-else class="journal-empty">No field entries yet. Add a marker from Surveyor to start the journal.</p></main>
</template>
