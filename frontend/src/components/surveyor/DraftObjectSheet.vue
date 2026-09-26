<script setup>
import { computed, reactive, watch } from 'vue'
import { PIN_GROUPS, OBJECT_TYPES } from '../../surveyor/objectTypes.js'

const props = defineProps({ kind: { type: String, required: true }, geometry: { type: Object, required: true }, defaultSubtype: { type: String, default: '' }, defaultName: { type: String, default: '' }, cameraDefaults: { type: Object, default: () => ({}) } })
const emit = defineEmits(['save', 'cancel'])
const form = reactive({ subtype: '', name: '', notes: '', occurredAt: '', confidence: 'possible', epistemicState: 'observed', cameraModel: '', powerType: '', heading: 0, fov: 62, range: 15 })
watch(() => [props.kind, props.defaultSubtype, props.defaultName, props.cameraDefaults], () => {
  const defaults = OBJECT_TYPES[props.defaultSubtype]
  Object.assign(form, { subtype: props.defaultSubtype, name: props.defaultName, notes: '', occurredAt: '', confidence: defaults?.defaultConfidence || 'possible', epistemicState: defaults?.defaultEpistemicState || (props.kind === 'line' || props.kind === 'zone' ? 'planning' : 'observed'), cameraModel: '', powerType: '', heading: props.cameraDefaults.heading ?? 0, fov: props.cameraDefaults.fov ?? 62, range: props.cameraDefaults.range ?? 15 })
}, { immediate: true, deep: true })
const title = computed(() => ({ pin: 'Add field marker', note: 'Add field note', zone: 'Save search zone', line: 'Save corridor', camera: 'Place trail camera' })[props.kind] || 'Add field object')
function submit() {
  emit('save', { kind: props.kind, geometry: props.geometry, subtype: form.subtype || props.defaultSubtype, name: form.name.trim(), notes: form.notes,
    occurred_at: form.occurredAt ? new Date(form.occurredAt).toISOString() : null, confidence: form.confidence, epistemic_state: form.epistemicState,
    camera_model: form.cameraModel, power_type: form.powerType, heading_degrees: Number(form.heading), fov_degrees: Number(form.fov), range_meters: Number(form.range) })
}
</script>

<template>
  <form class="field-sheet" @submit.prevent="submit">
    <header><div><p class="eyebrow">SURVEYOR · DRAFT</p><h2>{{ title }}</h2></div><button type="button" aria-label="Cancel" @click="emit('cancel')">×</button></header>
    <label v-if="kind === 'pin' || kind === 'zone'">Type<select v-model="form.subtype"><optgroup v-for="group in PIN_GROUPS" :key="group.key" :label="group.label"><option v-for="type in group.types" :key="type" :value="type">{{ OBJECT_TYPES[type].label }}</option></optgroup><option v-if="kind === 'zone'" value="needs_search">Needs search</option></select></label>
    <label v-if="kind === 'line'">Corridor type<select v-model="form.subtype"><option value="known_cat_highway">Known cat highway</option><option value="probable_animal_corridor">Probable animal corridor</option><option value="possible_corridor">Possible corridor</option><option value="custom">Custom corridor</option></select></label>
    <label>Name<input v-model="form.name" maxlength="180" :placeholder="kind === 'note' ? 'Field note' : kind === 'camera' ? 'Camera name' : 'Optional name'" /></label>
    <template v-if="kind === 'camera'">
      <label>Camera model<input v-model="form.cameraModel" /></label><label>Power type<input v-model="form.powerType" placeholder="Battery, solar…" /></label>
      <div class="field-form-grid"><label>Heading °<input v-model.number="form.heading" type="number" min="0" max="360" /></label><label>FOV °<input v-model.number="form.fov" type="number" min="1" max="179" /></label><label>Range m<input v-model.number="form.range" type="number" min="1" max="5000" /></label></div>
    </template>
    <template v-if="kind === 'pin' || kind === 'line' || kind === 'zone'">
      <label>Confidence<select v-model="form.confidence"><option value="confirmed">Confirmed</option><option value="strong">Strong</option><option value="possible">Possible</option><option value="uncertain">Uncertain</option><option value="context">Context only</option></select></label>
      <label>Interpretation<select v-model="form.epistemicState"><option value="observed">Observed</option><option value="inferred">Inferred</option><option value="hypothesis">Hypothesis</option><option value="planning">Planning</option></select></label>
    </template>
    <label v-if="kind === 'pin' || kind === 'note'">Occurred at<input v-model="form.occurredAt" type="datetime-local" /></label>
    <label>{{ kind === 'note' ? 'Note' : 'Notes' }}<textarea v-model="form.notes" rows="4"></textarea></label>
    <footer><button type="button" class="secondary-button" @click="emit('cancel')">Cancel</button><button class="primary" type="submit">Save</button></footer>
  </form>
</template>
