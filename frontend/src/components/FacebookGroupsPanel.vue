<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ api: { type: String, required: true } })
const emit = defineEmits(['review-new', 'updated', 'sync-finished'])
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
let runBaselineSet = false
let observedRunId = null
let observedRunStatus = null

const enabledCount = computed(() => groups.value.filter(group => group.enabled).length)
const latestRun = computed(() => run.value || status.value.last_sync)
const serverReady = computed(() => Boolean(status.value.server_session_ready))
const collectorReady = computed(() => status.value.collector_mode === 'server' ? serverReady.value : Boolean(status.value.paired))
const receipts = computed(() => latestRun.value?.groups || [])
const catRelated = computed(() => receipts.value.reduce((sum, row) => sum + Number(row.cat_related || 0), 0))
const alreadyKnown = computed(() => receipts.value.reduce((sum, row) => sum + Number(row.already_known || 0), 0))
const failedGroups = computed(() => receipts.value.filter(row => row.status === 'failed').length)
const warningGroups = computed(() => receipts.value.filter(row => row.status === 'parser_warning').length)
const finishedGroups = computed(() => receipts.value.filter(row => ['success', 'failed', 'parser_warning', 'disabled'].includes(row.status)).length)
const runStateLabel = computed(() => ({ queued: 'Queued', syncing: `Syncing · ${finishedGroups.value}/${latestRun.value?.requested_group_count || 0} groups finished`, complete: 'Sync complete', partial: 'Partial sync', failed: 'Sync failed' })[latestRun.value?.status] || 'Sync status unknown')
const runStateSymbol = computed(() => ({ queued: '○', syncing: '↻', complete: '✓', partial: '!', failed: '×' })[latestRun.value?.status] || '•')
function receiptLine(row) { return `${row.scanned || 0} scanned · ${row.cat_related || 0} cat-related · ${row.posts_new || 0} new${row.already_known ? ` · ${row.already_known} already known` : ''}${row.crossposts_combined ? ` · ${row.crossposts_combined} cross-post merged` : ''}` }
function syncInterpretation(run) {
  if (run.status === 'failed') return 'The Facebook scan did not complete successfully. Open group receipts for the failure.'
  if (run.status === 'partial') return `Only ${run.successful_group_count || 0} of ${run.requested_group_count || 0} groups completed. Open group receipts to see which group needs attention.`
  if (run.status === 'complete' && !catRelated.value) return `Collector completed normally. It scanned ${run.posts_seen || 0} rendered posts but found no cat-related candidates.`
  if (run.status === 'complete') return `Collector completed normally. ${run.posts_new || 0} unique ${run.posts_new === 1 ? 'candidate was' : 'candidates were'} new; ${catRelated.value} cat-related reports were already in Radar.`
  return ''
}
function runDuration(run) {
  if (!run.started_at || !run.completed_at) return ''
  const seconds = Math.max(0, Math.round((new Date(run.completed_at) - new Date(run.started_at)) / 1000))
  return seconds < 90 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

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
    let nextRun = connectorStatus.last_sync || run.value
    if (nextRun && ['queued', 'syncing'].includes(nextRun.status)) nextRun = await request(`/api/facebook/sync/${nextRun.id}`)
    run.value = nextRun
    if (nextRun) {
      if (!runBaselineSet) { runBaselineSet = true; observedRunId = nextRun.id; observedRunStatus = nextRun.status }
      else {
        const terminal = ['complete', 'partial', 'failed'].includes(nextRun.status)
        const newlyObserved = nextRun.id !== observedRunId
        const transitioned = nextRun.id === observedRunId && ['queued', 'syncing'].includes(observedRunStatus) && terminal
        if (terminal && (newlyObserved || transitioned)) emit('sync-finished', nextRun)
        observedRunId = nextRun.id; observedRunStatus = nextRun.status
      }
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

async function clearServerSession() {
  error.value = ''
  try {
    await request('/api/facebook/session', { method: 'DELETE' })
    pairingToken.value = ''
    await refresh()
  } catch (cause) { error.value = cause.message }
}

async function syncNow() {
  loading.value = true; error.value = ''
  try {
    run.value = await request('/api/facebook/sync', { method: 'POST' })
    runBaselineSet = true; observedRunId = run.value.id; observedRunStatus = run.value.status
    if (['complete', 'partial', 'failed'].includes(run.value.status)) emit('sync-finished', run.value)
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
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
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
      <span :class="['facebook-paired-state', { connected: collectorReady }]">{{ status.collector_mode === 'server' ? (serverReady ? 'Server session ready' : 'One-time setup needed') : (collectorReady ? 'Browser collector ready' : 'Not connected') }}</span>
    </div>
    <p class="facebook-panel-intro">After one-time setup, Archie Radar scans only the groups you select from its own headless browser. Your everyday browser can be completely closed.</p>
    <p v-if="status.server_session?.auth_state === 'login_required'" class="error facebook-panel-error">Facebook asked the server to log in again. Use <strong>Refresh Facebook session</strong> once, then the server resumes scanning independently.</p>

    <div class="facebook-panel-actions">
      <button class="secondary-button" type="button" @click="pairBrowser">{{ serverReady ? 'Refresh Facebook session' : 'Connect Facebook once' }}</button>
      <button class="primary" type="button" :disabled="loading || !collectorReady || enabledCount === 0" @click="syncNow">{{ loading ? 'Queuing…' : 'Sync selected groups' }}</button>
      <button v-if="serverReady" class="inline-button" type="button" @click="clearServerSession">Clear server session</button>
    </div>

    <div v-if="pairingToken" class="facebook-pair-instructions">
      <strong>One-time Facebook session handoff</strong>
      <p>Load the <code>browser-extension</code> folder once, while signed into Facebook. Open its popup, enter <code>{{ props.api }}</code>, paste the token, then choose <strong>Connect & hand off session</strong>. After it says the server session is ready, this browser does not need to remain open.</p>
      <div class="facebook-token-row"><input aria-label="One-time extension token" readonly :value="pairingToken" @focus="$event.target.select()" /><button class="secondary-button" type="button" @click="copyToken">Copy</button></div>
      <button class="inline-button" type="button" @click="pairingToken = ''">Hide token</button>
    </div>

    <div v-if="latestRun" class="facebook-run-summary">
      <div class="facebook-run-state" :class="`state-${latestRun.status}`"><strong><span aria-hidden="true">{{ runStateSymbol }}</span> {{ runStateLabel }}</strong><span v-if="latestRun.status === 'complete'">{{ latestRun.successful_group_count || 0 }} / {{ latestRun.requested_group_count || 0 }} groups completed</span></div>
      <div v-if="['complete','partial','failed'].includes(latestRun.status)" class="facebook-run-metrics"><span>{{ latestRun.posts_seen || 0 }} scanned</span><span v-if="catRelated">{{ catRelated }} cat-related</span><span>{{ latestRun.posts_new || 0 }} new</span><span v-if="alreadyKnown">{{ alreadyKnown }} already in Radar</span><span v-if="latestRun.posts_filtered">{{ latestRun.posts_filtered }} filtered</span><span v-if="latestRun.crossposts_combined">{{ latestRun.crossposts_combined }} cross-posts merged</span></div>
      <p v-if="syncInterpretation(latestRun)">{{ syncInterpretation(latestRun) }}</p>
      <small v-if="latestRun.completed_at">Completed {{ syncTime(latestRun.completed_at) }}<template v-if="runDuration(latestRun)"> · {{ runDuration(latestRun) }}</template></small>
      <button v-if="latestRun.posts_new" class="inline-button" type="button" @click="emit('review-new')">Review {{ latestRun.posts_new }} new</button>
      <details v-if="latestRun.groups?.length" :open="['partial','failed'].includes(latestRun.status)"><summary>Group receipts · {{ finishedGroups }}/{{ latestRun.requested_group_count || latestRun.groups.length }} completed<template v-if="failedGroups"> · {{ failedGroups }} failed</template><template v-if="warningGroups"> · {{ warningGroups }} warnings</template></summary><div v-for="receipt in latestRun.groups" :key="receipt.group.id" class="facebook-receipt"><b>{{ receipt.status === 'success' ? '✓' : receipt.status === 'failed' ? '×' : receipt.status === 'parser_warning' ? '!' : receipt.status === 'syncing' ? '↻' : '○' }} {{ receipt.group.group_name }}</b><strong>{{ receipt.status.replaceAll('_', ' ') }}</strong><span>{{ receiptLine(receipt) }}</span><small v-if="receipt.error || receipt.parser_warning">{{ receipt.error || receipt.parser_warning }}</small></div></details>
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
