<script setup>
defineProps({ activeTool: { type: String, required: true }, canUndo: Boolean, canRedo: Boolean })
const emit = defineEmits(['tool', 'more', 'undo', 'redo'])
const desktopTools = [['select', '↖', 'Select'], ['pin', '⌖', 'Marker'], ['camera', '◉', 'Camera'], ['zone', '▱', 'Zone'], ['line', '⌁', 'Line'], ['link', '⟷', 'Link'], ['note', '✎', 'Note'], ['access', '⌂', 'Access']]
</script>
<template>
  <aside class="surveyor-tools"><p>TOOLS</p><button v-for="[tool, icon, label] in desktopTools" :key="tool" :class="{ active: activeTool === tool }" @click="emit('tool', tool)">{{ icon }}<span>{{ label }}</span></button><div class="toolbar-history"><button :disabled="!canUndo" title="Undo · Ctrl/Cmd+Z" @click="emit('undo')">↶<span>Undo</span></button><button :disabled="!canRedo" title="Redo · Ctrl/Cmd+Shift+Z" @click="emit('redo')">↷<span>Redo</span></button></div></aside>
  <div class="mobile-field-bar"><button v-for="tool in [['pin','Marker'],['camera','Camera'],['zone','Zone'],['note','Note']]" :key="tool[0]" @click="emit('tool', tool[0])">{{ tool[1] }}</button><button @click="emit('more')">More</button></div>
</template>
