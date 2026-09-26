<script setup>
defineProps({ candidate: { type: Object, required: true } })
const emit = defineEmits(['close', 'evidence'])
</script>
<template>
  <aside class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">CANDIDATE REPORT</p><h2>{{ candidate.name || 'Found cat report' }}</h2></div><button aria-label="Close inspector" @click="emit('close')">×</button></div>
    <p class="inspector-meta">{{ candidate.source }} · {{ candidate.reported_at ? new Date(candidate.reported_at).toLocaleDateString() : 'Report date unknown' }}<span v-if="candidate.distance_from_home_miles != null"> · {{ Number(candidate.distance_from_home_miles).toFixed(1) }} mi from home</span></p><p>{{ candidate.location_text }}</p>
    <div class="inspector-buttons"><a class="primary candidate-open-link" :href="`/#post-${candidate.id}`">Open Candidate</a><button class="secondary-button" @click="emit('evidence')">Create evidence marker</button></div>
  </aside>
</template>
