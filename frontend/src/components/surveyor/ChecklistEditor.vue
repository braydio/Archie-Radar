<script setup>
import { computed, ref, watch } from 'vue'
const props = defineProps({ object: { type: Object, required: true } })
const emit = defineEmits(['save', 'followup'])
const rows = ref([])
const draft = ref('')
const dirty = ref(false)
watch(() => [props.object.id, props.object.properties?.checklist], () => {
  rows.value = (props.object.properties?.checklist || []).map(item => ({ ...item }))
  dirty.value = false
}, { immediate: true, deep: true })
const incomplete = computed(() => rows.value.filter(item => !item.done))
function add() {
  const text = draft.value.trim()
  if (!text) return
  rows.value.push({ id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`, text, done: false })
  draft.value = ''; dirty.value = true
}
function toggle(item) { item.done = !item.done; dirty.value = true }
function save() { emit('save', { ...props.object.properties, checklist: rows.value }); dirty.value = false }
</script>
<template>
  <section class="checklist-editor">
    <div class="inspector-section-heading"><h3>Checklist</h3><button v-if="dirty" type="button" class="secondary-button" @click="save">Save list</button></div>
    <div v-for="item in rows" :key="item.id" class="checklist-row"><label><input type="checkbox" :checked="item.done" @change="toggle(item)"/><span :class="{ done: item.done }">{{ item.text }}</span></label><button v-if="!item.done" type="button" class="text-button" @click="emit('followup', item)">→ Follow-up</button></div>
    <form class="checklist-add" @submit.prevent="add"><input v-model="draft" maxlength="240" placeholder="Add checklist item"/><button type="submit" class="secondary-button">Add</button></form>
    <p v-if="!rows.length" class="inspector-meta">No checklist items.</p>
  </section>
</template>
