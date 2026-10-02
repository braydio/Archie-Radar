<script setup>
import { ref } from 'vue'
const props = defineProps({ layers: { type: Object, required: true } })
const open = ref(false)
</script>

<template>
  <aside class="surveyor-map-legend" aria-label="Map legend">
    <button type="button" :aria-expanded="open" @click="open = !open">{{ open ? 'Hide legend' : 'Legend' }}</button>
    <ul v-if="open">
      <li><i class="legend-forest"></i>Woodland</li><li><i class="legend-developed"></i>Developed area</li><li><i class="legend-water"></i>Water</li>
      <li v-if="layers.wetlands"><i class="legend-wetland"></i>Mapped wetland · USFWS NWI</li>
      <li v-if="layers.boundaries"><i class="legend-boundary"></i>County / state boundary · Census</li>
      <li v-if="layers.wildlife"><i class="legend-wildlife"></i>Public wildlife observation · iNaturalist</li>
      <li><i class="legend-camera"></i>Current camera</li><li><i class="legend-camera-history"></i>Historical camera</li>
      <li><i class="legend-searched"></i>Searched area</li><li><i class="legend-needs-search"></i>Needs search</li>
    </ul>
  </aside>
</template>
