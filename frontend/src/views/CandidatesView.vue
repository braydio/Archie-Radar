<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import CandidateCard from '../components/CandidateCard.vue'
import FilterSection from '../components/FilterSection.vue'
import SearchMap from '../components/SearchMap.vue'
import FacebookGroupsPanel from '../components/FacebookGroupsPanel.vue'
import { sourceLabel, statusLabel } from '../lib/format.js'

const FILTER_STORAGE = 'archie-radar-v09-filters'
const CASE_RETURN_STORAGE = 'archie-radar-case-return'
const DEFAULT_NOT_BEFORE = '2026-06-01'
const DEFAULT_FILTERS = Object.freeze({
  source: '',
  facebookGroupId: '',
  status: '',
  sex: 'male',
  photoFilter: 'any',
  ageDays: 0,
  minScore: 0,
  maxDistance: 25,
  hideDuplicates: true,
  color: 'orange',
  pattern: 'striped',
  coat: 'short',
  collar: 'none',
  microchip: 'none',
  altered: 'neutered',
  whiteChest: 'yes',
  whiteBelly: 'any',
  whitePaws: 'any',
  whiteFace: 'any',
  ageCompatible: false,
  archieCompatible: false,
  notBefore: DEFAULT_NOT_BEFORE,
  traitMode: 'prioritize'
})

