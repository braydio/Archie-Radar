<script setup>
import { computed } from 'vue'
import { feetToMeters, metersToFeet } from '../../surveyor/units.js'
defineProps({ history: { type: Array, default: () => [] } })
const heading = defineModel('heading', { type: Number })
const fov = defineModel('fov', { type: Number })
const range = defineModel('range', { type: Number })
const rangeFeet = computed({ get: () => Math.round(metersToFeet(range.value)), set: value => { range.value = feetToMeters(value) } })
</script>
<template>
  <div class="trail-camera-editor"><label>Heading · degrees<input v-model.number="heading" type="number" min="0" max="360" /></label><label>Field of view · degrees<input v-model.number="fov" type="number" min="1" max="179" /></label><label>Useful range · feet<input v-model.number="rangeFeet" type="number" min="3" max="16404" /></label>
    <div class="camera-history-list"><strong>Placement history</strong><p v-for="placement in history" :key="placement.id">{{ placement.removed_at ? new Date(placement.installed_at).toLocaleDateString() + ' – ' + new Date(placement.removed_at).toLocaleDateString() : 'Current placement' }} · {{ Math.round(placement.heading_degrees) }}° · {{ Math.round(placement.fov_degrees) }}° · {{ Math.round(metersToFeet(placement.range_meters)) }} ft</p></div>
    <small>Heading, field of view, and range describe the map cone. Save as a new placement to preserve an aim change in history.</small>
  </div>
</template>
