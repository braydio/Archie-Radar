<script setup>
import { PIN_GROUPS, OBJECT_TYPES } from '../../surveyor/objectTypes.js'

defineEmits(['select', 'close'])
</script>

<template>
  <div class="marker-picker-backdrop" @click.self="$emit('close')">
    <section class="marker-type-picker" aria-label="Choose marker type">
      <header><div><p class="eyebrow">NEW MARKER</p><h2>What are you marking?</h2></div><button type="button" aria-label="Close marker picker" @click="$emit('close')">×</button></header>
      <section v-for="group in PIN_GROUPS" :key="group.key"><h3>{{ group.label }}</h3><div class="marker-type-grid"><button v-for="type in group.types" :key="type" type="button" @click="$emit('select', type)"><i :style="{ backgroundColor: OBJECT_TYPES[type].color }">{{ OBJECT_TYPES[type].icon.slice(0, 1).toUpperCase() }}</i>{{ OBJECT_TYPES[type].label }}</button></div></section>
      <button class="secondary-button marker-picker-cancel" type="button" @click="$emit('close')">Cancel</button>
    </section>
  </div>
</template>
