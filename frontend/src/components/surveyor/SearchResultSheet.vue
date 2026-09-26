<script setup>
import { reactive, watch } from 'vue'
import { coveragePreviewGeometry } from '../../surveyor/coveragePreview.js'
const props = defineProps({ route: { type: Object, default: null }, method: { type: String, default: 'walking' } })
const emit = defineEmits(['save', 'cancel'])
const widths = { walking: 15, bike: 20, car: 35, flyering: 20, other: 15 }
const form = reactive({ result_summary: 'No cat activity reported', notes: '', outcome: 'no_activity', create_coverage: false, buffer_meters: widths[props.method] || 15 })
watch(() => [form.create_coverage, form.buffer_meters, props.route], () => emit('coveragePreview', form.create_coverage && props.route ? coveragePreviewGeometry(props.route, form.buffer_meters) : null), { deep: true, immediate: true })
</script>
<template>
  <form class="field-sheet" @submit.prevent="emit('save', { ...form })"><header><div><p class="eyebrow">SEARCH SESSION</p><h2>Finish search</h2></div><button type="button" aria-label="Cancel" @click="emit('cancel')">×</button></header>
    <label>Outcome<select v-model="form.outcome"><option value="no_activity">No activity</option><option value="possible_evidence">Possible evidence</option><option value="camera_maintenance">Camera maintenance</option><option value="follow_up_needed">Follow-up needed</option><option value="other">Other</option></select></label>
    <label>Result summary<input v-model="form.result_summary" maxlength="500" /></label><label>Notes<textarea v-model="form.notes" rows="4"></textarea></label>
    <fieldset v-if="route?.type === 'LineString' && route.coordinates?.length >= 2"><label><input v-model="form.create_coverage" type="checkbox" /> Create searched corridor from route</label><template v-if="form.create_coverage"><label>Search width · approximate coverage<select v-model.number="form.buffer_meters"><option :value="5">5 m</option><option :value="10">10 m</option><option :value="15">15 m</option><option :value="25">25 m</option><option :value="50">50 m</option></select></label><small>Approximate area physically covered. Review the shaded preview on the map before saving.</small></template></fieldset>
    <footer><button type="button" class="secondary-button" @click="emit('cancel')">Cancel</button><button class="primary" type="submit">Save search</button></footer>
  </form>
</template>
