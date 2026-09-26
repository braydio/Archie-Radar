<script setup>
import { onBeforeUnmount, ref } from 'vue'

const emit = defineEmits(['select', 'cancel'])
const cameraInput = ref(null)
const fileInput = ref(null)
const previewUrl = ref('')
const selected = ref(null)

function releasePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}
function choose(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  releasePreview()
  selected.value = file
  previewUrl.value = URL.createObjectURL(file)
}
function retake() {
  selected.value = null
  releasePreview()
  cameraInput.value?.click()
}
function cancel() {
  selected.value = null
  releasePreview()
  emit('cancel')
}
function usePhoto() {
  if (!selected.value) return
  emit('select', selected.value)
  selected.value = null
  releasePreview()
}
onBeforeUnmount(releasePreview)
</script>

<template>
  <div class="photo-capture">
    <template v-if="!selected">
      <div class="media-capture-actions">
        <button type="button" class="secondary-button" @click="cameraInput?.click()">Take photo</button>
        <button type="button" class="secondary-button" @click="fileInput?.click()">Choose photo</button>
      </div>
      <input ref="cameraInput" class="visually-hidden" type="file" accept="image/*" capture="environment" @change="choose" />
      <input ref="fileInput" class="visually-hidden" type="file" accept="image/*" @change="choose" />
    </template>
    <template v-else>
      <div class="media-preview photo-preview-draft"><img :src="previewUrl" :alt="selected.name || 'Captured evidence photo'" /><span>{{ selected.name || 'Captured photo' }}</span></div>
      <div class="media-capture-actions"><button type="button" class="secondary-button" @click="retake">Retake</button><button type="button" class="secondary-button" @click="cancel">Cancel</button><button type="button" class="primary" @click="usePhoto">Use photo</button></div>
    </template>
  </div>
</template>
