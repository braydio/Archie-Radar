import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/CandidatesView.vue') },
    { path: '/surveyor', component: () => import('./views/SurveyorView.vue') },
    { path: '/journal', component: () => import('./views/JournalView.vue') }
  ]
})

export default router
