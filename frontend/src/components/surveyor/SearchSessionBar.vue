<script setup>
defineProps({ activeSession: { type: Object, default: null }, method: { type: String, required: true }, distance: { type: Number, default: 0 }, loading: Boolean })
const emit = defineEmits(['start', 'end', 'update:method', 'layers'])
</script>
<template>
  <div class="surveyor-actions"><span v-if="loading">Loading field data…</span>
    <template v-if="!activeSession"><select class="session-method" :value="method" @change="emit('update:method', $event.target.value)"><option value="walking">Walking</option><option value="bike">Bike</option><option value="car">Car</option><option value="stationary_observation">Observation</option><option value="camera_maintenance">Camera care</option><option value="flyering">Flyering</option></select><button class="session-button" @click="emit('start')">Start search</button></template>
    <button v-else class="session-button active" @click="emit('end')">End search · {{ Math.round(distance) }} m</button><button @click="emit('layers')">Layers</button>
  </div>
</template>
