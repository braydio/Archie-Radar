<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ api: { type: String, required: true } })
const emit = defineEmits(['review-new', 'updated'])
const groups = ref([])
const status = ref({ paired: false, last_sync: null })
const run = ref(null)
const loading = ref(false)
const error = ref('')
const pairingToken = ref('')
const showAdd = ref(false)
const groupUrl = ref('')
const groupName = ref('')
const cutoffChoice = ref('2026-06-01')
const customCutoff = ref('2026-06-01')
let pollTimer = null
let refreshing = false

const enabledCount = computed(() => groups.value.filter(group => group.enabled).length)
const latestRun = computed(() => run.value || status.value.last_sync)
const serverReady = computed(() => Boolean(status.value.server_session_ready))

async function request(path, options = {}) {
  const response = await fetch(`${props.api}${path}`, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `Facebook connector returned ${response.status}`)
  return body
}

async function refresh() {
  if (refreshing) return
  refreshing = true
  try {
    const [groupRows, connectorStatus] = await Promise.all([
      request('/api/facebook/groups'), request('/api/facebook/status')
    ])
    const previousGroupIds = groups.value.map(group => group.id).sort().join(',')
    groups.value = groupRows
    if (previousGroupIds !== groupRows.map(group => group.id).sort().join(',')) emit('updated')
    status.value = connectorStatus
    if (connectorStatus.last_sync) run.value = connectorStatus.last_sync
    if (run.value && ['queued', 'syncing'].includes(run.value.status)) {
      const current = await request(`/api/facebook/sync/${run.value.id}`)
      run.value = current
    }
  } catch (cause) { error.value = cause.message }
  finally { refreshing = false }
}

async function pairBrowser() {
  error.value = ''
  try {
    const result = await request('/api/facebook/pair', { method: 'POST' })
    pairingToken.value = result.token
    await refresh()
  } catch (cause) { error.value = cause.message }
}

async function addGroup() {
  error.value = ''
  try {
    const cutoff = cutoffChoice.value === 'custom' ? customCutoff.value : cutoffChoice.value
    await request('/api/facebook/groups', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_url: groupUrl.value.trim(), group_name: groupName.value.trim() || 'Facebook group',
        enabled: true, initial_sync_cutoff: `${cutoff}T00:00:00Z` })
    })
    groupUrl.value = ''; groupName.value = ''; showAdd.value = false
    emit('updated')
    await refresh()
  } catch (cause) { error.value = cause.message }
}

