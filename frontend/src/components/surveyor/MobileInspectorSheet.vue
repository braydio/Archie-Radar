<script setup>
import { ref } from 'vue'
defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['close'])
const collapsed = ref(false)
let startY = 0
function pointerDown(event) { startY = event.clientY; event.currentTarget.setPointerCapture(event.pointerId) }
function pointerUp(event) { const delta = event.clientY - startY; if (delta > 45) collapsed.value = true; else if (delta < -35) collapsed.value = false }
</script>
<template>
  <section v-if="open" class="mobile-inspector-sheet" :class="{ collapsed }">
    <div class="sheet-grab" @pointerdown="pointerDown" @pointerup="pointerUp"><span></span><button aria-label="Close details" @click.stop="emit('close')">×</button></div>
    <div v-show="!collapsed" class="mobile-inspector-content"><slot /></div>
  </section>
</template>
