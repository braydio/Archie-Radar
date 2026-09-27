<script setup>
import { computed, ref, watch } from 'vue'
import CandidateImageViewer from './CandidateImageViewer.vue'
import './candidate.css'

const props = defineProps({
  image: { type: Object, default: null },
  alt: { type: String, default: 'Candidate cat photo' },
  imageWidth: { type: Number, default: null },
  imageHeight: { type: Number, default: null },
  photoSimilarity: { type: Number, default: null },
  otherImages: { type: Array, default: () => [] },
  caseId: { type: [Number, String], default: null }
})
const emit = defineEmits(['selectImage', 'unavailable'])
const activeIndex = ref(0)
const viewerOpen = ref(false)
const failedUrls = ref(new Set())
const images = computed(() => {
  const all = [props.image, ...props.otherImages].filter(item => item?.url)
  const seen = new Set()
  return all.filter(item => {
    if (seen.has(item.url)) return false
    seen.add(item.url)
    return !failedUrls.value.has(item.url)
  })
})
const activeImage = computed(() => images.value[activeIndex.value] || null)
const similarity = computed(() => activeImage.value?.photo_similarity ?? props.photoSimilarity)
const aspect = computed(() => {
  const width = activeImage.value?.width || props.imageWidth
  const height = activeImage.value?.height || props.imageHeight
  return width && height ? width / height : null
})
const shape = computed(() => aspect.value == null ? 'unknown' : aspect.value < 0.85 ? 'portrait' : aspect.value < 1.15 ? 'square' : 'landscape')
watch(() => props.caseId, () => { activeIndex.value = 0; viewerOpen.value = false; failedUrls.value = new Set() })
watch(images, items => {
  if (activeIndex.value >= items.length) activeIndex.value = 0
  if (!items.length) emit('unavailable')
})

function select(index) {
  activeIndex.value = index
  emit('selectImage', images.value[index])
}
function failCurrent() {
  if (!activeImage.value) return
  const failed = new Set(failedUrls.value)
  failed.add(activeImage.value.url)
  failedUrls.value = failed
  activeIndex.value = 0
}
</script>

<template>
  <section v-if="activeImage" class="candidate-media" aria-label="Candidate photos">
    <button class="candidate-media-stage" :class="`source-${shape}`" type="button" :aria-label="`Open full image for ${alt}`" @click="viewerOpen = true">
      <img :src="activeImage.url" :alt="alt" :width="activeImage.width || imageWidth || undefined" :height="activeImage.height || imageHeight || undefined" loading="lazy" decoding="async" @error="failCurrent" />
      <span v-if="similarity != null" class="candidate-photo-signal">Visual {{ Math.round(similarity * 100) }}%</span>
      <span v-if="images.length > 1" class="candidate-media-count">{{ activeIndex + 1 }} / {{ images.length }}</span>
    </button>
    <div v-if="images.length > 1" class="candidate-media-controls" aria-label="Choose candidate image">
      <button v-for="(item, index) in images" :key="item.url" type="button" :class="{ active: index === activeIndex }" :aria-label="`Show image ${index + 1} of ${images.length}`" :aria-pressed="index === activeIndex" @click="select(index)">{{ index + 1 }}</button>
    </div>
    <CandidateImageViewer v-if="viewerOpen" :images="images" :index="activeIndex" :alt="alt" @close="viewerOpen = false" @change="select" />
  </section>
</template>
