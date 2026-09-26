<script setup>
import { ref, watch } from 'vue'
import PhotoCapture from './PhotoCapture.vue'
import AudioRecorder from './AudioRecorder.vue'
import { uploadMedia } from '../../surveyor/mediaCapture.js'
const props = defineProps({ api: { type: String, required: true }, sessionId: { type: Number, required: true } })
const emit = defineEmits(['close'])
const attachments = ref([])
const caption = ref('')
const uploading = ref(false)
const error = ref('')
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
    <PhotoCapture @select="upload" /><AudioRecorder @select="upload" @error="error=$event" />
    <label class="attachment-upload">{{ uploading ? 'Uploading…' : 'Add file' }}<input type="file" accept="audio/*,image/*,application/pdf,text/plain" :disabled="uploading" @change="upload($event.target.files?.[0]); $event.target.value=''" /></label>
    <p v-if="error" class="media-capture-error" role="status">{{ error }}</p>
    <section class="attachment-list"><h3>Session attachments · {{ attachments.length }}</h3><article v-for="item in attachments" :key="item.id" class="evidence-attachment"><img v-if="item.attachment_type==='image'" :src="`${api}${item.media_url}`" :alt="item.caption || 'Search evidence photo'"/><audio v-else-if="item.attachment_type==='audio'" :src="`${api}${item.media_url}`" controls preload="none"></audio><a v-else :href="`${api}${item.media_url}`" target="_blank" rel="noreferrer">Open attachment</a><p>{{ item.caption || item.source }}</p><small>{{ item.observed_at ? new Date(item.observed_at).toLocaleString() : new Date(item.created_at).toLocaleString() }}</small><button type="button" class="danger-button" @click="remove(item)">Delete</button></article></section>
  </form>
</template>
