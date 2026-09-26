<script setup>
import { reactive, ref, watch } from 'vue'
import { clearSurveyorDraft, storeSurveyorDraft } from '../../surveyor/draftStorage.js'
const props = defineProps({ coordinates: { type: Array, required: true }, api: { type: String, required: true }, record: { type: Object, default: null }, initialForm: { type: Object, default: null } })
const emit = defineEmits(['save', 'cancel'])
const saving = ref(false)
const error = ref('')
const detailsOpen = ref(false)
const form = reactive({ name: '', access_status: 'unknown', search_permission: 'unknown', camera_permission: 'unknown', trap_permission: 'unknown', dog_count: '', outdoor_cat_count: '', contact_name: '', contact_method: '', last_contact_at: '', next_followup_at: '', contact_notes: '' })
watch(() => props.record, record => {
  if (record) Object.assign(form, { ...record, dog_count: record.dog_count ?? '', outdoor_cat_count: record.outdoor_cat_count ?? '',
    last_contact_at: record.last_contact_at ? new Date(record.last_contact_at).toISOString().slice(0, 16) : '',
    next_followup_at: record.next_followup_at ? new Date(record.next_followup_at).toISOString().slice(0, 16) : '' })
}, { immediate: true })
watch(form, () => storeSurveyorDraft('access', { coordinates: props.coordinates, record: props.record, form: { ...form } }), { deep: true })
async function submit() {
  saving.value = true; error.value = ''
  try {
    const payload = { ...form, ...(props.record ? {} : { longitude: props.coordinates[0], latitude: props.coordinates[1] }),
      dog_count: form.dog_count === '' ? null : Number(form.dog_count), outdoor_cat_count: form.outdoor_cat_count === '' ? null : Number(form.outdoor_cat_count),
      last_contact_at: form.last_contact_at ? new Date(form.last_contact_at).toISOString() : null,
      next_followup_at: form.next_followup_at ? new Date(form.next_followup_at).toISOString() : null }
    const path = props.record ? `/api/surveyor/access/${props.record.id}` : '/api/surveyor/access'
    const response = await fetch(`${props.api}${path}`, { method: props.record ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || 'Could not save access record')
    clearSurveyorDraft('access')
    emit('save', result)
  } catch (cause) { error.value = cause.message }
  finally { saving.value = false }
}
function cancel() { clearSurveyorDraft('access'); emit('cancel') }
if (props.initialForm) Object.assign(form, props.initialForm)
</script>
<template>
  <form class="field-sheet" @submit.prevent="submit">
    <header><div><p class="eyebrow">SURVEYOR · PROPERTY</p><h2>{{ record ? 'Update access' : 'Access details' }}</h2></div><button type="button" aria-label="Close" @click="cancel">×</button></header>
    <label>Property name<input v-model="form.name" maxlength="180" placeholder="Optional shorthand" /></label>
    <label>Access<select v-model="form.access_status"><option value="unknown">Unknown</option><option value="no_answer">No answer</option><option value="permission_granted">Permission granted</option><option value="partial_permission">Partial permission</option><option value="permission_denied">Permission denied</option><option value="do_not_contact">Do not contact</option></select></label>
    <div class="field-form-grid"><label>Dogs<input v-model="form.dog_count" type="number" min="0" placeholder="Unknown" /></label><label>Outdoor cats<input v-model="form.outdoor_cat_count" type="number" min="0" placeholder="Unknown" /></label></div>
    <label>Search permission<select v-model="form.search_permission"><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
    <label>Camera permission<select v-model="form.camera_permission"><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
    <label>Trap permission<select v-model="form.trap_permission"><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
    <button type="button" class="secondary-button" @click="detailsOpen=!detailsOpen">{{ detailsOpen ? 'Hide' : 'Contact details' }}</button>
    <template v-if="detailsOpen"><label>Contact name<input v-model="form.contact_name" /></label><label>Contact method<input v-model="form.contact_method" /></label><label>Last contact<input v-model="form.last_contact_at" type="datetime-local" /></label><label>Follow up on<input v-model="form.next_followup_at" type="datetime-local" /></label><label>Private contact notes<textarea v-model="form.contact_notes" rows="3"></textarea></label></template>
    <p v-if="error" class="surveyor-error">{{ error }}</p><footer><button type="button" class="secondary-button" @click="cancel">Cancel</button><button class="primary" :disabled="saving">{{ saving ? 'Saving…' : record ? 'Update access' : 'Save access record' }}</button></footer>
  </form>
</template>
