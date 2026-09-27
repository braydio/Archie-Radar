<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useRouter } from 'vue-router'
import CandidateMedia from '../components/candidates/CandidateMedia.vue'
import MediaGallery from '../components/media/MediaGallery.vue'
import { setLocationFocus } from '../surveyor/locationFocus.js'

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const route = useRoute()
const router = useRouter()
const item = ref(null)
const notes = ref([])
const timeline = ref([])
const media = ref([])
const draft = ref('')
const selectedSourceIds = ref([])
const mergeTarget = ref('')
const mergeReason = ref('')
const merges = ref([])
const tab = ref('overview')
const error = ref('')
const saving = ref(false)
const hero = computed(() => item.value?.primary_image || item.value?.case_images?.[0] || null)
const tabs = ['overview', 'activity', 'media', 'sources']
function openCurrentLocation() {
  const location = item.value?.current_location
  if (!location || location.map_latitude == null || location.map_longitude == null) return
  setLocationFocus({ latitude: location.map_latitude, longitude: location.map_longitude,
    displayName: location.location_text || 'Candidate location', precision: location.precision || 'approximate',
    distanceMiles: location.distance_from_home_miles, caseId: item.value.case_id,
    externalIds: item.value.external_ids })
  router.push('/surveyor').then(() => window.dispatchEvent(new Event('archie:location-focus')))
}

async function request(path, options) {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Candidate case could not be loaded')
  return response.status === 204 ? null : response.json()
}
async function load() {
  error.value = ''
  try {
    const id = Number(route.params.caseId)
    const [caseData, caseNotes, events, attachments, mergeHistory] = await Promise.all([
      request(`/api/candidate-cases/${id}`), request(`/api/candidate-cases/${id}/notes`),
      request(`/api/candidate-cases/${id}/timeline`), request(`/api/surveyor/media?candidate_case_id=${id}&limit=2000`),
      request(`/api/candidate-cases/${id}/merges`)
    ])
    item.value = caseData
    notes.value = caseNotes
    timeline.value = events
    media.value = attachments
    merges.value = mergeHistory
    selectedSourceIds.value = []
  } catch (cause) { error.value = cause.message || 'Candidate case could not be loaded' }
}
async function saveNote() {
  if (!draft.value.trim() || saving.value) return
  saving.value = true
  try {
    await request(`/api/candidate-cases/${item.value.case_id}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body: draft.value }) })
    draft.value = ''
    await load()
  } catch (cause) { error.value = cause.message || 'Note could not be saved' }
  finally { saving.value = false }
}
async function review(review_state) {
  try {
    await request(`/api/candidate-cases/${item.value.case_id}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ review_state }) })
    await load()
  } catch (cause) { error.value = cause.message || 'Review could not be saved' }
}
async function splitSources() {
  try {
    await request(`/api/candidate-cases/${item.value.case_id}/split`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ post_ids: selectedSourceIds.value, reason: mergeReason.value }) })
    await load()
  } catch (cause) { error.value = cause.message || 'Source records could not be split' }
}
async function mergeCase() {
  if (!Number(mergeTarget.value)) return
  try {
    await request(`/api/candidate-cases/${item.value.case_id}/merge`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ other_case_id: Number(mergeTarget.value), reason: mergeReason.value }) })
    mergeTarget.value = ''
    await load()
  } catch (cause) { error.value = cause.message || 'Cases could not be merged' }
}
async function reverseMerge(mergeId) {
  try {
    await request(`/api/candidate-cases/${item.value.case_id}/merges/${mergeId}/reverse`, { method: 'POST' })
    await load()
  } catch (cause) { error.value = cause.message || 'Merge could not be reversed' }
}
onMounted(load)
watch(() => route.params.caseId, load)
</script>

