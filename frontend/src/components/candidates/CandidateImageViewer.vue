<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps({ images: { type: Array, required: true }, index: { type: Number, default: 0 }, alt: { type: String, default: 'Candidate cat photo' } })
const emit = defineEmits(['close', 'change'])
const image = computed(() => props.images[props.index] || props.images[0])

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
  if (event.key === 'ArrowLeft' && props.images.length > 1) emit('change', (props.index + props.images.length - 1) % props.images.length)
  if (event.key === 'ArrowRight' && props.images.length > 1) emit('change', (props.index + 1) % props.images.length)
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="candidate-viewer-backdrop" role="dialog" aria-modal="true" aria-label="Candidate image viewer" @click.self="emit('close')">
    <button class="candidate-viewer-close" type="button" aria-label="Close image" @click="emit('close')">×</button>
    <button v-if="images.length > 1" class="candidate-viewer-arrow previous" type="button" aria-label="Previous image" @click="emit('change', (index + images.length - 1) % images.length)">‹</button>
    <figure class="candidate-viewer-content">
      <img v-if="image" :src="image.url" :alt="alt" />
      <figcaption v-if="image">{{ image.source_platform || 'Source photo' }}<template v-if="image.holding_entity"> · {{ image.holding_entity }}</template><span v-if="images.length > 1"> · {{ index + 1 }} / {{ images.length }}</span></figcaption>
    </figure>
    <button v-if="images.length > 1" class="candidate-viewer-arrow next" type="button" aria-label="Next image" @click="emit('change', (index + 1) % images.length)">›</button>
  </div>
</template>
