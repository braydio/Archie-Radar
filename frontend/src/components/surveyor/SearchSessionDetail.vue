<script setup>
import { onMounted, ref } from 'vue'
import { downloadMediaBundle } from '../../surveyor/mediaCapture.js'
const props = defineProps({ api: { type: String, required: true }, sessionId: { type: Number, required: true } })
const emit = defineEmits(['close', 'showRoute', 'showCoverage', 'addNote', 'addEvidence', 'createCoverage', 'createFollowup'])
const summary = ref(null)
const error = ref('')
const exporting = ref(false)
onMounted(async () => {
  try { const response = await fetch(`${props.api}/api/surveyor/sessions/${props.sessionId}/summary`); const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.detail || 'Session detail unavailable'); summary.value = body }
  catch (cause) { error.value = cause.message }
})
function duration(session) { if (!session.ended_at) return 'In progress'; return `${Math.max(0, Math.round((new Date(session.ended_at) - new Date(session.started_at)) / 60000))} min` }
function distance(meters) { return meters == null ? '—' : meters >= 1609 ? `${(meters / 1609.344).toFixed(1)} mi` : `${Math.round(meters * 3.28084)} ft` }
async function exportSessionMedia() {
  exporting.value = true
  try {
    const response = await fetch(`${props.api}/api/surveyor/media?limit=2000`)
    if (!response.ok) throw new Error('Session media could not be loaded')
    const all = await response.json()
    const objectIds = new Set((summary.value?.objects || []).map(item => item.id))
    const selected = all.filter(item => item.search_session_id === props.sessionId || objectIds.has(item.map_object_id))
    if (!selected.length) throw new Error('There is no media linked to this search yet')
    if (!confirm(`Export ${selected.length} media items from this search? Private contact details are excluded.`)) return
    await downloadMediaBundle(props.api, selected.map(item => item.id))
  } catch (cause) { error.value = cause.message }
  finally { exporting.value = false }
}
</script>
<template>
  <section class="field-sheet session-detail-sheet">
    <header><div><p class="eyebrow">FIELD JOURNAL · SESSION</p><h2>{{ summary?.session.method?.replaceAll('_', ' ') || 'Search' }} search</h2></div><button type="button" aria-label="Close session detail" @click="emit('close')">×</button></header>
    <p v-if="error" class="surveyor-error">{{ error }}</p>
    <template v-if="summary">
      <p>{{ new Date(summary.session.started_at).toLocaleString() }}<span v-if="summary.session.ended_at"> — {{ new Date(summary.session.ended_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) }}</span></p>
      <div class="session-metrics"><span><strong>{{ duration(summary.session) }}</strong>duration</span><span><strong>{{ distance(summary.session.distance_meters) }}</strong>distance</span></div>
      <h3>Field record</h3><p>{{ summary.session.result_summary || 'No result summary' }}</p><p>{{ summary.session.notes }}</p>
      <dl class="session-counts"><template v-for="(count, kind) in summary.objects_by_type" :key="kind"><dt>{{ kind.replaceAll('_', ' ') }}</dt><dd>{{ count }}</dd></template><dt>Attachments</dt><dd>{{ summary.attachment_count }}</dd><dt>Coverage zones</dt><dd>{{ summary.coverage_objects.length }}</dd><dt>Follow-ups</dt><dd>{{ summary.tasks_created }}</dd></dl>
      <footer><button class="secondary-button" @click="emit('showRoute', summary.session)">Show route</button><button class="secondary-button" @click="emit('showCoverage', summary.coverage_objects)">Show coverage</button><button class="secondary-button" @click="emit('addNote')">Add note</button><button class="secondary-button" @click="emit('addEvidence')">Add evidence</button><button class="secondary-button" @click="emit('createCoverage')">Create coverage</button><button class="secondary-button" @click="emit('createFollowup')">Create follow-up</button><button class="primary" :disabled="exporting" @click="exportSessionMedia">{{ exporting ? 'Preparing export…' : 'Export session media' }}</button></footer>
    </template>
  </section>
</template>
