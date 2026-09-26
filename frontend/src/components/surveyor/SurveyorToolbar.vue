<script setup>
defineProps({ activeTool: { type: String, required: true } })
const emit = defineEmits(['tool', 'more'])
const desktopTools = [['select', '↖', 'Select'], ['pin', '⌖', 'Pin'], ['camera', '◉', 'Camera'], ['zone', '▱', 'Zone'], ['line', '⌁', 'Line'], ['link', '⟷', 'Link'], ['note', '✎', 'Note'], ['access', '⌂', 'Access']]
</script>
<template>
  <aside class="surveyor-tools"><p>TOOLS</p><button v-for="[tool, icon, label] in desktopTools" :key="tool" :class="{ active: activeTool === tool }" @click="emit('tool', tool)">{{ icon }}<span>{{ label }}</span></button></aside>
  <div class="mobile-field-bar"><button v-for="tool in [['pin','Pin'],['camera','Camera'],['zone','Zone'],['note','Note']]" :key="tool[0]" @click="emit('tool', tool[0])">{{ tool[1] }}</button><button @click="emit('more')">More</button></div>
</template>
