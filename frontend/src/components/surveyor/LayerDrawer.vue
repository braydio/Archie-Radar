<script setup>
defineProps({ modelValue: { type: Object, required: true }, counts: { type: Object, default: () => ({}) } })
const emit = defineEmits(['update:modelValue', 'close'])
</script>

<template>
  <aside class="layer-drawer" aria-label="Map layers">
    <header><div><p class="eyebrow">MAP LAYERS</p><h2>Field layers</h2></div><button aria-label="Close layers" @click="$emit('close')">×</button></header>
    <section><h3>MY SEARCH</h3><label><input type="checkbox" :checked="modelValue.objects" @change="emit('update:modelValue', { ...modelValue, objects: $event.target.checked })" /> Markers, notes, zones, and lines <b>{{ counts.objects || 0 }}</b></label><label><input type="checkbox" :checked="modelValue.links" @change="emit('update:modelValue', { ...modelValue, links: $event.target.checked })" /> Object connections <b>{{ counts.links || 0 }}</b></label><label><input type="checkbox" :checked="modelValue.cameras" @change="emit('update:modelValue', { ...modelValue, cameras: $event.target.checked })" /> Trail cameras and sight cones <b>{{ counts.cameras || 0 }}</b></label><label><input type="checkbox" :checked="modelValue.cameraHistory" @change="emit('update:modelValue', { ...modelValue, cameraHistory: $event.target.checked })" /> Previous camera placements</label><label><input type="checkbox" :checked="modelValue.candidates" @change="emit('update:modelValue', { ...modelValue, candidates: $event.target.checked })" /> Candidate reports <b>{{ counts.candidates || 0 }}</b></label></section>
    <section><h3>LANDSCAPE</h3><label><input type="checkbox" :checked="modelValue.landcover" @change="emit('update:modelValue', { ...modelValue, landcover: $event.target.checked })" /> Annual NLCD land cover · 2025</label><p>USGS / MRLC · 30 m land-cover context</p></section>
    <section><h3>WILDLIFE DATA</h3><p>Public observation providers will appear here when connected. Source observations will keep their own provenance.</p></section>
  </aside>
</template>
