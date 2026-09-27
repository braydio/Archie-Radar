<script setup>
import { onMounted, ref } from 'vue'
import PhotoCapture from './PhotoCapture.vue'
import VideoCapture from './VideoCapture.vue'
import AudioRecorder from './AudioRecorder.vue'

const props = defineProps({ api: { type: String, default: '' }, maxVideoMegabytes: { type: Number, default: 500 } })
const emit = defineEmits(['select', 'cancel', 'error'])
const mode = ref('menu')
const existingInput = ref(null)
const fileInput = ref(null)
const videoLimit = ref(props.maxVideoMegabytes)
onMounted(async () => {
  if (!props.api) return
  try { const response = await fetch(`${props.api}/api/surveyor/media/config`); if (response.ok) videoLimit.value = (await response.json()).max_video_mb || videoLimit.value }
  catch { /* Use the configured frontend fallback if the settings endpoint is unavailable. */ }
})
function selected(file) { mode.value = 'menu'; if (file) emit('select', file) }
function cancel() { mode.value = 'menu'; emit('cancel') }
function chooseFile(event) { const file = event.target.files?.[0]; event.target.value = ''; if (file) selected(file) }
</script>

<template>
  <section class="media-capture-sheet" aria-label="Add field media">
    <header><div><p class="eyebrow">FIELD EVIDENCE</p><h3>＋ Media</h3></div><button type="button" aria-label="Close media capture" @click="emit('cancel')">×</button></header>
    <template v-if="mode === 'menu'">
      <div class="media-capture-choice-grid"><button type="button" @click="mode='photo'">📷<span>Photo</span></button><button type="button" @click="mode='video'">▣<span>Video</span></button><button type="button" @click="mode='audio'">♫<span>Audio</span></button></div>
      <div class="media-capture-actions media-secondary-choices"><button type="button" class="secondary-button" @click="existingInput?.click()">Choose existing media</button><button type="button" class="secondary-button" @click="fileInput?.click()">Add file</button></div>
      <input ref="existingInput" class="visually-hidden" type="file" accept="image/*,video/*,audio/*" @change="chooseFile" />
      <input ref="fileInput" class="visually-hidden" type="file" accept="image/*,video/*,audio/*,application/pdf,text/plain" @change="chooseFile" />
    </template>
    <PhotoCapture v-else-if="mode === 'photo'" @select="selected" @cancel="cancel" />
    <VideoCapture v-else-if="mode === 'video'" :max-megabytes="videoLimit" @select="selected" @cancel="cancel" />
    <AudioRecorder v-else @select="selected" @error="emit('error', $event)" />
    <button v-if="mode !== 'menu'" type="button" class="secondary-button media-back-button" @click="mode='menu'">Back to media</button>
  </section>
</template>
