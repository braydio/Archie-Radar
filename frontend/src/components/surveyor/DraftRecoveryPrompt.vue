<script setup>
defineProps({ draft: { type: Object, required: true } })
const emit = defineEmits(['restore', 'discard'])
</script>

<template>
  <section class="draft-recovery-prompt" role="dialog" aria-modal="true" aria-label="Restore unsaved field entry">
    <p class="eyebrow">UNSAVED FIELD ENTRY</p><h2>Restore unsaved field entry?</h2>
    <p>{{ draft.kind.replaceAll('_', ' ') }} · saved {{ new Date(draft.saved_at).toLocaleString() }}</p>
    <footer><button type="button" class="secondary-button" @click="emit('discard')">Discard</button><button type="button" class="primary" @click="emit('restore')">Restore</button></footer>
  </section>
</template>
