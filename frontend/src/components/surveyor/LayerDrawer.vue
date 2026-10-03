<script setup>
const props = defineProps({ modelValue: { type: Object, required: true }, counts: { type: Object, default: () => ({}) }, providerStatus: { type: Object, default: () => ({}) } })
const emit = defineEmits(['update:modelValue', 'close', 'retry-provider'])
const species = [['coyote', 'Coyote'], ['red_fox', 'Red fox'], ['gray_fox', 'Gray fox'], ['bobcat', 'Bobcat'], ['raccoon', 'Raccoon'], ['deer', 'Deer']]
function set(key, value) { emit('update:modelValue', { ...props.modelValue, [key]: value }) }
function toggleSpecies(key, value) { set('wildlifeSpecies', { ...props.modelValue.wildlifeSpecies, [key]: value }) }
function state(key) { return props.providerStatus[key] || 'loading' }
function label(key) { return ({ off: 'off', zoom_in: 'zoom in', select_species: 'choose species', loading: 'loading', ready: 'ready', degraded: 'degraded', unavailable: 'unavailable' })[state(key)] || state(key) }
function canRetry(key) { return ['degraded', 'unavailable'].includes(state(key)) }
</script>

<template>
  <aside class="layer-drawer" aria-label="Map overlays">
    <header><div><p class="eyebrow">OVERLAYS</p><h2>Map context</h2></div><button aria-label="Close overlays" @click="$emit('close')">×</button></header>
    <section><h3>YOUR SEARCH</h3>
      <label><input type="checkbox" :checked="modelValue.objects" @change="set('objects', $event.target.checked)" /> Markers, notes, zones, and lines <b>{{ counts.objects || 0 }}</b></label>
      <label><input type="checkbox" :checked="modelValue.links" @change="set('links', $event.target.checked)" /> Object connections <b>{{ counts.links || 0 }}</b></label>
      <label><input type="checkbox" :checked="modelValue.cameras" @change="set('cameras', $event.target.checked)" /> Trail cameras and sight cones <b>{{ counts.cameras || 0 }}</b></label>
      <label><input type="checkbox" :checked="modelValue.cameraHistory" @change="set('cameraHistory', $event.target.checked)" /> Previous camera placements</label>
      <label><input type="checkbox" :checked="modelValue.candidates" @change="set('candidates', $event.target.checked)" /> Candidate reports <b>{{ counts.candidates || 0 }}</b></label>
    </section>
    <section><h3>LAND + WATER</h3>
      <label><input type="checkbox" :checked="modelValue.landcover" @change="set('landcover', $event.target.checked)" /> Annual NLCD · 2025 <b class="provider-status">{{ label('landcover') }}</b></label><p>USGS/MRLC</p>
      <label><input type="checkbox" :checked="modelValue.hydrography" @change="set('hydrography', $event.target.checked)" /> Streams / waterbodies <b class="provider-status">{{ label('hydrography') }}</b></label><p>NC OneMap <button v-if="canRetry('hydrography')" class="inline-button" @click="emit('retry-provider', 'hydrography')">Retry</button></p>
      <label><input type="checkbox" :checked="modelValue.wetlands" @change="set('wetlands', $event.target.checked)" /> Wetlands · USFWS NWI <b class="provider-status">{{ label('wetlands') }}</b></label>
      <label><input type="checkbox" :checked="modelValue.boundaries" @change="set('boundaries', $event.target.checked)" /> County / state boundaries <b class="provider-status">{{ label('boundaries') }}</b></label><p>US Census TIGERweb <button v-if="canRetry('boundaries')" class="inline-button" @click="emit('retry-provider', 'boundaries')">Retry</button></p>
    </section>
    <section><h3>WILDLIFE OBSERVATIONS</h3>
      <label><input type="checkbox" :checked="modelValue.wildlife" @change="set('wildlife', $event.target.checked)" /> Public wildlife observations <b class="provider-status">{{ label('wildlife') }}</b></label><p>iNaturalist <button v-if="canRetry('wildlife')" class="inline-button" @click="emit('retry-provider', 'wildlife')">Retry</button></p>
      <div v-if="modelValue.wildlife" class="wildlife-species-grid"><label v-for="[key, name] in species" :key="key"><input type="checkbox" :checked="modelValue.wildlifeSpecies?.[key]" @change="toggleSpecies(key, $event.target.checked)" /> {{ name }}</label></div>
    </section>
  </aside>
</template>
