<script setup>
const props = defineProps({ coordinates: { type: Array, required: true }, position: { type: Object, required: true } })
const emit = defineEmits(['select', 'close'])
const choices = [
  ['sighting', 'Sighting'], ['possible_sighting', 'Possible sighting'], ['camera', 'Camera'],
  ['evidence', 'Evidence'], ['dog_lives_here', 'Dog'], ['outdoor_cat', 'Outdoor cat'],
  ['food_station', 'Food station'], ['access', 'Access'], ['note', 'Note'], ['other', 'Other']
]
</script>

<template>
  <div class="quick-add-backdrop" @pointerdown.self="emit('close')" @contextmenu.prevent>
    <section class="quick-add-menu" :style="{ left: `${position.x}px`, top: `${position.y}px` }" aria-label="Add field observation">
      <header><strong>Add here</strong><button type="button" aria-label="Close" @click="emit('close')">×</button></header>
      <button v-for="[kind, label] in choices" :key="kind" type="button" @click="emit('select', kind, coordinates)">{{ label }}</button>
    </section>
  </div>
</template>
