<script setup>
import { RouterLink, RouterView, useRouter } from 'vue-router'
import AssistantLocationTool from './components/assistant/AssistantLocationTool.vue'
import { setLocationFocus } from './surveyor/locationFocus.js'

const router = useRouter()
function openInSurveyor(match) {
  setLocationFocus(match)
  router.push('/surveyor').then(() => window.dispatchEvent(new Event('archie:location-focus')))
}
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
      <AssistantLocationTool @open-surveyor="openInSurveyor" />
    </header>
    <RouterView />
  </div>
</template>
