<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  api: { type: String, required: true },
  open: Boolean,
  plan: { type: Object, default: null },
  method: { type: String, default: 'walking' },
  activeSession: { type: Object, default: null },
  inspectorOpen: Boolean,
})
const emit = defineEmits(['update:open', 'update:plan', 'start', 'focus', 'error'])
const plan = ref(props.plan)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const hasLastPlan = ref(false)
const lastPlan = ref(null)
const remainingOnly = ref(true)
const newTitles = ref({ prep: '', packing: '', gameplan: '' })
const dependencyItemId = ref(null)
const newPrepTitle = ref('')

watch(() => props.plan, value => { plan.value = value })
watch(() => props.open, async value => {
  if (value) await loadCurrent()
})

const sections = [
  { id: 'prep', title: 'Prep / Setup', done: 'ready', empty: 'What needs to be ready before you leave?' },
  { id: 'packing', title: 'Packing List', done: 'packed', empty: 'What do you need to bring?' },
  { id: 'gameplan', title: 'Gameplan', done: 'done', empty: 'What are you going to do out there?' },
]
const items = computed(() => plan.value?.items || [])
const readiness = computed(() => plan.value?.readiness || { ready_to_leave: false, prep_remaining: 0, packing_remaining: 0, packed_items: 0, gameplan_total: 0, gameplan_remaining: 0, skipped_required: 0, waived_dependency_count: 0 })
const nextItems = computed(() => items.value.filter(item => item.section === 'gameplan' && item.status === 'pending'))
const activeNext = computed(() => nextItems.value[0] || null)
const activeNextFocusable = computed(() => Boolean(activeNext.value?.linked_context?.focusable))
const gameplanIndex = computed(() => {
  if (!activeNext.value) return 0
  const stops = items.value.filter(item => item.section === 'gameplan')
  return stops.findIndex(item => item.id === activeNext.value.id) + 1
})
const hasPendingBlockers = computed(() => readiness.value.prep_remaining + readiness.value.packing_remaining > 0)

