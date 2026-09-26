<script setup>
import { onBeforeUnmount, ref } from 'vue'
const emit = defineEmits(['select'])
const secureContext = typeof window !== 'undefined' && window.isSecureContext === true
const cameraInput = ref(null)
const fileInput = ref(null)
const previewUrl = ref('')
const selected = ref(null)
function choose(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  selected.value = file
  previewUrl.value = URL.createObjectURL(file)
  emit('select', file)
  event.target.value = ''
}
function clear() { selected.value = null; if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
onBeforeUnmount(clear)
</script>
<template>
  <div class="photo-capture">
    <div class="media-capture-actions">
      <button type="button" class="secondary-button" :disabled="!secureContext" :title="!secureContext ? 'Photo capture requires HTTPS or localhost' : ''" @click="cameraInput?.click()">Take photo</button>
      <button type="button" class="secondary-button" @click="fileInput?.click()">Choose photo</button>
    </div>
    <p v-if="!secureContext" class="media-capture-error" role="status">Camera capture requires HTTPS (or localhost). You can still choose an existing photo.</p>
    <input ref="cameraInput" class="visually-hidden" type="file" accept="image/*" capture="environment" @change="choose" />
    <input ref="fileInput" class="visually-hidden" type="file" accept="image/*" @change="choose" />
    <div v-if="selected" class="media-preview"><img :src="previewUrl" :alt="selected.name || 'Captured evidence photo'" /><span>{{ selected.name || 'Captured photo' }}</span><button type="button" aria-label="Remove selected photo" @click="clear">×</button></div>
  </div>
</template>
