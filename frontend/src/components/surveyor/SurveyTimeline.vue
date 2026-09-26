<script setup>
import { computed } from 'vue'

const props = defineProps({ modelValue: { type: Object, required: true } })
const emit = defineEmits(['update:modelValue'])
const presets = [
  ['now', 'Now'], ['tonight', 'Tonight'], ['7d', '7 days'], ['30d', '30 days'],
  ['since_archie', 'Since Archie disappeared'], ['custom', 'Custom']
]
const now = () => new Date()
function localInput(date) {
  const d = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return d.toISOString().slice(0, 16)
}
function rangeFor(preset) {
  const end = now()
  if (preset === 'now') return { preset, from: localInput(new Date(end.getTime() - 24 * 3600000)), to: localInput(end) }
  if (preset === 'tonight') {
    const start = new Date(end); start.setHours(18, 0, 0, 0)
    if (end.getHours() < 6) start.setDate(start.getDate() - 1)
    const finish = new Date(start); finish.setDate(finish.getDate() + 1); finish.setHours(6, 0, 0, 0)
    return { preset, from: localInput(start), to: localInput(finish) }
  }
  if (preset === '7d' || preset === '30d') {
    const start = new Date(end); start.setDate(start.getDate() - (preset === '7d' ? 7 : 30))
    return { preset, from: localInput(start), to: localInput(end) }
  }
  if (preset === 'since_archie') return { preset, from: '2026-06-28T00:00', to: localInput(end) }
  return { ...props.modelValue, preset }
}
const title = computed(() => {
  if (props.modelValue.preset === 'all') return 'All dates'
  const from = new Date(props.modelValue.from).toLocaleDateString()
  const to = new Date(props.modelValue.to).toLocaleDateString()
  return `${from} – ${to}`
})
function setPreset(event) { emit('update:modelValue', rangeFor(event.target.value)) }
function updateRange(key, event) { emit('update:modelValue', { ...props.modelValue, preset: 'custom', [key]: event.target.value }) }
</script>

<template>
  <div class="survey-timeline">
    <div class="timeline-label"><strong>TIME</strong><span>{{ title }}</span></div>
    <select :value="modelValue.preset" aria-label="Timeline preset" @change="setPreset"><option v-for="[value,label] in presets" :key="value" :value="value">{{ label }}</option><option value="all">All dates</option></select>
    <template v-if="modelValue.preset === 'custom'"><label><span>From</span><input type="datetime-local" :value="modelValue.from" @change="updateRange('from', $event)" /></label><label><span>To</span><input type="datetime-local" :value="modelValue.to" @change="updateRange('to', $event)" /></label></template>
    <div v-else class="timeline-track" aria-hidden="true"><span></span><i></i></div>
  </div>
</template>
