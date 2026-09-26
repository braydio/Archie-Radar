<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="archie-shell">
    <header class="archie-nav">
      <RouterLink class="archie-brand" to="/">ARCHIE RADAR</RouterLink>
      <nav aria-label="Main navigation">
        <RouterLink to="/">Candidates</RouterLink>
        <RouterLink to="/surveyor">Surveyor</RouterLink>
        <RouterLink to="/journal">Journal</RouterLink>
      </nav>
    </header>
    <RouterView />
  </div>
</template>
