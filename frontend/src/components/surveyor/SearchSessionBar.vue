<script setup>
import { formatDistance } from '../../surveyor/units.js'
const format = formatDistance
defineProps({ activeSession: { type: Object, default: null }, method: { type: String, required: true }, distance: { type: Number, default: 0 }, loading: Boolean })
const emit = defineEmits(['start', 'end', 'update:method', 'layers', 'media', 'observation', 'note'])
</script>
<template>
  <div class="surveyor-actions"><span v-if="loading">Loading field data…</span>
    <template v-if="!activeSession"><select class="session-method" :value="method" @change="emit('update:method', $event.target.value)"><option value="walking">Walking</option><option value="bike">Bike</option><option value="car">Car</option><option value="stationary_observation">Observation</option><option value="camera_maintenance">Camera care</option><option value="flyering">Flyering</option></select><button class="session-button" @click="emit('start')">Start search</button></template>
    <template v-else><button class="secondary-button quick-observation-button" @click="emit('observation')">＋ Observation</button><button class="secondary-button" @click="emit('note')">＋ Note</button><button class="secondary-button session-media-button" @click="emit('media')">Media</button><button class="session-button active" @click="emit('end')">Stop · {{ format(distance) }}</button></template><button @click="emit('layers')">Layers</button>
  </div>
</template>
