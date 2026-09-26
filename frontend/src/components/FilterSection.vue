<script>
export default {
  name: 'FilterSection',
  props: {
    title: { type: String, required: true },
    open: { type: Boolean, default: false },
    summary: { type: String, default: '' },
    badgeCount: { type: Number, default: 0 }
  },
  emits: ['toggle']
}
</script>

<template>
  <section class="filter-section collapsible-filter">
    <button class="filter-section-summary" type="button" :aria-expanded="open" @click="$emit('toggle')">
      <span class="filter-section-heading">
        <strong>{{ title }}</strong>
        <small v-if="summary">{{ summary }}</small>
      </span>
      <span class="section-end">
        <b v-if="badgeCount">{{ badgeCount }}</b>
        <span aria-hidden="true">{{ open ? '▴' : '▾' }}</span>
      </span>
    </button>
    <div v-show="open" class="filter-section-body"><slot /></div>
  </section>
</template>
