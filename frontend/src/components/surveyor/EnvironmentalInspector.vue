<script setup>
import { computed } from 'vue'
const props = defineProps({ feature: { type: Object, required: true } })
defineEmits(['close', 'add-note', 'add-marker'])
const detail = computed(() => props.feature.properties || {})
const wildlife = computed(() => detail.value.provider === 'iNaturalist')
const waterbody = computed(() => detail.value.feature_type === 'waterbody')
const boundary = computed(() => ['county', 'state'].includes(detail.value.feature_type))
const title = computed(() => detail.value.common_name || (detail.value.feature_type === 'county' && detail.value.name && !/county$/i.test(detail.value.name) ? `${detail.value.name} County` : detail.value.name) || (waterbody.value ? 'Mapped waterbody' : 'Mapped stream / river'))
function displayDate(value) { return value ? new Date(value).toLocaleDateString() : 'Date unavailable' }
</script>

<template>
  <aside class="surveyor-inspector environment-inspector" aria-label="Environmental feature details">
    <div class="inspector-heading"><div><p class="eyebrow">{{ detail.provider || 'Environmental map feature' }}</p><h2>{{ title }}</h2></div><button aria-label="Close feature details" @click="$emit('close')">×</button></div>
    <template v-if="boundary"><p>{{ detail.feature_type === 'county' ? 'County boundary' : 'State boundary' }}</p><p>{{ detail.provider }}</p></template>
    <template v-else-if="!wildlife"><p>{{ waterbody ? 'Waterbody' : 'Stream / river' }}</p><p>NC OneMap hydrography</p></template>
    <template v-else>
      <p><i>{{ detail.scientific_name }}</i></p>
      <p>Observed {{ displayDate(detail.observed_at) }}</p>
      <p v-if="detail.added_at && detail.added_at.slice(0, 10) !== detail.observed_at">Added {{ displayDate(detail.added_at) }}</p>
      <p>Quality grade: {{ detail.quality_grade || 'Unavailable' }}</p>
      <p v-if="detail.coordinate_accuracy_m != null">Location accuracy: {{ Math.round(detail.coordinate_accuracy_m) }} m</p>
      <p v-if="detail.geoprivacy === 'obscured'" class="geoprivacy-warning">iNaturalist obscures this observation’s location. The displayed point is the public coordinate.</p>
      <a v-if="detail.url" :href="detail.url" target="_blank" rel="noreferrer">Open iNaturalist record ↗</a>
    </template>
    <div class="environment-actions"><button type="button" @click="$emit('add-note')">Add note here</button><button type="button" @click="$emit('add-marker')">Add field marker…</button></div>
    <p class="inspector-meta">External map information is reference context. It is not Archie Radar field evidence.</p>
  </aside>
</template>
