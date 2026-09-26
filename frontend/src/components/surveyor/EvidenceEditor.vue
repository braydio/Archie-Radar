<script setup>
import { reactive, watch } from 'vue'
import { clearSurveyorDraft, storeSurveyorDraft } from '../../surveyor/draftStorage.js'
const props = defineProps({ object: { type: Object, required: true }, saving: Boolean, initialForm: { type: Object, default: null } })
const emit = defineEmits(['save'])
const resolutions = ['unresolved', 'supports_archie', 'likely_not_archie', 'ruled_out', 'context_only']
const form = reactive({ evidence_type: 'reported_observation', source_type: 'firsthand', source_name: '', resolution: 'unresolved', observer: '', species_guess: '' })
watch(() => props.object.id, () => Object.assign(form, {
  evidence_type: props.object.properties?.evidence_type || 'reported_observation',
  source_type: props.object.properties?.source_type || 'firsthand',
  source_name: props.object.properties?.source_name || '',
  resolution: props.object.properties?.resolution || 'unresolved',
  observer: props.object.properties?.observer || '', species_guess: props.object.properties?.species_guess || '',
}), { immediate: true })
if (props.initialForm) Object.assign(form, props.initialForm)
watch(form, () => storeSurveyorDraft('evidence', { object_id: props.object.id, form: { ...form } }), { deep: true })
function save() { clearSurveyorDraft('evidence'); emit('save', { ...props.object.properties, ...form }) }
</script>
<template>
  <section class="evidence-editor">
    <p class="eyebrow">EVIDENCE · {{ form.resolution.replaceAll('_', ' ').toUpperCase() }}</p>
    <label>Evidence type<select v-model="form.evidence_type"><option value="visual_sighting">Visual sighting</option><option value="camera_hit">Camera hit</option><option value="photo">Photo</option><option value="audio">Audio</option><option value="footprint">Footprint</option><option value="fur">Fur</option><option value="tracks">Tracks</option><option value="scat">Scat</option><option value="reported_observation">Reported observation</option><option value="other">Other</option></select></label>
    <label>Source<select v-model="form.source_type"><option value="firsthand">Firsthand</option><option value="camera">Camera</option><option value="public_report">Public report</option><option value="neighbor_report">Neighbor report</option><option value="shelter_report">Shelter report</option><option value="other">Other</option></select></label>
    <label>Source name<input v-model="form.source_name" maxlength="180" /></label>
    <label>Resolution<select v-model="form.resolution"><option v-for="resolution in resolutions" :key="resolution" :value="resolution">{{ resolution.replaceAll('_', ' ') }}</option></select></label>
    <label>Observer<input v-model="form.observer" maxlength="180" /></label>
    <label>Species guess<input v-model="form.species_guess" maxlength="120" /></label>
    <button type="button" class="primary" :disabled="saving" @click="save">Save evidence details</button>
  </section>
</template>