async function toggleGroup(group) {
  error.value = ''
  try {
    await request(`/api/facebook/groups/${group.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !group.enabled })
    })
    emit('updated')
    await refresh()
  } catch (cause) { error.value = cause.message }
}

async function syncNow() {
  loading.value = true; error.value = ''
  try {
    run.value = await request('/api/facebook/sync', { method: 'POST' })
    window.dispatchEvent(new CustomEvent('archie-facebook-sync-started'))
    await refresh()
  } catch (cause) { error.value = cause.message }
  finally { loading.value = false }
}

async function copyToken() {
  try { await navigator.clipboard.writeText(pairingToken.value) } catch { /* The token remains selectable for manual copy. */ }
}

function syncTime(value) {
  if (!value) return 'Not synced yet'
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  return minutes < 1 ? 'Just now' : `${minutes}m ago`
}

onMounted(() => {
  refresh()
  pollTimer = window.setInterval(refresh, 5000)
})
onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>

<template>
  <section class="facebook-groups-panel" aria-labelledby="facebook-groups-heading">
    <div class="facebook-panel-header">
      <div><p class="eyebrow">FACEBOOK · SERVER COLLECTOR</p><h3 id="facebook-groups-heading">Selected groups</h3></div>
      <span :class="['facebook-paired-state', { connected: serverReady }]">{{ serverReady ? 'Server session ready' : 'One-time setup needed' }}</span>
    </div>
    <p class="facebook-panel-intro">After one-time setup, Archie Radar scans only the groups you select from its own headless browser. Your everyday browser can be completely closed.</p>

    <div class="facebook-panel-actions">
      <button class="secondary-button" type="button" @click="pairBrowser">{{ serverReady ? 'Refresh Facebook session' : 'Connect Facebook once' }}</button>
      <button class="primary" type="button" :disabled="loading || !serverReady || enabledCount === 0" @click="syncNow">{{ loading ? 'Queuing…' : 'Sync selected groups' }}</button>
    </div>

    <div v-if="pairingToken" class="facebook-pair-instructions">
      <strong>One-time Facebook session handoff</strong>
      <p>Load the <code>browser-extension</code> folder once, while signed into Facebook. Open its popup, enter this Archie Radar server URL, paste the token, then choose <strong>Connect & hand off session</strong>. After it says the server session is ready, this browser does not need to remain open.</p>
      <div class="facebook-token-row"><input aria-label="One-time extension token" readonly :value="pairingToken" @focus="$event.target.select()" /><button class="secondary-button" type="button" @click="copyToken">Copy</button></div>
      <button class="inline-button" type="button" @click="pairingToken = ''">Hide token</button>
    </div>

    <div v-if="latestRun" class="facebook-run-summary">
      <strong>Last sync · {{ latestRun.status.replaceAll('_', ' ') }}</strong>
      <span>{{ latestRun.posts_seen || 0 }} posts scanned · {{ latestRun.posts_new || 0 }} new candidates · {{ latestRun.crossposts_combined || 0 }} cross-posts combined</span>
      <button v-if="latestRun.posts_new" class="inline-button" type="button" @click="emit('review-new')">Review {{ latestRun.posts_new }} new</button>
      <details v-if="latestRun.groups?.length"><summary>Group receipts</summary><div v-for="receipt in latestRun.groups" :key="receipt.group.id" class="facebook-receipt"><b>{{ receipt.group.group_name }}</b><span>{{ receipt.status }} · {{ receipt.scanned }} scanned · {{ receipt.posts_new }} new · {{ receipt.crossposts_combined }} combined</span><small v-if="receipt.error || receipt.parser_warning">{{ receipt.error || receipt.parser_warning }}</small></div></details>
      <small v-if="latestRun.error_summary" class="facebook-error-summary">{{ latestRun.error_summary }}</small>
    </div>

    <div class="facebook-group-list">
      <p class="eyebrow">FACEBOOK GROUPS · {{ enabledCount }} SELECTED</p>
      <p v-if="!groups.length" class="facebook-empty">Add Facebook group URLs here. The extension's in-group button is only an optional shortcut for adding a group, not a requirement for scanning.</p>
      <article v-for="group in groups" :key="group.id" class="facebook-group-row">
        <button type="button" class="facebook-group-toggle" :aria-label="`${group.enabled ? 'Disable' : 'Enable'} ${group.group_name}`" @click="toggleGroup(group)">{{ group.enabled ? '✓' : '○' }}</button>
        <div><strong>{{ group.group_name }}</strong><span>{{ group.last_error ? `Needs attention · ${group.last_error}` : `Last synced ${syncTime(group.last_success_at)}` }}</span></div>
      </article>
      <button class="inline-button" type="button" @click="showAdd = !showAdd">{{ showAdd ? 'Cancel adding group' : '+ Add group' }}</button>
    </div>

    <form v-if="showAdd" class="facebook-add-form" @submit.prevent="addGroup">
      <label>Facebook group URL<input v-model="groupUrl" required type="url" placeholder="https://www.facebook.com/groups/..." /></label>
      <label>Group name<input v-model="groupName" type="text" placeholder="Group name (optional)" /></label>
      <label>First sync starts<select v-model="cutoffChoice"><option value="2026-09-20">Last 7 days</option><option value="2026-08-28">Last 30 days</option><option value="2026-06-27">Since Archie disappeared</option><option value="2026-06-01">Since June 1, 2026</option><option value="custom">Custom date</option></select></label>
      <label v-if="cutoffChoice === 'custom'">Custom cutoff<input v-model="customCutoff" type="date" required /></label>
      <button class="primary" type="submit">Save group</button>
    </form>
    <p v-if="error" class="error facebook-panel-error">{{ error }}</p>
  </section>
</template>
