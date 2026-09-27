import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/CandidatesView.vue') },
    { path: '/candidates/:caseId', component: () => import('./views/CandidateCaseView.vue') },
    { path: '/surveyor', component: () => import('./views/SurveyorView.vue') },
    { path: '/journal', component: () => import('./views/JournalView.vue') },
    { path: '/media', component: () => import('./views/MediaVaultView.vue') }
  ]
})

export default router
