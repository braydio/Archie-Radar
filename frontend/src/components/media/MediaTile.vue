<script setup>
import { ref, watch } from 'vue'
const props = defineProps({ item: { type: Object, required: true }, api: { type: String, required: true }, selected: Boolean, selectable: Boolean })
const emit = defineEmits(['open', 'toggle'])
const previewFailed = ref(false)
watch(() => props.item.id, () => { previewFailed.value = false })
function dateLabel(item) { const date = item.observed_at || item.created_at; return date ? new Date(date).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'Date unknown' }
</script>
<template>
  <article class="media-tile" :class="[`media-${item.attachment_type}`, { selected }]">
    <button class="media-tile-preview" type="button" :aria-label="selectable ? `Select ${item.original_filename}` : `Open ${item.original_filename}`" @click="selectable ? emit('toggle', item) : emit('open', item)">
      <img v-if="['image','video'].includes(item.attachment_type) && item.thumbnail_url && !previewFailed" :src="`${api}${item.thumbnail_url}`" :alt="item.caption || item.original_filename" loading="lazy" @error="previewFailed=true" />
      <span v-else class="media-type-icon">{{ item.attachment_type === 'audio' ? '♫' : item.attachment_type === 'video' ? '▶' : '▤' }}</span>
      <span v-if="item.attachment_type === 'video'" class="media-play-mark">▶</span>
      <span v-if="item.duration_seconds" class="media-duration">{{ Math.floor(item.duration_seconds / 60) }}:{{ String(Math.floor(item.duration_seconds % 60)).padStart(2,'0') }}</span>
    </button>
    <label v-if="selectable" class="media-select"><input type="checkbox" :checked="selected" @change="emit('toggle', item)" /> Select</label>
    <div class="media-tile-copy"><time>{{ dateLabel(item) }}</time><strong>{{ item.caption || item.original_filename }}</strong><small>{{ item.camera_name || item.map_object_name || item.session_label || item.linked_entities?.[0]?.label || item.attachment_type }}</small></div>
  </article>
</template>
