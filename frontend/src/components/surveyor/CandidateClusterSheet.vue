<script setup>
const props = defineProps({ cluster: { type: Object, required: true } })
const emit = defineEmits(['close', 'open', 'evidence', 'zoom'])
</script>
<template>
  <section class="candidate-cluster-sheet" role="dialog" aria-label="Candidate reports in this cluster">
    <header><div><p class="eyebrow">CANDIDATE REPORTS</p><h2>{{ cluster.count }} reports near this approximate location</h2><small v-if="cluster.count > cluster.posts.length">Showing {{ cluster.posts.length }} of {{ cluster.count }}</small></div><button aria-label="Close" @click="emit('close')">×</button></header>
    <article v-for="post in cluster.posts" :key="post.id" class="candidate-cluster-row"><div><strong>{{ post.holding_entity || post.custody_label || post.title || 'Found cat report' }}</strong><p>{{ post.external_ids?.[0]?.label }} {{ post.external_ids?.[0]?.value }}<span v-if="post.record_count > 1"> · {{ post.record_count }} records</span><span v-if="post.distance_from_home_miles != null"> · {{ Number(post.distance_from_home_miles).toFixed(1) }} mi</span></p><small v-if="post.location_text">{{ post.location_text }}<span v-if="post.location_precision"> · {{ post.location_precision }} location</span></small></div><div><a class="secondary-button" :href="`/#post-${post.case_id || post.id}`">Open Candidate</a><button class="secondary-button" @click="emit('evidence', post.case_id || post.id)">Evidence</button></div></article>
    <footer><button class="secondary-button" @click="emit('zoom')">Zoom farther in</button><button class="secondary-button" @click="emit('close')">Close</button></footer>
  </section>
</template>
