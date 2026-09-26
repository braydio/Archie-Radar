<script setup>
import { reactive, watch } from 'vue'
import { coveragePreviewGeometry } from '../../surveyor/coveragePreview.js'
import { metersToFeet } from '../../surveyor/units.js'
import { clearSurveyorDraft, storeSurveyorDraft } from '../../surveyor/draftStorage.js'
const props = defineProps({ route: { type: Object, default: null }, method: { type: String, default: 'walking' }, session: { type: Object, default: null }, distance: { type: Number, default: 0 }, initialForm: { type: Object, default: null } })
const emit = defineEmits(['save', 'cancel'])
const widths = { walking: 15, bike: 20, car: 35, flyering: 20, other: 15 }
const form = reactive({ result_summary: 'No cat activity reported', notes: '', outcome: 'no_activity', create_coverage: false, buffer_meters: widths[props.method] || 15 })
form.create_followup = false
form.add_evidence = false
if (props.initialForm) Object.assign(form, props.initialForm)
watch(form, () => storeSurveyorDraft('search_result', { form: { ...form } }), { deep: true })
function duration() { return props.session?.started_at ? `${Math.max(0, Math.round((Date.now() - new Date(props.session.started_at).getTime()) / 60000))} min` : '—' }
function save() { clearSurveyorDraft('search_result'); emit('save', { ...form }) }
function cancel() { clearSurveyorDraft('search_result'); emit('cancel') }
watch(() => [form.create_coverage, form.buffer_meters, props.route], () => emit('coveragePreview', form.create_coverage && props.route ? coveragePreviewGeometry(props.route, form.buffer_meters) : null), { deep: true, immediate: true })
</script>
<template>
  <form class="field-sheet" @submit.prevent="save"><header><div><p class="eyebrow">SEARCH SESSION · COMPLETE</p><h2>Finish search</h2></div><button type="button" aria-label="Cancel" @click="cancel">×</button></header>
    <div class="session-completion-metrics"><span><strong>{{ duration() }}</strong>duration</span><span><strong>{{ Math.round(metersToFeet(distance)) }} ft</strong>distance</span><span><strong>{{ session?.started_at ? new Date(session.started_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—' }}</strong>started</span><span><strong>{{ new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) }}</strong>ended</span></div>
    <label>Outcome<select v-model="form.outcome"><option value="no_activity">No notable activity</option><option value="possible_evidence">Possible evidence</option><option value="cat_activity">Cat activity</option><option value="wildlife_activity">Wildlife activity</option><option value="camera_maintenance">Camera maintenance</option><option value="follow_up_needed">Follow-up required</option><option value="other">Other</option></select></label>
    <label>Result summary<input v-model="form.result_summary" maxlength="500" /></label><label>Notes<textarea v-model="form.notes" rows="4"></textarea></label>
    <fieldset v-if="form.create_coverage && route?.type === 'LineString' && route.coordinates?.length >= 2"><label>Search width · approximate coverage<select v-model.number="form.buffer_meters"><option :value="5">{{ Math.round(metersToFeet(5)) }} ft (5 m)</option><option :value="10">{{ Math.round(metersToFeet(10)) }} ft (10 m)</option><option :value="15">{{ Math.round(metersToFeet(15)) }} ft (15 m)</option><option :value="25">{{ Math.round(metersToFeet(25)) }} ft (25 m)</option><option :value="50">{{ Math.round(metersToFeet(50)) }} ft (50 m)</option></select></label><small>Approximate area physically covered. Review the shaded preview on the map before saving.</small></fieldset>
    <fieldset class="session-completion-options"><legend>After saving</legend><label><input v-model="form.create_coverage" type="checkbox" :disabled="!route?.coordinates?.length" /> Create searched corridor from route</label><label><input v-model="form.create_followup" type="checkbox" /> Create a follow-up task</label><label><input v-model="form.add_evidence" type="checkbox" /> Add an evidence marker</label></fieldset>
    <footer><button type="button" class="secondary-button" @click="cancel">Cancel</button><button class="primary" type="submit">Save search</button></footer>
  </form>
</template>
