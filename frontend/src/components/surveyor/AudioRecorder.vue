<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { mediaCaptureError, supportedAudioMimeType, stopMediaTracks } from '../../surveyor/mediaCapture.js'
const emit = defineEmits(['select', 'error'])
const state = ref('idle')
const error = ref('')
const elapsed = ref(0)
const previewUrl = ref('')
const blob = ref(null)
let stream = null
let recorder = null
let chunks = []
let interval = null
let cancelRequested = false
let disposed = false
const elapsedLabel = computed(() => `${Math.floor(elapsed.value / 60)}:${String(elapsed.value % 60).padStart(2, '0')}`)
const secureContext = typeof window !== 'undefined' && window.isSecureContext === true
const captureAvailable = secureContext && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined'
function stopTracks() { stopMediaTracks(stream); stream = null }
function clearTimer() { if (interval) clearInterval(interval); interval = null }
function clearPreview() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = ''; blob.value = null }
async function start() {
  error.value = ''
  if (!window.isSecureContext) { error.value = mediaCaptureError(); emit('error', error.value); return }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { error.value = 'Audio recording is not supported in this browser.'; emit('error', error.value); return }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    if (disposed) { stopTracks(); return }
    const mimeType = supportedAudioMimeType()
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    chunks = []
    recorder.ondataavailable = event => { if (event.data?.size) chunks.push(event.data) }
    recorder.onerror = event => { error.value = mediaCaptureError(event.error); emit('error', error.value); stopTracks(); clearTimer(); state.value = 'idle' }
    recorder.onstop = () => {
      stopTracks()
      clearTimer()
      if (cancelRequested) { cancelRequested = false; chunks = []; state.value = 'idle'; return }
      blob.value = new Blob(chunks, { type: recorder?.mimeType || mimeType || 'application/octet-stream' })
      if (!blob.value.size) { state.value = 'idle'; return }
      if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
      previewUrl.value = URL.createObjectURL(blob.value)
      state.value = 'preview'
    }
    elapsed.value = 0
    state.value = 'recording'
    interval = setInterval(() => elapsed.value += 1, 1000)
    recorder.start()
  } catch (cause) { stopTracks(); clearTimer(); state.value = 'idle'; error.value = mediaCaptureError(cause); emit('error', error.value) }
}
function stop() { if (recorder?.state === 'recording') recorder.stop(); else { stopTracks(); clearTimer(); state.value = 'idle' } }
function retake() { clearPreview(); state.value = 'idle'; elapsed.value = 0; chunks = [] }
function cancel() { cancelRequested = true; stopTracks(); if (recorder?.state === 'recording') recorder.stop(); clearTimer(); clearPreview(); state.value = 'idle'; elapsed.value = 0; chunks = [] }
function save() {
  if (!blob.value) return
  const extension = blob.value.type.includes('mp4') ? 'm4a' : blob.value.type.includes('ogg') ? 'ogg' : 'webm'
  emit('select', new File([blob.value], `field-recording-${new Date().toISOString().replaceAll(':', '-')}.${extension}`, { type: blob.value.type }))
}
onBeforeUnmount(() => { disposed = true; cancel(); clearPreview() })
</script>
<template>
  <section class="audio-recorder" aria-label="Audio evidence recorder">
    <div v-if="state === 'idle'"><button type="button" class="secondary-button" :disabled="!captureAvailable" @click="start">Record audio</button><p v-if="!captureAvailable" class="media-capture-error" role="status">{{ secureContext ? 'Audio recording is unavailable in this browser.' : 'Audio recording requires HTTPS (or localhost).' }} You can still attach a file.</p></div>
    <div v-else-if="state === 'recording'" class="recording-state"><span class="recording-dot"></span><strong>Recording · {{ elapsedLabel }}</strong><button type="button" class="secondary-button" @click="stop">Stop</button><button type="button" class="secondary-button" @click="cancel">Cancel</button></div>
    <div v-else-if="state === 'preview'" class="audio-preview"><audio :src="previewUrl" controls></audio><span>Recording · {{ elapsedLabel }} · {{ blob ? `${(blob.size / 1024).toFixed(0)} KB` : '' }}</span><div class="media-capture-actions"><button type="button" class="secondary-button" @click="retake">Retake</button><button type="button" class="secondary-button" @click="cancel">Cancel</button><button type="button" class="primary" @click="save">Save recording</button></div></div>
    <p v-if="error" class="media-capture-error" role="status">{{ error }}</p>
  </section>
</template>