function emitPlan(value = plan.value) {
  plan.value = value
  emit('update:plan', value)
}
async function request(path, options = {}) {
  const response = await fetch(`${props.api}/api/surveyor/outings${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  })
  if (!response.ok) {
    let message = 'Could not save outing plan'
    try { message = (await response.json()).detail || message } catch {}
    throw new Error(message)
  }
  return response.status === 204 ? null : response.json()
}
async function loadCurrent() {
  loading.value = true; error.value = ''
  try {
    const current = await request('/current')
    emitPlan(current)
    if (!current) { lastPlan.value = await request('/last'); hasLastPlan.value = Boolean(lastPlan.value) }
  }
  catch (cause) { error.value = cause.message; emit('error', cause.message) }
  finally { loading.value = false }
}
async function buildPlan() {
  loading.value = true; error.value = ''
  try {
    emitPlan(await request('', { method: 'POST', body: JSON.stringify({ title: "Tonight's plan", method: props.method }) }))
    remainingOnly.value = false
  } catch (cause) { error.value = cause.message; emit('error', cause.message) }
  finally { loading.value = false }
}
async function reuseLast() {
  loading.value = true; error.value = ''
  try { emitPlan(await request('/reuse-last', { method: 'POST' })); hasLastPlan.value = true; remainingOnly.value = false }
  catch (cause) { error.value = cause.message; emit('error', cause.message) }
  finally { loading.value = false }
}
async function continueUnfinished() {
  if (!lastPlan.value?.id) return
  loading.value = true; error.value = ''
  try { emitPlan(await request(`/${lastPlan.value.id}/continue-unfinished`, { method: 'POST' })); remainingOnly.value = false }
  catch (cause) { error.value = cause.message; emit('error', cause.message) }
  finally { loading.value = false }
}
async function patchPlan(changes) {
  if (!plan.value) return
  saving.value = true
  try { emitPlan(await request(`/${plan.value.id}`, { method: 'PATCH', body: JSON.stringify(changes) })) }
  catch (cause) { error.value = cause.message; emit('error', cause.message); await loadCurrent() }
  finally { saving.value = false }
}
function savePlanTitle(event) { patchPlan({ title: event.target.value.trim() || "Tonight's plan" }) }
async function addItem(values) {
  if (!plan.value) await buildPlan()
  if (!plan.value) return null
  const result = await request(`/${plan.value.id}/items`, { method: 'POST', body: JSON.stringify(values) })
  emitPlan(result)
  return result.items.find(item => item.section === values.section && item.title === values.title && item.position === Math.max(...result.items.filter(row => row.section === values.section).map(row => row.position))) || result.items.at(-1)
}
async function addFromInput(section) {
  const title = newTitles.value[section].trim()
  if (!title) return
  try { await addItem({ section, title }); newTitles.value[section] = '' }
  catch (cause) { error.value = cause.message; emit('error', cause.message) }
}
async function patchItem(item, changes) {
  if (!plan.value) return
  const previous = { ...item }
  Object.assign(item, changes)
  emitPlan({ ...plan.value, items: [...plan.value.items] })
  try {
    emitPlan(await request(`/items/${item.id}`, { method: 'PATCH', body: JSON.stringify(changes) }))
  } catch (cause) {
    Object.assign(item, previous); emitPlan({ ...plan.value, items: [...plan.value.items] })
    error.value = cause.message; emit('error', cause.message)
  }
}
async function removeItem(item) {
  try { emitPlan(await request(`/items/${item.id}`, { method: 'DELETE' })) }
  catch (cause) { error.value = cause.message; emit('error', cause.message) }
}
async function toggleDependency(item, prepId) {
  const ids = new Set(item.depends_on_prep_ids || [])
  if (ids.has(prepId)) ids.delete(prepId); else ids.add(prepId)
  try { emitPlan(await request(`/items/${item.id}/dependencies`, { method: 'PUT', body: JSON.stringify({ prep_item_ids: [...ids] }) })) }
  catch (cause) { error.value = cause.message; emit('error', cause.message) }
}
async function addAndLinkPrep() {
  const title = newPrepTitle.value.trim()
  if (!title || !dependencyItemId.value) return
  try {
    emitPlan(await request(`/items/${dependencyItemId.value}/create-prep-dependency`, { method: 'POST', body: JSON.stringify({ title }) }))
    newPrepTitle.value = ''
  } catch (cause) { error.value = cause.message; emit('error', cause.message) }
}
async function reorder(item, direction) {
  const group = plan.value.items.filter(row => row.section === item.section).sort((a, b) => a.position - b.position)
  const index = group.findIndex(row => row.id === item.id)
  const target = index + direction
  if (target < 0 || target >= group.length) return
  const reordered = [...group]
  const [moving] = reordered.splice(index, 1)
  reordered.splice(target, 0, moving)
  try {
    emitPlan(await request(`/${plan.value.id}/reorder`, { method: 'POST', body: JSON.stringify({ section: item.section, ordered_item_ids: reordered.map(row => row.id) }) }))
  } catch (cause) { error.value = cause.message; emit('error', cause.message) }
}
function sectionItems(section) {
  return [...items.value].filter(item => item.section === section && (!remainingOnly.value || item.status !== 'completed'))
    .sort((a, b) => a.position - b.position || a.id - b.id)
}
function sectionCount(section) {
  return items.value.filter(item => item.section === section && item.status === 'completed').length
}
function sectionTotal(section) { return items.value.filter(item => item.section === section).length }
function dependencies(item) { return items.value.filter(row => item.depends_on_prep_ids?.includes(row.id)) }
function unmetDependencies(item) { return dependencies(item).filter(row => row.status === 'pending') }
function usedByCount(prep) { return items.value.filter(row => row.depends_on_prep_ids?.includes(prep.id)).length }
function dependencySummary(item) {
  const deps = dependencies(item)
  const pending = deps.filter(row => row.status === 'pending')
  const skipped = deps.filter(row => row.status === 'skipped')
  if (pending.length) return `Needs setup: ${pending.map(row => row.title).join(', ')}`
  if (skipped.length) return `Setup skipped: ${skipped.map(row => row.title).join(', ')}`
  return deps.length ? 'Setup ready' : ''
}
function dismiss() { emit('update:open', false); dependencyItemId.value = null }
function start(anyway = false) {
  emit('start', { plan: plan.value, method: props.method, anyway })
}

defineExpose({ addItem, refresh: loadCurrent })
</script>

<template>
  <div v-if="activeSession && plan" class="outing-mission-strip" :class="{ 'inspector-open': inspectorOpen }">
    <template v-if="activeNext">
      <div class="mission-copy"><span class="eyebrow">NEXT · {{ gameplanIndex }} / {{ items.filter(item => item.section === 'gameplan').length }}</span><strong>{{ activeNext.title }}</strong><span v-if="activeNext.note">{{ activeNext.note }}</span><small v-if="dependencySummary(activeNext)" :class="{ 'mission-needs-setup': unmetDependencies(activeNext).length }">{{ unmetDependencies(activeNext).length ? '⚠ ' : '✓ ' }}{{ dependencySummary(activeNext) }}</small></div>
      <div class="mission-actions"><button v-if="activeNextFocusable" type="button" @click="emit('focus', activeNext)">Map</button><button type="button" @click="patchItem(activeNext, { status: 'completed' })">{{ activeNext.surveyor_task_id ? 'Done · completes follow-up' : 'Done' }}</button><button type="button" @click="patchItem(activeNext, { status: 'skipped' })">Skip</button><button type="button" aria-label="Open outing plan" @click="emit('update:open', true)">Plan</button></div>
    </template>
    <template v-else><div class="mission-copy"><span class="eyebrow">OUTING PLAN</span><strong>Gameplan complete</strong></div><button type="button" @click="emit('update:open', true)">Review plan</button></template>
  </div>

  <div v-if="open" class="field-sheet-backdrop outing-backdrop" @click.self="dismiss">
    <section class="field-sheet outing-preflight" role="dialog" aria-modal="true" aria-labelledby="outing-title">
      <header class="outing-heading"><div><p class="eyebrow">PRE-FLIGHT · {{ plan?.title || "TONIGHT'S PLAN" }}</p><h2 id="outing-title">{{ plan ? 'Before you head out' : "Tonight's plan" }}</h2></div><button type="button" aria-label="Close preflight" @click="dismiss">×</button></header>
      <p v-if="loading" class="inspector-meta">Loading outing plan…</p>
      <template v-else-if="!plan">
        <p class="outing-intro">Build a quick launch list, reuse your last outing, or head straight into a search.</p>
        <p v-if="lastPlan?.readiness?.gameplan_remaining" class="outing-continue-hint">{{ lastPlan.readiness.gameplan_remaining }} unfinished from last outing · <button type="button" class="text-button" @click="continueUnfinished">Continue</button></p>
        <div class="outing-start-choices"><button type="button" class="primary" @click="buildPlan">Build plan</button><button v-if="hasLastPlan" type="button" class="secondary-button" @click="reuseLast">Reuse last outing</button><button type="button" class="text-button" @click="start(true)">Start without a plan</button></div>
      </template>
      <template v-else>
        <div class="outing-summary" :class="{ ready: !hasPendingBlockers }"><strong>{{ hasPendingBlockers ? `${readiness.prep_remaining + readiness.packing_remaining} things left before you're ready` : 'READY TO GO' }}</strong><span v-if="!hasPendingBlockers">{{ readiness.packed_items }} packed · {{ readiness.gameplan_total }} stops<template v-if="readiness.skipped_required"> · {{ readiness.skipped_required }} setup item{{ readiness.skipped_required === 1 ? '' : 's' }} skipped</template></span><span v-else>{{ readiness.prep_remaining }} setup blocker{{ readiness.prep_remaining === 1 ? '' : 's' }} · {{ readiness.packing_remaining }} unpacked item{{ readiness.packing_remaining === 1 ? '' : 's' }}</span></div>
        <label class="outing-objective-label">PLAN TITLE<input :value="plan.title" maxlength="180" @blur="savePlanTitle" /></label>
        <label class="outing-objective-label">THE PLAN<input :value="plan.objective" placeholder="What is tonight about? (optional)" maxlength="500" @blur="patchPlan({ objective: $event.target.value })" /></label>
        <div class="outing-view-switch"><span>{{ saving ? 'Saving…' : 'Saved automatically' }}</span><div><button type="button" :aria-pressed="!remainingOnly" @click="remainingOnly=false">All</button><button type="button" :aria-pressed="remainingOnly" @click="remainingOnly=true">Remaining</button></div></div>
        <section v-for="section in sections" :key="section.id" class="outing-section">
          <details :open="sectionItems(section.id).some(item => item.status === 'pending') || sectionTotal(section.id) === 0">
            <summary><span>{{ section.title }}</span><small>· {{ sectionCount(section.id) }}/{{ sectionTotal(section.id) }} {{ section.done }}</small></summary>
            <div class="outing-items">
              <article v-for="(item, index) in sectionItems(section.id)" :key="item.id" class="outing-item" :class="[`item-${item.status}`, { 'item-needs-setup': unmetDependencies(item).length }]">
                <label class="outing-check"><input type="checkbox" :checked="item.status === 'completed'" :aria-label="`${item.status === 'skipped' ? 'Skipped' : item.status === 'completed' ? 'Completed' : 'Pending'}: ${item.title}`" @change="patchItem(item, { status: $event.target.checked ? 'completed' : 'pending' })" /><span></span></label>
                <div class="outing-item-body"><input class="outing-item-title" :value="item.title" :aria-label="`Edit ${section.title} item`" maxlength="240" @blur="patchItem(item, { title: $event.target.value.trim() || item.title })" /><small v-if="item.status === 'skipped'" class="outing-skipped-label">Skipped</small><small v-if="item.section === 'prep' && usedByCount(item)">Used by {{ usedByCount(item) }} item{{ usedByCount(item) === 1 ? '' : 's' }}</small><small v-if="item.linked_context" class="outing-linked">{{ item.linked_context.label }}</small><small v-else-if="item.map_object_id || item.surveyor_task_id || item.candidate_case_id" class="outing-linked">Location unavailable</small><small v-if="section.id !== 'prep' && dependencySummary(item)" :class="{ 'mission-needs-setup': unmetDependencies(item).length, 'mission-ready': !unmetDependencies(item).length && !dependencies(item).some(row => row.status === 'skipped'), 'mission-skipped': !unmetDependencies(item).length && dependencies(item).some(row => row.status === 'skipped') }">{{ unmetDependencies(item).length ? '⚠ ' : dependencies(item).some(row => row.status === 'skipped') ? '○ ' : '✓ ' }}{{ dependencySummary(item) }}</small><details class="outing-item-details"><summary>{{ item.note ? 'Details' : 'Add details' }}</summary><textarea :value="item.note" rows="2" placeholder="Note (optional)" @blur="patchItem(item, { note: $event.target.value })"></textarea></details><select v-if="section.id === 'gameplan'" :value="item.time_hint || ''" aria-label="Optional time hint" @change="patchItem(item, { time_hint: $event.target.value || null })"><option value="">Anytime</option><option value="Dusk">Dusk</option><option value="10:30 PM">10:30 PM</option><option value="Late">Late</option></select></div>
                <div class="outing-item-tools"><button type="button" :disabled="index === 0" :aria-label="`Move ${item.title} earlier`" @click="reorder(item, -1)">↑</button><button type="button" :disabled="index === sectionItems(section.id).length - 1" :aria-label="`Move ${item.title} later`" @click="reorder(item, 1)">↓</button><button v-if="section.id !== 'prep'" type="button" aria-label="Add setup dependency" @click="dependencyItemId = dependencyItemId === item.id ? null : item.id">＋ Needs setup</button><button type="button" class="outing-optional-toggle" @click="patchItem(item, { required: !item.required })">{{ item.required ? 'Required' : 'Optional' }}</button><button type="button" :disabled="item.status === 'completed'" :aria-label="item.status === 'skipped' ? `Restore ${item.title}` : `Skip ${item.title}`" @click="patchItem(item, { status: item.status === 'skipped' ? 'pending' : 'skipped' })">{{ item.status === 'skipped' ? 'Restore' : 'Skip' }}</button><button type="button" :aria-label="`Remove ${item.title}`" @click="removeItem(item)">×</button></div>
                <div v-if="dependencyItemId === item.id" class="outing-dependency-editor"><strong>Needs setup</strong><label v-for="prep in items.filter(row => row.section === 'prep')" :key="prep.id"><input type="checkbox" :checked="item.depends_on_prep_ids?.includes(prep.id)" @change="toggleDependency(item, prep.id)" />{{ prep.title }}</label><div class="outing-add-prep"><input v-model="newPrepTitle" placeholder="Add setup item" @keydown.enter.prevent="addAndLinkPrep" /><button type="button" :disabled="!newPrepTitle.trim()" @click="addAndLinkPrep">Add & link</button></div></div>
              </article>
              <p v-if="sectionItems(section.id).length === 0 && remainingOnly && sectionTotal(section.id)" class="outing-empty">Everything here is checked off.</p>
            </div>
            <form class="outing-add-row" @submit.prevent="addFromInput(section.id)"><input v-model="newTitles[section.id]" :placeholder="section.empty" maxlength="240" /><button type="submit" :disabled="!newTitles[section.id].trim()">＋ Add</button></form>
          </details>
        </section>
        <p v-if="error" class="outing-error" role="alert">{{ error }}</p>
        <footer class="outing-footer"><button type="button" class="secondary-button" @click="dismiss">Close</button><template v-if="!activeSession"><button v-if="hasPendingBlockers" type="button" class="secondary-button" @click="remainingOnly=false">Review blockers</button><button type="button" class="primary" @click="start(hasPendingBlockers)">{{ hasPendingBlockers ? 'Start search anyway' : 'Start search' }}</button></template></footer>
      </template>
    </section>
  </div>
</template>