export default {
  name: 'App',
  components: { CandidateCard, FilterSection, SearchMap, FacebookGroupsPanel },
  setup() {
    const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
    const posts = ref([])
    const referencePhotos = ref([])
    const searchConfig = ref(null)
    const queueStats = ref({})
    const filterOptions = ref({ sources: [], statuses: [], sexes: [], colors: [], patterns: [], coats: [] })
    const loading = ref(false)
    const uploading = ref(false)
    const error = ref('')
    const scanSummary = ref(null)
    const filtersOpen = ref(false)
    const filterSectionOpen = ref({ area: true, appearance: true, markings: false, identification: false, queue: false })
    const defaultsExpanded = ref(false)
    const setupOpen = ref(false)
    const sourcesOpen = ref(false)
    const showMap = ref(false)
    const filterSheet = ref(null)
    const filterButton = ref(null)
    const refreshBusy = ref({})
    const refreshReceipt = ref({})
    let candidateFeedController = null
    let candidateRequestVersion = 0

    const state = ref('new')
    const sort = ref('smart')

    const source = ref(DEFAULT_FILTERS.source)
    const facebookGroupId = ref(DEFAULT_FILTERS.facebookGroupId)
    const status = ref(DEFAULT_FILTERS.status)
    const sex = ref(DEFAULT_FILTERS.sex)
    const photoFilter = ref(DEFAULT_FILTERS.photoFilter)
    const ageDays = ref(DEFAULT_FILTERS.ageDays)
    const minScore = ref(DEFAULT_FILTERS.minScore)
    const maxDistance = ref(DEFAULT_FILTERS.maxDistance)
    const hideDuplicates = ref(DEFAULT_FILTERS.hideDuplicates)
    const color = ref(DEFAULT_FILTERS.color)
    const pattern = ref(DEFAULT_FILTERS.pattern)
    const coat = ref(DEFAULT_FILTERS.coat)
    const collar = ref(DEFAULT_FILTERS.collar)
    const microchip = ref(DEFAULT_FILTERS.microchip)
    const altered = ref(DEFAULT_FILTERS.altered)
    const whiteChest = ref(DEFAULT_FILTERS.whiteChest)
    const whiteBelly = ref(DEFAULT_FILTERS.whiteBelly)
    const whitePaws = ref(DEFAULT_FILTERS.whitePaws)
    const whiteFace = ref(DEFAULT_FILTERS.whiteFace)
    const ageCompatible = ref(DEFAULT_FILTERS.ageCompatible)
    const archieCompatible = ref(DEFAULT_FILTERS.archieCompatible)
    const notBefore = ref(DEFAULT_FILTERS.notBefore)
    const traitMode = ref(DEFAULT_FILTERS.traitMode)
    const appliedFilters = ref({ ...DEFAULT_FILTERS })

    function draftSnapshot() {
      return {
        source: source.value,
        facebookGroupId: facebookGroupId.value,
        status: status.value,
        sex: sex.value,
        photoFilter: photoFilter.value,
        ageDays: Number(ageDays.value || 0),
        minScore: Number(minScore.value || 0),
        maxDistance: Number(maxDistance.value || 500),
        hideDuplicates: Boolean(hideDuplicates.value),
        color: color.value,
        pattern: pattern.value,
        coat: coat.value,
        collar: collar.value,
        microchip: microchip.value,
        altered: altered.value,
        whiteChest: whiteChest.value,
        whiteBelly: whiteBelly.value,
        whitePaws: whitePaws.value,
        whiteFace: whiteFace.value,
        ageCompatible: Boolean(ageCompatible.value),
        archieCompatible: Boolean(archieCompatible.value),
        notBefore: notBefore.value,
        traitMode: traitMode.value
      }
    }

    function loadDraft(values) {
      const f = { ...DEFAULT_FILTERS, ...(values || {}) }
      source.value = f.source
      facebookGroupId.value = f.facebookGroupId
      status.value = f.status
      sex.value = f.sex
      photoFilter.value = f.photoFilter
      ageDays.value = Number(f.ageDays || 0)
      minScore.value = Number(f.minScore || 0)
      maxDistance.value = Number(f.maxDistance || 500)
      hideDuplicates.value = Boolean(f.hideDuplicates)
      color.value = f.color
      pattern.value = f.pattern
      coat.value = f.coat
      collar.value = f.collar
      microchip.value = f.microchip
      altered.value = f.altered
      whiteChest.value = f.whiteChest
      whiteBelly.value = f.whiteBelly
      whitePaws.value = f.whitePaws
      whiteFace.value = f.whiteFace
      ageCompatible.value = Boolean(f.ageCompatible)
      archieCompatible.value = Boolean(f.archieCompatible)
      notBefore.value = f.notBefore
      traitMode.value = f.traitMode
    }

    try {
      const saved = JSON.parse(localStorage.getItem(FILTER_STORAGE) || '{}')
      if (saved?.filters) {
        appliedFilters.value = { ...DEFAULT_FILTERS, ...saved.filters }
        loadDraft(appliedFilters.value)
      }
      if (typeof saved?.sort === 'string') sort.value = saved.sort
    } catch {}

    function persistApplied() {
      localStorage.setItem(FILTER_STORAGE, JSON.stringify({ filters: appliedFilters.value, sort: sort.value }))
    }

    const queueTabs = computed(() => [
      { value: 'new', label: 'New', count: queueStats.value.new || 0 },
      { value: 'possible', label: 'Possible Archie', count: queueStats.value.possible || 0 },
      { value: 'needs_review', label: 'Hold', count: queueStats.value.needs_review || 0 },
      { value: 'dismissed', label: 'Dismissed', count: queueStats.value.dismissed || 0 }
    ])
    const sourceOptions = computed(() => (filterOptions.value.sources || []).map(value => ({ value, label: sourceLabel(value) })))
    const statusOptions = computed(() => (filterOptions.value.statuses || []).map(value => ({ value, label: statusLabel(value) || value })))
    const setupNeededCount = computed(() => (searchConfig.value?.source_statuses || []).filter(item => item.status === 'setup_required' || item.status === 'configured_pending_mapping').length)
    const activeSourceCount = computed(() => (searchConfig.value?.source_statuses || []).filter(item => item.status === 'active').length)
    const mappedCount = computed(() => posts.value.filter(p => p.map_latitude != null && p.map_longitude != null).length)

    const nonDefaultApplied = computed(() => {
      const f = appliedFilters.value
      const chips = []
      if (f.source !== DEFAULT_FILTERS.source) chips.push(`Source: ${sourceLabel(f.source)}`)
      if (f.facebookGroupId) chips.push(`Facebook group: ${(filterOptions.value.facebook_groups || []).find(group => String(group.id) === String(f.facebookGroupId))?.group_name || 'Selected group'}`)
      if (f.status !== DEFAULT_FILTERS.status) chips.push(`Status: ${statusLabel(f.status) || f.status}`)
      if (f.maxDistance !== DEFAULT_FILTERS.maxDistance) chips.push(f.maxDistance >= 500 ? 'Any distance' : `${f.maxDistance} mi`)
      if (f.notBefore !== DEFAULT_FILTERS.notBefore) chips.push(f.notBefore ? `On/after ${f.notBefore}` : 'Older dates included')
      if (f.traitMode !== DEFAULT_FILTERS.traitMode) chips.push('Hide trait mismatches')
      if (f.sex !== DEFAULT_FILTERS.sex) chips.push(`Sex: ${f.sex || 'any'}`)
      if (f.color !== DEFAULT_FILTERS.color) chips.push(`Color: ${f.color || 'any'}`)
      if (f.pattern !== DEFAULT_FILTERS.pattern) chips.push(`Pattern: ${f.pattern || 'any'}`)
      if (f.coat !== DEFAULT_FILTERS.coat) chips.push(`Coat: ${f.coat || 'any'}`)
      if (f.altered !== DEFAULT_FILTERS.altered) chips.push(`Altered: ${f.altered || 'any'}`)
      if (f.whiteChest !== DEFAULT_FILTERS.whiteChest) chips.push(`White chest: ${f.whiteChest}`)
      if (f.whiteBelly !== DEFAULT_FILTERS.whiteBelly) chips.push(`White belly: ${f.whiteBelly}`)
      if (f.whitePaws !== DEFAULT_FILTERS.whitePaws) chips.push(`White paws: ${f.whitePaws}`)
      if (f.whiteFace !== DEFAULT_FILTERS.whiteFace) chips.push(`White face: ${f.whiteFace}`)
      if (f.collar !== DEFAULT_FILTERS.collar) chips.push(`Collar: ${f.collar || 'any'}`)
      if (f.microchip !== DEFAULT_FILTERS.microchip) chips.push(`Microchip: ${f.microchip || 'any'}`)
      if (f.ageCompatible !== DEFAULT_FILTERS.ageCompatible) chips.push(f.ageCompatible ? 'Age ~8' : 'Any age')
      if (f.archieCompatible !== DEFAULT_FILTERS.archieCompatible) chips.push('Archie-compatible only')
      if (f.photoFilter !== DEFAULT_FILTERS.photoFilter) chips.push(f.photoFilter === 'with' ? 'Has photo' : 'No photo')
      if (f.ageDays !== DEFAULT_FILTERS.ageDays) chips.push(`Past ${f.ageDays}d`)
      if (f.minScore !== DEFAULT_FILTERS.minScore) chips.push(`Match signals ${f.minScore}+`)
      if (f.hideDuplicates !== DEFAULT_FILTERS.hideDuplicates) chips.push(f.hideDuplicates ? 'Hide reposts' : 'Show reposts')
      return chips
    })

    const selectedDraftTraits = computed(() => {
      const items = []
      if (sex.value) items.push('male')
      if (color.value) items.push(color.value)
      if (pattern.value) items.push(pattern.value === 'striped' ? 'striped / tabby' : pattern.value)
      if (coat.value) items.push(`${coat.value} hair`)
      if (altered.value) items.push(altered.value)
      if (whiteChest.value === 'yes') items.push('white chest')
      if (whiteBelly.value === 'yes') items.push('white belly')
      if (whiteBelly.value === 'no') items.push('no white belly')
      if (whitePaws.value === 'yes') items.push('white paws')
      if (whitePaws.value === 'no') items.push('no white paws')
      if (whiteFace.value === 'yes') items.push('white face')
      if (whiteFace.value === 'no') items.push('no white face')
      if (collar.value === 'none') items.push('no collar')
      if (microchip.value === 'none') items.push('not microchipped')
      if (ageCompatible.value) items.push('age ~8')
      return items
    })

    const defaultTraitCount = computed(() => selectedDraftTraits.value.length)
    const filterSummaries = computed(() => {
      const label = value => String(value || '').replaceAll('_', ' ')
      const join = values => values.filter(Boolean).join(' · ')
      const appearance = join([
        sex.value && label(sex.value), color.value && label(color.value), pattern.value && (pattern.value === 'striped' ? 'tabby' : label(pattern.value)),
        coat.value && `${coat.value} hair`, altered.value && label(altered.value)
      ])
      const markings = join([
        whiteChest.value !== 'any' && `White chest ${whiteChest.value}`,
        whiteBelly.value !== 'any' && `White belly ${whiteBelly.value}`,
        whitePaws.value !== 'any' && `White paws ${whitePaws.value}`,
        whiteFace.value !== 'any' && `White face ${whiteFace.value}`
      ])
      const identification = join([
        collar.value && (collar.value === 'none' ? 'No collar' : 'Collar'),
        microchip.value && (microchip.value === 'none' ? 'Not microchipped' : 'Microchipped'),
        ageCompatible.value && 'Age ~8', archieCompatible.value && 'Archie-compatible',
        photoFilter.value !== 'any' && (photoFilter.value === 'with' ? 'Has photo' : 'No photo')
      ])
      const area = join([
        maxDistance.value !== DEFAULT_FILTERS.maxDistance && (Number(maxDistance.value) >= 500 ? 'Any distance' : `${maxDistance.value} mi`),
        ageDays.value && `Past ${ageDays.value} days`, notBefore.value !== DEFAULT_FILTERS.notBefore && (notBefore.value ? `Since ${notBefore.value}` : 'Older dates'),
        source.value && sourceLabel(source.value), status.value && statusLabel(status.value)
      ])
      const queue = join([minScore.value && `Signals ${minScore.value}+`, hideDuplicates.value !== DEFAULT_FILTERS.hideDuplicates && (hideDuplicates.value ? 'Hide reposts' : 'Show reposts')]) || 'Default'
      return {
        area: area || '25 mi · Since Jun 1', appearance: appearance || 'Archie defaults', markings,
        identification, queue
      }
    })

    function isDefaultDraft(key, value) { return DEFAULT_FILTERS[key] === value }

    function clientPrioritize(list, f) {
      if (sort.value !== 'smart' || f.traitMode !== 'prioritize') return list
      return [...list].map(post => {
        const traits = post.parsed_traits || {}
        let boost = 0
        if (f.sex && post.sex === f.sex) boost += 4
        if (f.color && (traits.colors || []).includes(f.color)) boost += 7
        if (f.pattern && (traits.patterns || []).includes(f.pattern)) boost += 5
        if (f.coat && traits.coat === f.coat) boost += 3
        if (f.altered && traits.altered_status === f.altered) boost += 4
        if (f.whiteChest === 'yes' && traits.white_chest === true) boost += 4
        if (f.whiteChest === 'no' && traits.white_chest === false) boost += 2
        if (f.whiteBelly === 'yes' && traits.white_belly === true) boost += 1
        if (f.whiteBelly === 'no' && traits.white_belly === false) boost += 1
        if (f.whitePaws === 'yes' && traits.white_paws === true) boost += 2
        if (f.whitePaws === 'no' && traits.white_paws === false) boost += 1
        if (f.whiteFace === 'yes' && traits.white_face === true) boost += 2
        if (f.whiteFace === 'no' && traits.white_face === false) boost += 1
        if (f.collar && traits.collar === f.collar) boost += 3
        if (f.microchip && traits.microchip === f.microchip) boost += 3
        if (f.ageCompatible && traits.age_years != null && Math.abs(Number(traits.age_years) - 8) <= 2.5) boost += 2
        if (f.archieCompatible && (post.archie_trait_conflicts || []).length === 0) boost += 5
        return { ...post, _trait_boost: boost }
      }).sort((a, b) => {
        const boost = Number(b._trait_boost || 0) - Number(a._trait_boost || 0)
        if (boost) return boost
        const score = Number(b.match_score || 0) - Number(a.match_score || 0)
        if (score) return score
        return new Date(b.posted_at || b.reported_at || b.first_seen_at || 0) - new Date(a.posted_at || a.reported_at || a.first_seen_at || 0)
      })
    }

    async function load() {
      candidateFeedController?.abort()
      const controller = new AbortController()
      candidateFeedController = controller
      const requestVersion = ++candidateRequestVersion
      loading.value = true
      error.value = ''
      try {
        const f = appliedFilters.value
        const params = new URLSearchParams()
        if (state.value) params.set('review_state', state.value)
        params.set('min_score', String(f.minScore))
        params.set('include_duplicates', f.hideDuplicates ? 'false' : 'true')
        params.set('sort', sort.value)
        if (f.source) params.set('source', f.source)
        if (f.facebookGroupId) params.set('facebook_group_subscription_id', String(f.facebookGroupId))
        if (f.status) params.set('status', f.status)
        if (f.traitMode === 'hide') {
          if (f.sex) params.set('sex', f.sex)
          if (f.color) params.set('color', f.color)
          if (f.pattern) params.set('pattern', f.pattern)
          if (f.coat) params.set('coat', f.coat)
          if (f.collar) params.set('collar', f.collar)
          if (f.microchip) params.set('microchip', f.microchip)
          if (f.altered) params.set('altered', f.altered)
          if (f.whiteChest !== 'any') params.set('white_chest', f.whiteChest === 'yes' ? 'true' : 'false')
          if (f.whiteBelly !== 'any') params.set('white_belly', f.whiteBelly === 'yes' ? 'true' : 'false')
          if (f.whitePaws !== 'any') params.set('white_paws', f.whitePaws === 'yes' ? 'true' : 'false')
          if (f.whiteFace !== 'any') params.set('white_face', f.whiteFace === 'yes' ? 'true' : 'false')
          if (f.ageCompatible) params.set('age_compatible', 'true')
          if (f.archieCompatible) params.set('archie_compatible', 'true')
        }
        if (f.photoFilter === 'with') params.set('has_photo', 'true')
        if (f.photoFilter === 'without') params.set('has_photo', 'false')
        if (f.ageDays > 0) params.set('reported_within_days', String(f.ageDays))
        if (f.notBefore) params.set('not_before', `${f.notBefore}T00:00:00Z`)
        if (f.maxDistance < 500) params.set('max_distance_miles', String(f.maxDistance))
        params.set('limit', '500')
        const res = await fetch(`${API}/api/candidate-cases?${params}`, { signal: controller.signal })
        if (!res.ok) throw new Error(`Candidate feed ${res.status}`)
        const responsePosts = await res.json()
        if (requestVersion === candidateRequestVersion) posts.value = clientPrioritize(responsePosts, f)
      } catch (e) {
        if (e?.name !== 'AbortError' && requestVersion === candidateRequestVersion) error.value = e?.message || String(e)
      } finally {
        if (requestVersion === candidateRequestVersion) loading.value = false
      }
    }

    async function loadConfig() {
      const res = await fetch(`${API}/api/search-config`)
      if (!res.ok) throw new Error(`Search config ${res.status}`)
      searchConfig.value = await res.json()
    }
    async function loadReferencePhotos() {
      const res = await fetch(`${API}/api/reference-photos`)
      if (!res.ok) throw new Error(`Reference photos ${res.status}`)
      referencePhotos.value = await res.json()
    }
    async function loadQueueStats() {
      const params = new URLSearchParams()
      const cutoff = appliedFilters.value.notBefore
      if (cutoff) params.set('not_before', `${cutoff}T00:00:00Z`)
      const res = await fetch(`${API}/api/queue-stats?${params}`)
      if (!res.ok) throw new Error(`Queue stats ${res.status}`)
      queueStats.value = await res.json()
    }
    async function loadFilterOptions() {
      const res = await fetch(`${API}/api/filter-options`)
      if (!res.ok) throw new Error(`Filter options ${res.status}`)
      filterOptions.value = await res.json()
    }
    async function refreshAux() {
      await Promise.all([loadQueueStats(), loadFilterOptions()])
    }

    async function ingest() {
      loading.value = true
      error.value = ''
      try {
        const res = await fetch(`${API}/api/ingest/all`, { method: 'POST' })
        if (!res.ok) throw new Error(`Regional scan failed: ${res.status}`)
        scanSummary.value = await res.json()
        await Promise.all([load(), refreshAux()])
      } catch (e) {
        error.value = e?.message || String(e)
      } finally { loading.value = false }
    }

    const ingestEndpoints = {
      pawboost: 'pawboost', orange_county: 'orange-county', regional_24petconnect: '24petconnect',
      aps_durham: 'aps-durham', wake_county: 'wake-county', pet911: 'pet911', petkey: 'petkey'
    }
    async function refreshSource(key) {
      const endpoint = ingestEndpoints[key]
      if (!endpoint) return
      refreshBusy.value = { ...refreshBusy.value, [key]: true }
      try {
        const res = await fetch(`${API}/api/ingest/${endpoint}`, { method: 'POST' })
        if (!res.ok) throw new Error(`Source refresh failed: ${res.status}`)
        const payload = await res.json()
        refreshReceipt.value = { ...refreshReceipt.value, [key]: payload }
        scanSummary.value = { ...(scanSummary.value || {}), [key]: payload }
        await Promise.all([load(), refreshAux()])
      } catch (e) { error.value = e?.message || String(e) }
      finally { refreshBusy.value = { ...refreshBusy.value, [key]: false } }
    }

    async function review(post, review_state) {
      try {
        const res = await fetch(`${API}/api/candidate-cases/${post.case_id || post.id}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ review_state }) })
        if (!res.ok) throw new Error(`Review update failed: ${res.status}`)
        posts.value = posts.value.filter(item => item.id !== post.id)
        await loadQueueStats()
      } catch (e) { error.value = e?.message || String(e) }
    }

    function locateCandidate(post) {
      const config = searchConfig.value
      if (post.latitude != null && post.longitude != null && config) {
        const lat1 = Number(config.home_latitude) * Math.PI / 180
        const lat2 = Number(post.latitude) * Math.PI / 180
        const dLon = (Number(post.longitude) - Number(config.home_longitude)) * Math.PI / 180
        const y = Math.sin(dLon) * Math.cos(lat2)
        const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon)
        const bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360
        const labels = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        window.dispatchEvent(new CustomEvent('archie:locate', { detail: { latitude: post.latitude, longitude: post.longitude,
          displayName: post.location_text || 'Candidate location', precision: 'address', distance_miles: post.distance_from_home_miles,
          bearing_degrees: Number(bearing.toFixed(1)), bearing_label: labels[Math.round(bearing / 22.5) % 16],
          home: { latitude: config.home_latitude, longitude: config.home_longitude } } }))
      } else {
        window.dispatchEvent(new CustomEvent('archie:locate', { detail: { query: post.location_text || '' } }))
      }
    }

    async function uploadReference(event) {
      const file = event.target.files?.[0]
      if (!file) return
      uploading.value = true
      try {
        const dataUrl = await new Promise((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file)
        })
        const res = await fetch(`${API}/api/reference-photos`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label: file.name, filename: file.name, data_url: dataUrl }) })
        if (!res.ok) throw new Error(`Photo upload failed: ${res.status}`)
        await Promise.all([loadReferencePhotos(), load()])
      } catch (e) { error.value = e?.message || String(e) }
      finally { uploading.value = false; event.target.value = '' }
    }
    async function deleteReference(photo) {
      const res = await fetch(`${API}/api/reference-photos/${photo.id}`, { method: 'DELETE' })
      if (!res.ok) { error.value = `Delete failed: ${res.status}`; return }
      await Promise.all([loadReferencePhotos(), load()])
    }

    async function setQueue(value) { filtersOpen.value = false; state.value = value; await load() }
    async function changeSort() { filtersOpen.value = false; persistApplied(); await load() }
    function toggleMap() { filtersOpen.value = false; showMap.value = !showMap.value }
    function toggleSources() { filtersOpen.value = false; sourcesOpen.value = !sourcesOpen.value; setupOpen.value = false }
    function toggleSetup() { filtersOpen.value = false; setupOpen.value = !setupOpen.value; sourcesOpen.value = false }

    async function applySelections() {
      appliedFilters.value = draftSnapshot()
      persistApplied()
      filtersOpen.value = false
      await Promise.all([load(), loadQueueStats()])
    }
    function clearSelections() {
      loadDraft({
        ...DEFAULT_FILTERS,
        source: '', status: '', sex: '', color: '', pattern: '', coat: '', altered: '',
        whiteChest: 'any', whiteBelly: 'any', whitePaws: 'any', whiteFace: 'any',
        collar: '', microchip: '', ageCompatible: false, archieCompatible: false,
        photoFilter: 'any', ageDays: 0, minScore: 0, maxDistance: 500,
        hideDuplicates: false, notBefore: '', traitMode: 'prioritize'
      })
    }
    async function applyDefaults() {
      loadDraft(DEFAULT_FILTERS)
      appliedFilters.value = { ...DEFAULT_FILTERS }
      persistApplied()
      filtersOpen.value = false
      await Promise.all([load(), loadQueueStats()])
    }
    function openFilters() {
      loadDraft(appliedFilters.value)
      filtersOpen.value = !filtersOpen.value
      sourcesOpen.value = false
      setupOpen.value = false
    }
    function handleOutside(event) {
      if (!filtersOpen.value) return
      if (filterSheet.value?.contains(event.target) || filterButton.value?.contains(event.target)) return
      filtersOpen.value = false
    }

    onBeforeRouteLeave((to) => {
      if (!to.path.startsWith('/candidates/')) return
      try {
        sessionStorage.setItem(CASE_RETURN_STORAGE, JSON.stringify({ state: state.value, sort: sort.value,
          filters: appliedFilters.value, scrollY: window.scrollY, caseIds: posts.value.map(item => item.case_id || item.id) }))
      } catch {}
    })

    onMounted(async () => {
      document.addEventListener('pointerdown', handleOutside)
      let returnState = null
      try {
        returnState = JSON.parse(sessionStorage.getItem(CASE_RETURN_STORAGE) || 'null')
        if (returnState) {
          sessionStorage.removeItem(CASE_RETURN_STORAGE)
          state.value = returnState.state || state.value
          sort.value = returnState.sort || sort.value
          appliedFilters.value = { ...DEFAULT_FILTERS, ...(returnState.filters || {}) }
          loadDraft(appliedFilters.value)
        }
      } catch { returnState = null }
      try {
        await loadConfig()
        await Promise.all([load(), loadReferencePhotos(), loadQueueStats(), loadFilterOptions()])
        if (returnState) {
          await nextTick()
          requestAnimationFrame(() => window.scrollTo(0, Number(returnState.scrollY || 0)))
        }
      }
      catch (e) { error.value = e?.message || String(e) }
    })
    onBeforeUnmount(() => {
      candidateRequestVersion += 1
      candidateFeedController?.abort()
      document.removeEventListener('pointerdown', handleOutside)
    })

    return {
      API, posts, referencePhotos, searchConfig, queueStats, loading, uploading, error, scanSummary,
      filtersOpen, setupOpen, sourcesOpen, showMap, filterSheet, filterButton, state, sort,
      filterSectionOpen, defaultsExpanded, defaultTraitCount, filterSummaries,
      source, facebookGroupId, status, sex, photoFilter, ageDays, minScore, maxDistance, hideDuplicates, color, pattern, coat,
      collar, microchip, altered, whiteChest, whiteBelly, whitePaws, whiteFace, ageCompatible, archieCompatible,
      notBefore, traitMode, queueTabs, sourceOptions, statusOptions, setupNeededCount, activeSourceCount, mappedCount,
      nonDefaultApplied, selectedDraftTraits, refreshBusy, refreshReceipt, isDefaultDraft, appliedFilters,
      ingest, review, uploadReference, deleteReference, setQueue, changeSort, toggleMap, toggleSources, toggleSetup,
      applySelections, clearSelections, applyDefaults, openFilters, refreshSource, locateCandidate
    }
  }
}
</script>

<template>
  <main>
    <header class="app-header">
      <div class="brand-copy">
        <p class="eyebrow">ARCHIE RADAR</p>
        <h1>Lost-cat review</h1>
        <p class="lede">#1 is the next report to review. Archie-like traits are prioritized by default without hiding uncertain reports.</p>
      </div>
      <div class="header-actions">
        <span v-if="queueStats.high_priority_new" class="priority-summary"><strong>{{ queueStats.high_priority_new }}</strong> strong-signal new</span>
        <button class="primary scan-button" @click="ingest" :disabled="loading">{{ loading ? 'Scanning…' : 'Scan now' }}</button>
      </div>
    </header>

    <nav class="queue-tabs" aria-label="Review queues">
      <button v-for="tab in queueTabs" :key="tab.value" :class="{ active: state === tab.value }" @click="setQueue(tab.value)"><span>{{ tab.label }}</span><strong>{{ tab.count }}</strong></button>
    </nav>

    <section class="control-row" aria-label="Review controls">
      <label class="sort-control"><span>Order</span><select v-model="sort" @change="changeSort"><option value="smart">Priority (#1 first)</option><option value="newest">Newest report</option><option value="closest">Closest first</option><option value="score">Strongest match signals</option></select></label>
      <button ref="filterButton" class="control-button" :class="{ active: filtersOpen }" @click="openFilters">Filters</button>
      <button class="control-button map-toggle" :class="{ active: showMap }" @click="toggleMap">{{ showMap ? `Hide map · ${mappedCount}` : `Show map · ${mappedCount}` }}</button>
      <button class="control-button" :class="{ active: sourcesOpen }" @click="toggleSources">Sources · {{ activeSourceCount }} active<span v-if="setupNeededCount" class="setup-count">{{ setupNeededCount }} setup</span></button>
      <button class="control-button setup-button" :class="{ active: setupOpen }" @click="toggleSetup">Archie profile · {{ referencePhotos.length }} photos</button>
    </section>

    <div v-if="nonDefaultApplied.length" class="applied-filter-strip" aria-label="Applied non-default filters">
      <span>Applied:</span><b v-for="chip in nonDefaultApplied" :key="chip">{{ chip }}</b>
    </div>

    <section v-if="filtersOpen" ref="filterSheet" class="filter-sheet">
      <div class="filter-sheet-top">
        <div class="filter-intro">
          <div><p class="eyebrow">FILTERS</p><h2>Review selections</h2><p class="filter-intro-copy">Selections below are staged until you press <strong>Apply Selections</strong>.</p></div>
          <button class="collapse-button" @click="filtersOpen = false">Collapse</button>
        </div>
        <div class="filter-actions three-way top-actions">
          <button class="secondary-button" @click="clearSelections">Clear Selections</button>
          <button class="secondary-button" @click="applyDefaults">Apply Defaults</button>
          <button class="primary" @click="applySelections">Apply Selections</button>
        </div>
      </div>

      <div class="trait-mode-toggle">
        <button :class="{ active: traitMode === 'prioritize' }" title="Move candidates matching selected traits higher without hiding others" @click="traitMode = 'prioritize'">Prioritize</button>
        <button :class="{ active: traitMode === 'hide' }" title="Hide candidates that do not match selected traits" @click="traitMode = 'hide'">Hide mismatches</button>
      </div>
      <div class="default-trait-summary">
        <button type="button" class="default-trait-summary-button" :aria-expanded="defaultsExpanded" @click="defaultsExpanded = !defaultsExpanded">Archie defaults · {{ defaultTraitCount }} traits <span>{{ defaultsExpanded ? 'Hide defaults' : 'Show defaults' }}</span></button>
        <div v-if="defaultsExpanded" class="default-trait-strip"><span v-for="item in selectedDraftTraits" :key="item" class="default-trait-chip">{{ item }}</span></div>
      </div>

      <FilterSection title="Area & Date" :open="filterSectionOpen.area" :summary="filterSummaries.area" @toggle="filterSectionOpen.area = !filterSectionOpen.area">
        <div class="filter-grid">
          <label>Distance<select v-model.number="maxDistance"><option :value="10">10 miles</option><option :value="25">25 miles</option><option :value="50">50 miles</option><option :value="100">100 miles</option><option :value="500">Any distance</option></select></label>
          <label>Report age<select v-model.number="ageDays"><option :value="0">Any age</option><option :value="1">Past 24 hours</option><option :value="3">Past 3 days</option><option :value="7">Past 7 days</option><option :value="14">Past 2 weeks</option><option :value="30">Past 30 days</option><option :value="60">Past 60 days</option></select></label>
          <label>On or after:<input class="date-input" type="date" v-model="notBefore" /></label>
          <label>Source<select v-model="source"><option value="">All sources</option><option v-for="item in sourceOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
          <label>Facebook group<select v-model="facebookGroupId"><option value="">All Facebook groups</option><option v-for="group in filterOptions.facebook_groups || []" :key="group.id" :value="String(group.id)">{{ group.group_name }}{{ group.enabled ? '' : ' · disabled' }}</option></select></label>
          <label>Status<select v-model="status"><option value="">All statuses</option><option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        </div>
      </FilterSection>

      <FilterSection title="Appearance" :open="filterSectionOpen.appearance" :summary="filterSummaries.appearance" @toggle="filterSectionOpen.appearance = !filterSectionOpen.appearance">
        <div class="filter-grid grouped-filters">
          <label :class="{ defaulted: isDefaultDraft('sex', sex) }">Sex<select v-model="sex"><option value="">Any / unknown</option><option value="male">Male</option><option value="female">Female</option><option value="unknown">Unknown only</option></select></label>
          <label :class="{ defaulted: isDefaultDraft('color', color) }">Color<select v-model="color"><option value="">Any color</option><option value="orange">Orange / ginger</option><option value="black">Black</option><option value="gray">Gray / blue</option><option value="white">White</option><option value="brown">Brown</option><option value="cream">Cream / buff</option><option value="calico">Calico</option><option value="tortoiseshell">Tortoiseshell</option></select></label>
          <label :class="{ defaulted: isDefaultDraft('pattern', pattern) }">Pattern<select v-model="pattern"><option value="">Any pattern</option><option value="striped">Striped / tabby</option><option value="solid">Solid</option><option value="tuxedo">Tuxedo</option><option value="spotted">Spotted</option></select></label>
          <label :class="{ defaulted: isDefaultDraft('coat', coat) }">Coat<select v-model="coat"><option value="">Any coat</option><option value="short">Short hair</option><option value="medium">Medium hair</option><option value="long">Long hair</option></select></label>
          <label :class="{ defaulted: isDefaultDraft('altered', altered) }">Altered<select v-model="altered"><option value="">Any / unknown</option><option value="neutered">Neutered</option><option value="intact">Intact</option><option value="spayed">Spayed</option></select></label>
        </div>
      </FilterSection>

      <FilterSection title="Markings" :open="filterSectionOpen.markings" :summary="filterSummaries.markings" :badge-count="[whiteChest, whiteBelly, whitePaws, whiteFace].filter(v => v !== 'any').length" @toggle="filterSectionOpen.markings = !filterSectionOpen.markings">
        <div class="filter-grid grouped-filters">
          <label :class="{ defaulted: isDefaultDraft('whiteChest', whiteChest) }">White chest<select v-model="whiteChest"><option value="any">Any / unknown</option><option value="yes">White chest stated</option><option value="no">No white chest stated</option></select></label>
          <label>White belly<select v-model="whiteBelly"><option value="any">Any / unknown</option><option value="yes">White belly stated</option><option value="no">No white belly stated</option></select></label>
          <label>White paws / feet<select v-model="whitePaws"><option value="any">Any / unknown</option><option value="yes">White paws stated</option><option value="no">No white paws stated</option></select></label>
          <label>White face / muzzle<select v-model="whiteFace"><option value="any">Any / unknown</option><option value="yes">White face stated</option><option value="no">No white face stated</option></select></label>
        </div>
      </FilterSection>

      <FilterSection title="Identification" :open="filterSectionOpen.identification" :summary="filterSummaries.identification" :badge-count="[collar, microchip].filter(Boolean).length + Number(ageCompatible) + Number(archieCompatible) + Number(photoFilter !== 'any')" @toggle="filterSectionOpen.identification = !filterSectionOpen.identification">
        <div class="filter-grid grouped-filters">
          <label :class="{ defaulted: isDefaultDraft('collar', collar) }">Collar<select v-model="collar"><option value="">Any / unknown</option><option value="none">No collar</option><option value="wearing">Wearing collar</option></select></label>
          <label :class="{ defaulted: isDefaultDraft('microchip', microchip) }">Microchip<select v-model="microchip"><option value="">Any / unknown</option><option value="none">Not microchipped</option><option value="yes">Microchipped</option></select></label>
          <label class="checkbox-label"><input type="checkbox" v-model="ageCompatible" /> Age ~8 (explicit only)</label>
          <label class="checkbox-label"><input type="checkbox" v-model="archieCompatible" /> Archie-compatible only</label>
          <label>Photo<select v-model="photoFilter"><option value="any">With or without photo</option><option value="with">Has photo</option><option value="without">No photo</option></select></label>
        </div>
      </FilterSection>

      <FilterSection title="Queue Behavior" :open="filterSectionOpen.queue" :summary="filterSummaries.queue" :badge-count="Number(minScore !== 0) + Number(hideDuplicates !== DEFAULT_FILTERS.hideDuplicates)" @toggle="filterSectionOpen.queue = !filterSectionOpen.queue">
        <div class="filter-grid">
          <label>Match-signal floor<select v-model.number="minScore"><option :value="0">Show all</option><option :value="40">40+</option><option :value="55">55+</option><option :value="65">65+</option><option :value="75">75+</option></select></label>
          <label class="checkbox-label"><input type="checkbox" v-model="hideDuplicates" /> Hide confirmed image reposts</label>
        </div>
      </FilterSection>
    </section>

    <section v-if="setupOpen" class="setup-panel">
      <div class="setup-copy"><div><p class="eyebrow">ARCHIE PROFILE</p><h2>The traits Radar is looking for</h2><p v-if="searchConfig?.archie_profile_summary?.description">{{ searchConfig.archie_profile_summary.description }}</p><div class="profile-traits"><span>orange</span><span>striped / tabby</span><span>short hair</span><span>white chest</span><span>male</span><span>neutered</span><span>~8 years</span><span>no collar</span><span>not microchipped</span><span>missing late June 2026</span></div><p class="photo-explainer"><strong>Photos:</strong> reference photos add a visual-likeness signal. They help most with reused or very similar photos and do not confirm identity by themselves.</p></div><label class="upload-button">{{ uploading ? 'Analyzing…' : '+ Add Archie photo' }}<input type="file" accept="image/jpeg,image/png,image/webp" @change="uploadReference" :disabled="uploading" /></label></div>
      <div v-if="referencePhotos.length" class="reference-strip"><figure v-for="photo in referencePhotos" :key="photo.id" class="reference-photo"><img :src="`${API}${photo.media_url}`" :alt="photo.label" /><button title="Remove reference" @click="deleteReference(photo)">×</button></figure></div>
      <div v-if="searchConfig" class="setup-meta"><span><strong>Home:</strong> {{ searchConfig.home_address }}</span><span><strong>Default review radius:</strong> 25 mi</span></div>
    </section>

    <section v-if="sourcesOpen" class="sources-panel">
      <div class="panel-heading"><div><p class="eyebrow">SOURCE COVERAGE</p><h2>Where Radar is looking</h2></div><span>{{ activeSourceCount }} active</span></div>
      <div class="source-status-grid">
        <article v-for="item in searchConfig?.source_statuses || []" :key="item.key" :class="['source-status-card', item.status, `source-${item.key}`]">
          <div class="source-card-top"><div><strong>{{ item.label }}</strong><span>{{ item.status.replaceAll('_', ' ') }}</span></div><button v-if="['pawboost','orange_county','regional_24petconnect','aps_durham','wake_county','pet911','petkey'].includes(item.key)" class="inline-button source-refresh" @click="refreshSource(item.key)" :disabled="refreshBusy[item.key]">{{ refreshBusy[item.key] ? 'Refreshing…' : 'Refresh' }}</button></div>
          <p v-if="item.detail">{{ item.detail }}</p><small v-if="refreshReceipt[item.key] && !refreshReceipt[item.key]?.error">{{ refreshReceipt[item.key].total ?? 0 }} seen · {{ refreshReceipt[item.key].created ?? 0 }} new</small>
        </article>
      </div>
      <FacebookGroupsPanel :api="API" @updated="loadFilterOptions" @review-new="setQueue('new')" />
      <details v-if="scanSummary" class="scan-summary"><summary>Last scan receipt</summary><div class="scan-grid"><div v-for="(result, name) in scanSummary" :key="name" :class="['scan-source', { failed: result?.error }]"><strong>{{ name.replaceAll('_', ' ') }}</strong><span v-if="result?.error">error</span><span v-else>{{ result?.total ?? 0 }} seen · {{ result?.created ?? 0 }} new</span></div></div></details>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
    <SearchMap v-if="showMap" :posts="posts" :config="searchConfig" :review-radius="appliedFilters.maxDistance" />

    <div class="results-heading"><div><p class="eyebrow">REVIEW QUEUE</p><h2>{{ posts.length }} {{ state === 'new' ? 'new candidates' : 'candidates' }}</h2></div><div class="results-meta"><span v-if="mappedCount">{{ mappedCount }} on map</span><span v-if="loading">Updating…</span></div></div>
    <p v-if="!loading && !posts.length" class="empty">Nothing in this view. Widen a filter or run a fresh scan.</p>
    <section class="candidate-list"><CandidateCard v-for="(post, index) in posts" :id="`post-${post.id}`" :key="post.id" :post="post" :rank="index + 1" @review="review" @locate="locateCandidate" /></section>
  </main>
</template>
