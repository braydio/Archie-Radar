<script setup>
import { computed, onMounted, ref, watch } from 'vue'
const props = defineProps({ api: { type: String, required: true }, attachmentId: { type: Number, required: true } })
const links = ref([])
const entities = ref([])
const entityType = ref('map_object')
const entityId = ref('')
const relationship = ref('related')
const error = ref('')
const saving = ref(false)
const types = [
  { value: 'map_object', label: 'Map object', path: '/api/surveyor/objects' },
  { value: 'search_session', label: 'Search session', path: '/api/surveyor/sessions' },
  { value: 'camera', label: 'Trail camera', path: '/api/surveyor/cameras' },
  { value: 'candidate_case', label: 'Candidate case', path: '/api/candidate-cases' },
]
const relationships = ['related', 'captured_during', 'evidence_for', 'camera_capture', 'source_media']
const selectedType = computed(() => types.find(item => item.value === entityType.value))
function idOf(item) { return item.id ?? item.case_id }
function labelOf(item) { return item.name || item.display_name || item.primary?.name || item.method?.replaceAll('_',' ') || `${selectedType.value.label} #${idOf(item)}` }
async function loadLinks() {
  try { const response = await fetch(`${props.api}/api/surveyor/attachments/${props.attachmentId}/links`); if (!response.ok) throw new Error('Links could not be loaded'); links.value = await response.json() }
  catch (cause) { error.value = cause.message }
}
async function loadEntities() {
  const type = selectedType.value
  if (!type) return
  try { const response = await fetch(`${props.api}${type.path}`); if (!response.ok) throw new Error(`${type.label} list is unavailable`); entities.value = await response.json(); entityId.value = String(idOf(entities.value[0]) || '') }
  catch (cause) { entities.value = []; error.value = cause.message }
}
async function add() {
  if (!entityId.value) return
  saving.value = true; error.value = ''
  try {
    const response = await fetch(`${props.api}/api/surveyor/attachments/${props.attachmentId}/links`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entity_type: entityType.value, entity_id: Number(entityId.value), relationship: relationship.value }) })
    const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body.detail || 'Media could not be linked')
    links.value.push(body)
  } catch (cause) { error.value = cause.message }
  finally { saving.value = false }
}
async function remove(link) {
  const response = await fetch(`${props.api}/api/surveyor/attachments/${props.attachmentId}/links/${link.id}`, { method: 'DELETE' })
  if (!response.ok) { error.value = 'Media link could not be removed.'; return }
  links.value = links.value.filter(item => item.id !== link.id)
}
onMounted(() => { loadLinks(); loadEntities() })
watch(entityType, loadEntities)
watch(() => props.attachmentId, () => { links.value = []; loadLinks() })
</script>

<template>
  <section class="media-link-editor">
    <h4>Linked records</h4>
    <ul v-if="links.length"><li v-for="link in links" :key="link.id"><span>{{ link.label }} · {{ link.relationship.replaceAll('_',' ') }}</span><button type="button" aria-label="Remove media link" @click="remove(link)">×</button></li></ul>
    <p v-else class="inspector-meta">No additional links.</p>
    <div class="media-link-controls"><label>Link to<select v-model="entityType"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>Record<select v-model="entityId"><option v-for="item in entities" :key="idOf(item)" :value="String(idOf(item))">{{ labelOf(item) }}</option></select></label><label>Relationship<select v-model="relationship"><option v-for="value in relationships" :key="value" :value="value">{{ value.replaceAll('_',' ') }}</option></select></label><button type="button" class="secondary-button" :disabled="saving || !entityId" @click="add">{{ saving ? 'Linking…' : 'Link media' }}</button></div>
    <p v-if="error" class="media-capture-error" role="status">{{ error }}</p>
  </section>
</template>
