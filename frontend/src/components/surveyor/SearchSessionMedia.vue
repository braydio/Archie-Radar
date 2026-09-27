<script setup>
import { ref, watch } from 'vue'
import MediaCaptureSheet from './MediaCaptureSheet.vue'
import MediaGallery from '../media/MediaGallery.vue'
import { uploadMedia } from '../../surveyor/mediaCapture.js'
const props = defineProps({ api: { type: String, required: true }, sessionId: { type: Number, required: true } })
const emit = defineEmits(['close'])
const attachments = ref([])
const caption = ref('')
const uploading = ref(false)
const error = ref('')
const captureOpen = ref(false)
async function load() {
  try { const response = await fetch(`${props.api}/api/surveyor/sessions/${props.sessionId}/attachments`); if (!response.ok) throw new Error(); attachments.value = await response.json() }
  catch { attachments.value = []; error.value = 'Session media could not be loaded.' }
}
async function upload(file) {
  if (!file) return
  uploading.value = true; error.value = ''
  try {
    const result = await uploadMedia(props.api, { searchSessionId: props.sessionId }, file, { caption: caption.value })
    attachments.value.unshift(result); caption.value = ''
  } catch (cause) { error.value = cause.message }
  finally { uploading.value = false }
}
async function remove(item) {
  try { const response = await fetch(`${props.api}/api/surveyor/attachments/${item.id}`, { method: 'DELETE' }); if (!response.ok) throw new Error('Could not delete attachment'); attachments.value = attachments.value.filter(row => row.id !== item.id) }
  catch (cause) { error.value = cause.message }
}
watch(() => props.sessionId, load, { immediate: true })
</script>
<template>
  <form class="field-sheet session-media-sheet" @submit.prevent>
    <header><div><p class="eyebrow">ACTIVE SEARCH · SESSION MEDIA</p><h2>Field media</h2></div><button type="button" aria-label="Close" @click="emit('close')">×</button></header>
    <label>Caption for next attachment<input v-model="caption" maxlength="500" /></label>
    <button type="button" class="secondary-button" :disabled="uploading" @click="captureOpen=!captureOpen">{{ uploading ? 'Uploading…' : '＋ Media' }}</button>
    <MediaCaptureSheet v-if="captureOpen" :api="api" @select="upload($event); captureOpen=false" @cancel="captureOpen=false" @error="error=$event" />
    <p v-if="error" class="media-capture-error" role="status">{{ error }}</p>
    <MediaGallery :items="attachments" :api="api" title="Session media" @delete="remove" />
  </form>
</template>
