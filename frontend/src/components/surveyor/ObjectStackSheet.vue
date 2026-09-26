<script setup>
defineProps({ objects: { type: Array, required: true } })
const emit = defineEmits(['select', 'close'])
</script>

<template>
  <section class="object-stack-sheet" role="dialog" aria-label="Choose map object">
    <header><strong>{{ objects.length }} things here</strong><button type="button" aria-label="Close" @click="emit('close')">×</button></header>
    <button v-for="item in objects" :key="item.id" type="button" class="object-stack-row" @click="emit('select', item.id)">
      <span class="object-stack-type">{{ item.object_type.replaceAll('_', ' ') }}</span><strong>{{ item.name || item.subtype || 'Field object' }}</strong><small>{{ item.occurred_at ? new Date(item.occurred_at).toLocaleString() : item.status || '' }}</small>
    </button>
  </section>
</template>
