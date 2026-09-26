<script setup>
defineProps({ history: { type: Array, default: () => [] } })
const heading = defineModel('heading', { type: Number })
const fov = defineModel('fov', { type: Number })
const range = defineModel('range', { type: Number })
</script>
<template>
  <div class="trail-camera-editor"><label>Heading · degrees<input v-model.number="heading" type="number" min="0" max="360" /></label><label>Field of view · degrees<input v-model.number="fov" type="number" min="1" max="179" /></label><label>Useful range · meters<input v-model.number="range" type="number" min="1" max="5000" /></label>
    <div class="camera-history-list"><strong>Placement history</strong><p v-for="placement in history" :key="placement.id">{{ placement.removed_at ? new Date(placement.installed_at).toLocaleDateString() + ' – ' + new Date(placement.removed_at).toLocaleDateString() : 'Current placement' }} · {{ Math.round(placement.heading_degrees) }}° · {{ Math.round(placement.fov_degrees) }}° · {{ Math.round(placement.range_meters) }} m</p></div>
    <small>Heading, field of view, and range describe the map cone. Save as a new placement to preserve an aim change in history.</small>
  </div>
</template>
