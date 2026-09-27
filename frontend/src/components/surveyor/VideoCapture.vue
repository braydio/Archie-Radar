<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

const props = defineProps({ maxMegabytes: { type: Number, default: 500 } })
const emit = defineEmits(['select', 'cancel'])
const cameraInput = ref(null)
const fileInput = ref(null)
const selected = ref(null)
const previewUrl = ref('')
const duration = ref(null)
const fileSize = computed(() => selected.value ? `${(selected.value.size / 1024 / 1024).toFixed(1)} MB` : '')
const tooLarge = computed(() => selected.value && selected.value.size > props.maxMegabytes * 1024 * 1024)
function release() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = ''; duration.value = null }
function choose(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  release(); selected.value = file; previewUrl.value = URL.createObjectURL(file)
}
function setDuration(event) {
  if (Number.isFinite(event.target.duration)) duration.value = Math.round(event.target.duration)
  if (selected.value) { selected.value.media_width = event.target.videoWidth || undefined; selected.value.media_height = event.target.videoHeight || undefined }
}
function formatDuration(value) { return value == null ? 'Duration unavailable' : `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}` }
function retake() { selected.value = null; release(); cameraInput.value?.click() }
function cancel() { selected.value = null; release(); emit('cancel') }
function useVideo() { if (!selected.value || tooLarge.value) return; selected.value.duration_seconds = duration.value; emit('select', selected.value); selected.value = null; release() }
onBeforeUnmount(release)
</script>

<template>
  <section class="video-capture" aria-label="Video evidence capture">
    <template v-if="!selected">
      <div class="media-capture-actions">
        <button type="button" class="secondary-button" @click="cameraInput?.click()">Record video</button>
        <button type="button" class="secondary-button" @click="fileInput?.click()">Choose video</button>
      </div>
      <input ref="cameraInput" class="visually-hidden" type="file" accept="video/*" capture="environment" @change="choose" />
      <input ref="fileInput" class="visually-hidden" type="file" accept="video/*" @change="choose" />
    </template>
    <template v-else>
      <video class="media-capture-video-preview" :src="previewUrl" controls playsinline preload="metadata" @loadedmetadata="setDuration"></video>
      <p class="media-file-summary">{{ selected.name }} · {{ fileSize }} · {{ formatDuration(duration) }}</p>
      <p v-if="tooLarge" class="media-capture-error" role="alert">This video exceeds the {{ maxMegabytes }} MB upload limit. Choose a shorter video.</p>
      <div class="media-capture-actions"><button type="button" class="secondary-button" @click="retake">Retake</button><button type="button" class="secondary-button" @click="cancel">Cancel</button><button type="button" class="primary" :disabled="tooLarge" @click="useVideo">Use video</button></div>
    </template>
  </section>
</template>