<template>
  <main class="candidate-case-page" v-if="item">
    <RouterLink class="case-back-link" to="/">← Candidates</RouterLink>
    <header class="candidate-case-hero">
      <CandidateMedia v-if="hero" :image="hero" :other-images="item.case_images?.filter(image => image.url !== hero.url) || []" :alt="`Candidate case ${item.case_id} photo`" :case-id="item.case_id" />
      <div class="candidate-case-facts">
        <p class="eyebrow">CURRENT CUSTODY</p>
        <h1>{{ item.current_custody?.holding_entity || item.current_custody?.custody_label || 'Status unknown' }}</h1>
        <p>{{ item.current_custody?.custody_label || item.custody_label || 'Status unknown' }}<template v-if="item.source_platform"> · via {{ item.source_platform }}</template></p>
        <div class="candidate-case-ids">
          <strong v-for="identifier in item.external_ids" :key="identifier.namespace + identifier.value">{{ identifier.label }} {{ identifier.value }}</strong>
          <span>Radar case #{{ item.case_id }} · {{ item.record_count }} source {{ item.record_count === 1 ? 'record' : 'records' }}</span>
        </div>
        <p v-if="item.current_location?.location_text">{{ item.current_location.location_text }}<template v-if="item.current_location.distance_from_home_miles != null"> · {{ item.current_location.distance_is_approximate ? '~' : '' }}{{ Number(item.current_location.distance_from_home_miles).toFixed(1) }} mi from home</template><small v-if="item.current_location.record_id"> · source record #{{ item.current_location.record_id }}</small></p>
        <button v-if="item.current_location?.map_latitude != null" type="button" class="secondary-button" @click="openCurrentLocation">Open location in Surveyor</button>
        <div class="review-actions case-review-actions">
          <button class="possible" @click="review('possible')">Possible Archie</button>
          <button class="hold" @click="review('needs_review')">Hold</button>
          <button class="dismiss" @click="review('dismissed')">Not Archie</button>
        </div>
      </div>
    </header>

    <nav class="candidate-case-tabs" aria-label="Candidate case sections">
      <button v-for="name in tabs" :key="name" type="button" :aria-current="tab === name ? 'page' : undefined" @click="tab = name">{{ name }}</button>
    </nav>
    <p v-if="error" class="error-banner">{{ error }}</p>

    <section v-if="tab === 'overview'" class="candidate-case-content">
      <h2>Case overview</h2>
      <p>{{ item.description || 'No description is available from the current source record.' }}</p>
      <p v-if="item.current_location?.record_id" class="inspector-meta">Location from source record #{{ item.current_location.record_id }} · {{ item.current_location.precision || 'precision unknown' }}</p>
      <h3>Case notes</h3>
      <form class="case-note-form" @submit.prevent="saveNote"><textarea v-model="draft" rows="3" placeholder="Add a case note"></textarea><button type="submit" :disabled="saving || !draft.trim()">{{ saving ? 'Saving…' : 'Add note' }}</button></form>
      <article v-for="note in notes" :key="note.id" class="case-note"><time>{{ new Date(note.created_at).toLocaleString() }}</time><p>{{ note.body }}</p></article>
    </section>
    <section v-else-if="tab === 'activity'" class="candidate-case-content">
      <h2>Activity</h2>
      <article v-for="entry in timeline" :key="`${entry.kind}-${entry.id}`" class="case-timeline-row"><time>{{ entry.occurred_at ? new Date(entry.occurred_at).toLocaleString() : 'Date unknown' }}</time><strong>{{ entry.label }}</strong><p v-if="entry.body">{{ entry.body }}</p><small v-if="entry.kind === 'source_record'">{{ entry.source_record?.holding_entity || entry.source_record?.source_label }} · {{ entry.source_record?.listing_state || 'status unknown' }}</small></article>
    </section>
    <section v-else-if="tab === 'media'" class="candidate-case-content">
      <h2>Field media</h2><MediaGallery :items="media" :api="API" title="Linked field media" />
    </section>
    <section v-else class="candidate-case-content">
      <h2>Source records</h2>
      <details class="case-identity-actions"><summary>Correct case identity</summary>
        <p>Select source records that are actually different cats to split them into a new case.</p>
        <label v-for="record in item.source_records" :key="`select-${record.post_id}`" class="case-source-select"><input v-model="selectedSourceIds" type="checkbox" :value="record.post_id" /> {{ record.holding_entity || record.custody_label || record.source_label }} · {{ record.identifier_label }} {{ record.source_id }}</label>
        <label>Reason <input v-model="mergeReason" maxlength="2000" placeholder="Optional explanation" /></label>
        <button type="button" class="secondary-button" :disabled="!selectedSourceIds.length || selectedSourceIds.length >= item.source_records.length" @click="splitSources">These are different cats · split selected records</button>
        <hr />
        <label>Merge into this case from Radar case # <input v-model="mergeTarget" type="number" min="1" /></label>
        <button type="button" class="secondary-button" :disabled="!Number(mergeTarget)" @click="mergeCase">Confirm same cat · merge</button>
        <h3>Merge history</h3>
        <article v-for="merge in merges" :key="merge.id" class="case-merge-row"><span>Case #{{ merge.absorbed_case_id }} merged {{ new Date(merge.created_at).toLocaleString() }}<template v-if="merge.reason"> · {{ merge.reason }}</template></span><button v-if="!merge.reversed_at" type="button" @click="reverseMerge(merge.id)">Undo merge</button><span v-else>Reversed</span></article>
      </details>
      <article v-for="record in item.source_records" :key="record.post_id" class="case-source-row">
        <div><strong>{{ record.holding_entity || record.custody_label || record.source_label }}</strong><span>{{ record.custody_label || record.status }} · via {{ record.source_platform || record.source_label }}</span><small>{{ record.identifier_label }} {{ record.source_id }} · {{ record.listing_state || 'status unknown' }}<template v-if="record.listing_state_reason"> ({{ record.listing_state_reason }})</template></small></div>
        <a v-if="record.source_url" :href="record.source_url" target="_blank" rel="noopener">Open source ↗</a>
      </article>
    </section>
  </main>
  <main v-else class="candidate-case-loading"><RouterLink to="/">← Candidates</RouterLink><p>{{ error || 'Loading candidate case…' }}</p></main>
</template>
