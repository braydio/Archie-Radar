<script setup>
import { ref } from 'vue'
import MediaTile from './MediaTile.vue'
import MediaViewer from './MediaViewer.vue'
const props = defineProps({ items: { type: Array, default: () => [] }, api: { type: String, required: true }, title: { type: String, default: 'Media' }, selectable: Boolean })
const emit = defineEmits(['delete', 'select'])
const current = ref(null)
function remove(item) { emit('delete', item); current.value = null }
</script>
<template>
  <section class="media-gallery">
    <h3 v-if="title">{{ title }} · {{ items.length }}</h3>
    <div v-if="items.length" class="media-gallery-grid"><MediaTile v-for="item in items" :key="item.id" :item="item" :api="api" @open="current=$event" /></div>
    <p v-else class="inspector-meta">No media attached yet.</p>
    <MediaViewer v-if="current" :item="current" :api="api" @close="current=null" @delete="remove" />
  </section>
</template>
