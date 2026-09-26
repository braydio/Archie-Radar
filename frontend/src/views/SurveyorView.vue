<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { TerraDraw, TerraDrawLineStringMode, TerraDrawPolygonMode, TerraDrawSelectMode } from 'terra-draw'
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter'
import { applyCatMapStyle } from '../surveyor/catMapStyle.js'
import { PIN_TYPES } from '../surveyor/objectTypes.js'
import { useRoute } from 'vue-router'
import { createMapFeatureSnapper } from '../surveyor/snapEngine.js'
import SurveyTimeline from '../components/surveyor/SurveyTimeline.vue'
import LayerDrawer from '../components/surveyor/LayerDrawer.vue'
import DraftObjectSheet from '../components/surveyor/DraftObjectSheet.vue'
import SearchResultSheet from '../components/surveyor/SearchResultSheet.vue'
import CandidateClusterSheet from '../components/surveyor/CandidateClusterSheet.vue'
import MobileInspectorSheet from '../components/surveyor/MobileInspectorSheet.vue'
import SurveyorToolbar from '../components/surveyor/SurveyorToolbar.vue'
import SearchSessionBar from '../components/surveyor/SearchSessionBar.vue'
import CandidateInspector from '../components/surveyor/CandidateInspector.vue'
import ObjectInspector from '../components/surveyor/ObjectInspector.vue'
import AudioRecorder from '../components/surveyor/AudioRecorder.vue'
import PhotoCapture from '../components/surveyor/PhotoCapture.vue'
import AccessEditor from '../components/surveyor/AccessEditor.vue'
import { cameraConePolygon, cameraHandlePoints } from '../surveyor/cameraGeometry.js'
import { searchFreshness } from '../surveyor/zoneState.js'
import { registerSurveyorIcons } from '../surveyor/iconRegistry.js'

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const route = useRoute()
const timelineWindow = ref({ preset: '30d', from: new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 16), to: new Date().toISOString().slice(0, 16) })
const LAYER_STORAGE = 'archie-radar-surveyor-layers'
const SNAP_STORAGE = 'archie-radar-surveyor-snap'
const defaultLayers = { objects: true, links: true, cameras: true, cameraHistory: false, candidates: true, landcover: false }
const layerSettings = ref((() => { try { return { ...defaultLayers, ...JSON.parse(localStorage.getItem(LAYER_STORAGE) || '{}') } } catch { return { ...defaultLayers } } })())
const layerDrawerOpen = ref(false)
const mobileMoreOpen = ref(false)
const mapEl = ref(null)
const objects = ref([])
const candidates = ref([])
const cameras = ref([])
const links = ref([])
const linkStartId = ref(null)
const linkType = ref('association')
const attachments = ref([])
const tasks = ref([])
const draftObject = ref(null)
const accessDraftCoordinates = ref(null)
const draftDrawId = ref(null)
const searchResultOpen = ref(false)
const attachmentCaption = ref('')
const uploadingAttachment = ref(false)
const activeSession = ref(null)
const sessionMethod = ref('walking')
const trackCoords = ref([])
const trackTimes = ref([])
const locationWarning = ref('')
const selected = ref(null)
const selectedCandidate = ref(null)
const selectedHistoricalPlacement = ref(null)
const candidateCluster = ref(null)
const candidatesVisible = ref(true)
const cameraHistoryVisible = ref(false)
const activeTool = ref('select')
const editingGeometryId = ref(null)
const loading = ref(true)
const error = ref('')
const title = ref('')
const subtype = ref('sighting')
const zoneSubtype = ref('needs_search')
const cameraHeading = ref(0)
const cameraFov = ref(62)
const cameraRange = ref(15)
const snapSettings = ref((() => { try { return { roads: true, trails: true, waterways: true, objects: true, zoneBoundaries: true, cameras: true, ...JSON.parse(localStorage.getItem(SNAP_STORAGE) || '{}') } } catch { return { roads: true, trails: true, waterways: true, objects: true, zoneBoundaries: true, cameras: true } } })())
const snapMenuOpen = ref(false)
const snapTarget = ref(null)
const notes = ref('')
const saving = ref(false)
const coveragePreview = ref(null)
let map
let draw
let resizeObserver
let geoWatchId = null
let checkpointBusy = false
let cameraHandleDrag = null
let screenWakeLock = null

const types = PIN_TYPES
watch(snapSettings, settings => { try { localStorage.setItem(SNAP_STORAGE, JSON.stringify(settings)) } catch {} }, { deep: true })
watch(layerSettings, settings => {
  try { localStorage.setItem(LAYER_STORAGE, JSON.stringify(settings)) } catch {}
  candidatesVisible.value = settings.candidates
  cameraHistoryVisible.value = settings.cameraHistory
  for (const layer of ['surveyor-zones-fill', 'surveyor-zones-outline', 'surveyor-lines', 'surveyor-points', 'surveyor-icons', 'surveyor-labels']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.objects ? 'visible' : 'none')
  }
  for (const layer of ['surveyor-links-line', 'surveyor-links-labels', 'surveyor-links-arrows']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.links ? 'visible' : 'none')
  }
  for (const layer of ['camera-cones-fill', 'camera-cones-outline', 'trail-camera-points']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.cameras ? 'visible' : 'none')
  }
  for (const layer of ['trail-camera-history-points']) if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.cameras && settings.cameraHistory ? 'visible' : 'none')
  if (map?.getLayer('annual-landcover')) map.setLayoutProperty('annual-landcover', 'visibility', settings.landcover ? 'visible' : 'none')
  refreshCameraSource()
}, { deep: true })
watch(() => selected.value?.id, id => { attachments.value = []; tasks.value = []; refreshCameraSource(); if (id) { loadAttachments(id); loadTasks(id) } })
function inTimeline(value) {
  if (timelineWindow.value.preset === 'all' || !value) return true
  const time = new Date(value).getTime()
  return time >= new Date(timelineWindow.value.from).getTime() && time <= new Date(timelineWindow.value.to).getTime()
}
const featureCollection = computed(() => ({
  type: 'FeatureCollection',
  features: objects.value.filter(object => object.id !== editingGeometryId.value && inTimeline(object.occurred_at || object.valid_from || object.created_at)).map(object => ({
    type: 'Feature', id: object.id, geometry: object.geometry,
    properties: { id: object.id, name: object.name || object.subtype || object.object_type, subtype: object.subtype || '', object_type: object.object_type,
      epistemic_state: object.epistemic_state || 'observed', confidence: object.confidence || 'possible', status: object.status || '', search_freshness: searchFreshness(object),
      color: types.find(item => item.value === object.subtype)?.color || '#bf704d', icon: object.object_type === 'trail_camera' ? 'trail-camera' : object.object_type === 'note' ? 'note' : (types.find(item => item.value === object.subtype)?.icon || 'sighting') }
  }))
}))

async function loadObjects() {
  try {
    const response = await fetch(`${API}/api/surveyor/objects`)
    if (!response.ok) throw new Error(`Survey data unavailable (${response.status})`)
    objects.value = await response.json()
    error.value = ''
    refreshSource()
    const focusId = Number(route.query.object)
    const focusObject = objects.value.find(object => object.id === focusId)
    if (focusObject) {
      selected.value = focusObject; title.value = focusObject.name || ''; subtype.value = focusObject.subtype || ''; notes.value = focusObject.notes || ''
      const center = focusObject.geometry.type === 'Point' ? focusObject.geometry.coordinates : [focusObject.centroid_lon, focusObject.centroid_lat]
      map?.flyTo({ center, zoom: Math.max(map.getZoom(), 14) })
    }
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
  loadCandidates()
  loadCameras()
  loadLinks()
  loadActiveSession()
}

async function loadCameras() {
  try {
    const response = await fetch(`${API}/api/surveyor/cameras`)
    if (!response.ok) return
    cameras.value = await response.json(); refreshCameraSource()
  } catch { /* Camera overlays can fail independently from the base map. */ }
}

function cameraGeoJSON() {
  const features = [], historyPoints = []
  for (const camera of cameras.value) {
    const overlapping = camera.history.filter(placement => timelineWindow.value.preset === 'all' || (
      new Date(placement.installed_at) <= new Date(timelineWindow.value.to) &&
      (!placement.removed_at || new Date(placement.removed_at) >= new Date(timelineWindow.value.from))))
    const placements = cameraHistoryVisible.value ? overlapping : overlapping.filter(placement =>
      !placement.removed_at || new Date(placement.removed_at) >= new Date(timelineWindow.value.to)).slice(0, 1)
    for (const placement of placements) {
      const current = !placement.removed_at
      const historyIndex = current ? 0 : overlapping.filter(item => item.removed_at && new Date(item.installed_at) > new Date(placement.installed_at)).length + 1
      const historyAgeDays = Math.max(0, (Date.now() - new Date(placement.installed_at).getTime()) / 86400000)
      const opacity = current ? 1 : Math.max(0.15, 0.38 - (historyIndex - 1) * 0.08)
      const properties = { camera_id: camera.id, name: camera.name, current, history_index: historyIndex, history_age_days: historyAgeDays,
        opacity, installed_at: placement.installed_at, removed_at: placement.removed_at || '', heading_degrees: placement.heading_degrees,
        fov_degrees: placement.fov_degrees, range_meters: placement.range_meters }
      features.push({ type: 'Feature', properties, geometry: cameraConePolygon(placement) })
      if (!current) historyPoints.push({ type: 'Feature', properties, geometry: { type: 'Point', coordinates: [Number(placement.longitude), Number(placement.latitude)] } })
    }
  }
  const camera = cameras.value.find(item => item.map_object_id === selected.value?.id)
  const handles = camera?.placement ? cameraHandlePoints(camera.placement) : null
  const handleFeatures = handles ? Object.entries(handles).map(([kind, coordinates]) => ({ type: 'Feature', properties: { handle: kind, camera_id: camera.id }, geometry: { type: 'Point', coordinates } })) : []
  map?.getSource('camera-history-points')?.setData({ type: 'FeatureCollection', features: historyPoints })
  map?.getSource('selected-camera-handles')?.setData({ type: 'FeatureCollection', features: handleFeatures })
  return { type: 'FeatureCollection', features }
}

function refreshCameraSource() { map?.getSource('camera-cones')?.setData(cameraGeoJSON()) }
function bearingFrom(center, point) {
  const rad = value => value * Math.PI / 180
  const lat1 = rad(center[1]), lat2 = rad(point[1]), delta = rad(point[0] - center[0])
  return (Math.atan2(Math.sin(delta) * Math.cos(lat2), Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(delta)) * 180 / Math.PI + 360) % 360
}
function previewCamera(cameraId, updates) {
  const camera = cameras.value.find(item => item.id === cameraId)
  if (!camera?.placement) return
  cameras.value = cameras.value.map(item => item.id === cameraId ? { ...item, placement: { ...item.placement, ...updates } } : item)
  const object = objects.value.find(item => item.id === camera.map_object_id)
  if (object && ('latitude' in updates || 'longitude' in updates)) {
    const lon = updates.longitude ?? object.geometry.coordinates[0], lat = updates.latitude ?? object.geometry.coordinates[1]
    const next = { ...object, geometry: { type: 'Point', coordinates: [lon, lat] }, centroid_lon: lon, centroid_lat: lat, bbox: [lon, lat, lon, lat] }
    objects.value = objects.value.map(item => item.id === next.id ? next : item)
    if (selected.value?.id === next.id) selected.value = next
    refreshSource()
  }
  refreshCameraSource()
}
function beginCameraHandleDrag(event) {
  const feature = event.features?.[0]
  if (!feature) return
  const camera = cameras.value.find(item => item.id === Number(feature.properties.camera_id))
  if (!camera?.placement) return
  event.preventDefault()
  cameraHandleDrag = { cameraId: camera.id, handle: feature.properties.handle, original: { ...camera.placement }, latest: {}, moved: false }
  map.dragPan.disable(); map.on('mousemove', moveCameraHandle); map.on('touchmove', moveCameraHandle)
  map.on('mouseup', endCameraHandleDrag); map.on('touchend', endCameraHandleDrag)
  map.getCanvas().style.cursor = 'grabbing'
}
function moveCameraHandle(event) {
  if (!cameraHandleDrag) return
  const drag = cameraHandleDrag, point = [event.lngLat.lng, event.lngLat.lat], center = [drag.original.longitude, drag.original.latitude]
  let update
  if (drag.handle === 'center') update = { latitude: point[1], longitude: point[0] }
  else if (drag.handle === 'heading') update = { heading_degrees: bearingFrom(center, point) }
  else if (drag.handle === 'range') update = { range_meters: Math.max(1, Math.min(5000, distanceBetween(center, point))) }
  else { const angle = bearingFrom(center, point), delta = ((angle - Number(drag.original.heading_degrees) + 540) % 360) - 180
    update = { fov_degrees: Math.max(1, Math.min(179, Math.round(Math.abs(delta) * 2))) }
  }
  drag.latest = update; drag.moved = true; previewCamera(drag.cameraId, update)
}
async function endCameraHandleDrag() {
  const drag = cameraHandleDrag; cameraHandleDrag = null
  map.dragPan.enable(); map.off('mousemove', moveCameraHandle); map.off('touchmove', moveCameraHandle)
  map.off('mouseup', endCameraHandleDrag); map.off('touchend', endCameraHandleDrag); map.getCanvas().style.cursor = ''
  if (!drag?.moved) return
  try {
    const response = await fetch(`${API}/api/surveyor/cameras/${drag.cameraId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(drag.latest) })
    if (!response.ok) throw new Error('Could not save camera adjustment')
    const updated = await response.json(); cameras.value = cameras.value.map(item => item.id === updated.id ? updated : item)
    const objectResponse = await fetch(`${API}/api/surveyor/objects/${updated.map_object_id}`)
    if (objectResponse.ok) { const object = await objectResponse.json(); objects.value = objects.value.map(item => item.id === object.id ? object : item); selected.value = object }
    refreshCameraSource(); refreshSource()
  } catch (err) { error.value = err.message; await loadCameras(); await loadObjects() }
}
watch(timelineWindow, () => { refreshSource(); refreshCandidates(); refreshCameraSource() }, { deep: true })

function trackCollection() {
  return { type: 'FeatureCollection', features: trackCoords.value.length >= 2 ? [{ type: 'Feature', properties: {},
    geometry: { type: 'LineString', coordinates: trackCoords.value } }] : [] }
}

function refreshTrack() { map?.getSource('active-search-track')?.setData(trackCollection()) }
function setCoveragePreview(geometry) {
  coveragePreview.value = geometry
  map?.getSource('search-coverage-preview')?.setData({ type: 'FeatureCollection', features: geometry ? [{ type: 'Feature', properties: {}, geometry }] : [] })
}

function distanceBetween(a, b) {
  const rad = value => value * Math.PI / 180
  const dLat = rad(b[1] - a[1]), dLon = rad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * 6371008.8 * Math.asin(Math.sqrt(h))
}

function sessionDistance() {
  return trackCoords.value.slice(1).reduce((sum, coordinate, index) => sum + distanceBetween(trackCoords.value[index], coordinate), 0)
}

async function saveSessionCheckpoint() {
  if (!activeSession.value || trackCoords.value.length < 2 || checkpointBusy) return
  checkpointBusy = true
  try {
    await fetch(`${API}/api/surveyor/sessions/${activeSession.value.id}/checkpoint`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_geojson: { type: 'LineString', coordinates: trackCoords.value }, distance_meters: sessionDistance() }) })
  } finally { checkpointBusy = false }
}

function beginLocationWatch() {
  if (!navigator.geolocation || geoWatchId != null) return
  geoWatchId = navigator.geolocation.watchPosition(position => {
    const coordinate = [position.coords.longitude, position.coords.latitude]
    const previous = trackCoords.value.at(-1)
    const now = position.timestamp || Date.now(), previousTime = trackTimes.value.at(-1)
    if (position.coords.accuracy > 60) return
    if (previous && previousTime && distanceBetween(previous, coordinate) / Math.max(0.001, (now - previousTime) / 1000) > 45) return
    if (!previous || distanceBetween(previous, coordinate) > 2) {
      trackCoords.value.push(coordinate); trackTimes.value.push(now); locationWarning.value = ''; refreshTrack()
      if (trackCoords.value.length % 5 === 0) saveSessionCheckpoint()
    }
  }, () => { locationWarning.value = 'Location tracking is unavailable. The search session is still active.' }, { enableHighAccuracy: true, maximumAge: 5000 })
}

async function loadActiveSession() {
  try {
    const response = await fetch(`${API}/api/surveyor/sessions`)
    if (!response.ok) return
    const sessions = await response.json()
    const requestedId = Number(route.query.session)
    const session = sessions.find(item => item.id === requestedId) || sessions.find(item => !item.ended_at)
    if (!session) return
    if (!session.ended_at) { activeSession.value = session; requestScreenWakeLock() }
    trackCoords.value = session.track_geojson?.type === 'LineString' ? session.track_geojson.coordinates : []
    trackTimes.value = trackCoords.value.map(() => null)
    refreshTrack()
    if (trackCoords.value.length) map?.flyTo({ center: trackCoords.value.at(-1), zoom: Math.max(map.getZoom(), 14) })
    if (!session.ended_at) beginLocationWatch()
  } catch { /* Running field work will still load if the session service is unavailable. */ }
}

async function startSearch() {
  const response = await fetch(`${API}/api/surveyor/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method: sessionMethod.value }) })
  if (!response.ok) { error.value = 'Could not start search session'; return }
  activeSession.value = await response.json(); trackCoords.value = []; trackTimes.value = []; locationWarning.value = ''; refreshTrack()
  requestScreenWakeLock()
  beginLocationWatch()
}

async function requestScreenWakeLock() {
  if (!activeSession.value || !navigator.wakeLock?.request || (screenWakeLock && !screenWakeLock.released)) return
  try { screenWakeLock = await navigator.wakeLock.request('screen') } catch { /* Wake lock is an optional field-use convenience. */ }
}

async function releaseScreenWakeLock() {
  try { await screenWakeLock?.release() } catch { /* Ignore an already released lock. */ }
  screenWakeLock = null
}

async function endSearch() {
  if (!activeSession.value) return
  searchResultOpen.value = true
}

async function finishSearch(result) {
  if (!activeSession.value) return
  const sessionId = activeSession.value.id
  const response = await fetch(`${API}/api/surveyor/sessions/${sessionId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_geojson: trackCoords.value.length >= 2 ? { type: 'LineString', coordinates: trackCoords.value } : null,
      distance_meters: sessionDistance(), result_summary: result.result_summary, notes: [result.outcome, result.notes].filter(Boolean).join(' · ') }) })
  if (!response.ok) { error.value = 'Could not finish search session'; return }
  if (result.create_coverage) {
    try {
      const coverageResponse = await fetch(`${API}/api/surveyor/sessions/${sessionId}/coverage`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buffer_meters: result.buffer_meters, name: 'Searched route', notes: result.notes || '' }) })
      const coverageBody = await coverageResponse.json().catch(() => ({}))
      if (!coverageResponse.ok) throw new Error(coverageBody.detail || 'Could not create searched coverage')
      objects.value.unshift(coverageBody); refreshSource()
    } catch (err) { error.value = `Search saved, but coverage was not created: ${err.message}` }
  }
  if (geoWatchId != null) navigator.geolocation?.clearWatch(geoWatchId)
  geoWatchId = null; activeSession.value = null; searchResultOpen.value = false; setCoveragePreview(null); releaseScreenWakeLock()
}

async function loadCandidates() {
  try {
    const response = await fetch(`${API}/api/posts?limit=2000&sort=newest&max_distance_miles=500`)
    if (!response.ok) return
    candidates.value = (await response.json()).filter(post => post.map_latitude != null && post.map_longitude != null)
    refreshCandidates()
  } catch { /* Candidate reports remain an optional layer. */ }
}

function candidateCollection() {
  return { type: 'FeatureCollection', features: candidates.value.filter(post => inTimeline(post.reported_at || post.posted_at || post.first_seen_at)).map(post => ({
    type: 'Feature', id: post.id, properties: { id: post.id, title: post.name || 'Candidate report', source: post.source,
      source_id: post.source_id, source_url: post.source_url || '', reported_at: post.reported_at || '', posted_at: post.posted_at || '',
      first_seen_at: post.first_seen_at || '', location_text: post.location_text || '', match_score: post.match_score ?? 0,
      distance_from_home_miles: post.distance_from_home_miles ?? null, location_precision: post.location_precision || '', image_url: post.image_url || '' },
    geometry: { type: 'Point', coordinates: [Number(post.map_longitude), Number(post.map_latitude)] }
  })) }
}

function refreshCandidates() {
  const source = map?.getSource('candidate-reports')
  if (source) source.setData(candidateCollection())
  for (const layer of ['candidate-reports-point', 'candidate-reports-cluster', 'candidate-reports-cluster-count']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', candidatesVisible.value ? 'visible' : 'none')
  }
}

function refreshSource() {
  const source = map?.getSource('surveyor-objects')
  if (source) source.setData(featureCollection.value)
  refreshLinks()
}

async function loadLinks() {
  try {
    const response = await fetch(`${API}/api/surveyor/links`)
    if (!response.ok) return
    links.value = await response.json(); refreshLinks()
  } catch { /* Link overlay is optional while the rest of Surveyor loads. */ }
}

function linkCollection() {
  const features = []
  for (const link of links.value) {
    const source = objects.value.find(item => item.id === link.source_object_id)
    const target = objects.value.find(item => item.id === link.target_object_id)
    if (!source || !target) continue
    if (!inTimeline(source.occurred_at || source.valid_from || source.created_at) || !inTimeline(target.occurred_at || target.valid_from || target.created_at)) continue
    const middle = link.geometry.coordinates.slice(1, -1)
    features.push({ type: 'Feature', id: link.id, properties: { id: link.id, link_type: link.link_type,
      line_style: link.line_style, label: link.label }, geometry: { type: 'LineString', coordinates: [
      [source.centroid_lon, source.centroid_lat], ...middle, [target.centroid_lon, target.centroid_lat]
    ] } })
  }
  return { type: 'FeatureCollection', features }
}

function refreshLinks() { map?.getSource('surveyor-links')?.setData(linkCollection()) }

async function createLink(targetId) {
  if (linkStartId.value == null) { linkStartId.value = targetId; return }
  if (linkStartId.value === targetId) { linkStartId.value = null; return }
  const style = { observed_movement: 'solid', hypothesized_movement: 'dashed', possible_corridor: 'double_arrow', association: 'dotted', evidence_for: 'solid', evidence_against: 'dashed', custom: 'dotted' }[linkType.value]
  const response = await fetch(`${API}/api/surveyor/links`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_object_id: linkStartId.value, target_object_id: targetId, link_type: linkType.value, line_style: style }) })
  if (!response.ok) throw new Error((await response.json()).detail || 'Could not link map objects')
  links.value.unshift(await response.json()); linkStartId.value = null; refreshLinks(); activeTool.value = 'select'
}

async function createPin(coordinates) {
  draftObject.value = { kind: 'pin', geometry: { type: 'Point', coordinates }, subtype: subtype.value }
}

async function accessSaved(record) {
  accessDraftCoordinates.value = null
  const response = await fetch(`${API}/api/surveyor/objects/${record.map_object_id}`)
  if (!response.ok) throw new Error('Access record was saved but its map marker could not be loaded')
  const object = await response.json(); objects.value.unshift(object); refreshSource(); selected.value = object
  title.value = object.name || ''; subtype.value = object.subtype || ''; notes.value = object.notes || ''; activeTool.value = 'select'
}

async function createCamera(coordinates) {
  draftObject.value = { kind: 'camera', geometry: { type: 'Point', coordinates } }
}

function createNote(coordinates) {
  draftObject.value = { kind: 'note', geometry: { type: 'Point', coordinates }, subtype: 'field_note' }
}

async function saveDraft(payload) {
  if (payload.kind === 'camera') {
  const response = await fetch(`${API}/api/surveyor/cameras`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: payload.name || 'Trail camera', longitude: payload.geometry.coordinates[0], latitude: payload.geometry.coordinates[1],
      heading_degrees: payload.heading_degrees, fov_degrees: payload.fov_degrees, range_meters: payload.range_meters,
      camera_model: payload.camera_model, power_type: payload.power_type, notes: payload.notes }) })
  if (!response.ok) throw new Error('Could not save trail camera')
  const camera = await response.json(); cameras.value.unshift(camera)
  const objectResponse = await fetch(`${API}/api/surveyor/objects/${camera.map_object_id}`)
  if (!objectResponse.ok) throw new Error('Camera was saved but its map object could not be loaded')
  const object = await objectResponse.json(); objects.value.unshift(object); refreshSource(); refreshCameraSource()
  selected.value = object; selectedCandidate.value = null; title.value = object.name; subtype.value = 'camera'; notes.value = object.notes
  cameraHeading.value = camera.placement.heading_degrees; cameraFov.value = camera.placement.fov_degrees; cameraRange.value = camera.placement.range_meters
  } else {
    const isZone = payload.kind === 'zone', isLine = payload.kind === 'line'
    const properties = activeSession.value ? { search_session_id: activeSession.value.id } : {}
    if (isZone && payload.subtype === 'searched') Object.assign(properties, { searched_at: new Date().toISOString(), search_session_id: activeSession.value?.id || null, search_method: activeSession.value?.method || null })
    const response = await fetch(`${API}/api/surveyor/objects`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ object_type: isZone ? 'zone' : isLine ? 'corridor' : payload.kind === 'note' ? 'note' : 'pin',
        subtype: payload.subtype || (payload.kind === 'note' ? 'field_note' : null), name: payload.name || (payload.kind === 'note' ? 'Field note' : null),
        geometry: payload.geometry, notes: payload.notes || '', occurred_at: payload.occurred_at,
        epistemic_state: payload.epistemic_state, confidence: payload.confidence, properties,
        status: isZone ? payload.subtype : null }) })
    if (!response.ok) throw new Error((await response.json()).detail || 'Could not save map object')
    const object = await response.json(); objects.value.unshift(object); refreshSource(); selected.value = object
    title.value = object.name || ''; subtype.value = object.subtype || ''; notes.value = object.notes || ''
  }
  if (draftDrawId.value != null) draw?.removeFeatures([draftDrawId.value])
  draftObject.value = null; draftDrawId.value = null; activeTool.value = 'select'; draw?.setMode('select'); refreshSource(); refreshCameraSource()
}

function cancelDraft() {
  if (draftDrawId.value != null) draw?.removeFeatures([draftDrawId.value])
  draftObject.value = null; draftDrawId.value = null; activeTool.value = 'select'; draw?.setMode('select')
}

async function moveSelectedCamera(coordinates) {
  if (!selected.value || selected.value.object_type !== 'trail_camera') return
  const camera = cameras.value.find(item => item.map_object_id === selected.value.id)
  if (!camera) return
  const response = await fetch(`${API}/api/surveyor/cameras/${camera.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitude: coordinates[1], longitude: coordinates[0] }) })
  if (!response.ok) throw new Error('Could not move camera')
  const updated = await response.json(); cameras.value = cameras.value.map(item => item.id === updated.id ? updated : item)
  const objectResponse = await fetch(`${API}/api/surveyor/objects/${updated.map_object_id}`)
  const canonical = await objectResponse.json(); objects.value = objects.value.map(item => item.id === canonical.id ? canonical : item)
  selected.value = canonical; activeTool.value = 'select'; refreshSource(); refreshCameraSource()
}

async function moveSelectedObject(coordinates) {
  if (!selected.value) return
  const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ geometry: { type: 'Point', coordinates } }) })
  if (!response.ok) throw new Error('Could not move map object')
  const canonical = await response.json()
  objects.value = objects.value.map(item => item.id === canonical.id ? canonical : item)
  selected.value = canonical; activeTool.value = 'select'; refreshSource()
}

function beginGeometryEdit() {
  if (!selected.value || !['Polygon', 'LineString'].includes(selected.value.geometry.type)) return
  const object = selected.value, id = object.id
  const mode = object.geometry.type === 'Polygon' ? 'polygon' : 'linestring'
  draw.addFeatures([{ type: 'Feature', id, geometry: object.geometry, properties: { mode, surveyor_object_id: id } }])
  editingGeometryId.value = id; activeTool.value = 'edit'; draw.setMode('select'); draw.selectFeature(id); refreshSource()
}

async function finishGeometryEdit(save) {
  const id = editingGeometryId.value
  if (id == null) return
  const feature = draw.getSnapshotFeature(id)
  if (save && feature?.geometry) {
    const response = await fetch(`${API}/api/surveyor/objects/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ geometry: feature.geometry }) })
    if (!response.ok) { error.value = 'Could not save edited geometry'; return }
    const canonical = await response.json()
    objects.value = objects.value.map(item => item.id === canonical.id ? canonical : item); selected.value = canonical
  }
  draw.removeFeatures([id]); editingGeometryId.value = null; activeTool.value = 'select'; draw.setMode('select'); refreshSource()
}

async function createEvidenceFromCandidate() {
  const post = selectedCandidate.value
  if (!post) return
  const response = await fetch(`${API}/api/surveyor/objects`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_type: 'evidence', subtype: 'reported_observation', name: post.name || 'Candidate report',
      geometry: { type: 'Point', coordinates: [Number(post.map_longitude), Number(post.map_latitude)] },
      occurred_at: post.reported_at || null, epistemic_state: 'observed', confidence: 'possible',
      properties: { candidate_id: post.id, source: post.source, source_id: post.source_id, source_url: post.source_url, snapshot_title: post.name, reported_at: post.reported_at } })
  })
  if (!response.ok) { error.value = 'Could not create evidence marker'; return }
  const object = await response.json(); objects.value.unshift(object); refreshSource(); selected.value = object; selectedCandidate.value = null
}

async function persistDrawn(id) {
  const feature = draw?.getSnapshotFeature(id)
  if (!feature?.geometry) return
  const isZone = feature.geometry.type === 'Polygon'
  draftDrawId.value = id
  draftObject.value = { kind: isZone ? 'zone' : 'line', geometry: feature.geometry, subtype: isZone ? zoneSubtype.value : 'known_cat_highway' }
}

function chooseObject(event) {
  selectedHistoricalPlacement.value = null
  selectedCandidate.value = null
  const id = event.features?.[0]?.properties?.id
  selected.value = objects.value.find(object => object.id === Number(id)) || null
  if (selected.value) { title.value = selected.value.name || ''; subtype.value = selected.value.subtype || ''; notes.value = selected.value.notes || '' }
  const camera = cameras.value.find(item => item.map_object_id === selected.value?.id)
  if (camera?.placement) {
    cameraHeading.value = camera.placement.heading_degrees; cameraFov.value = camera.placement.fov_degrees; cameraRange.value = camera.placement.range_meters
  }
  if (selected.value) loadAttachments(selected.value.id)
  refreshCameraSource()
}

function chooseHistoricalPlacement(event) {
  const feature = event.features?.[0]
  if (!feature) return
  selected.value = null; selectedCandidate.value = null
  selectedHistoricalPlacement.value = { ...feature.properties, coordinates: feature.geometry.coordinates }
  refreshCameraSource()
}

async function loadAttachments(objectId) {
  try {
    const response = await fetch(`${API}/api/surveyor/objects/${objectId}/attachments`)
    if (response.ok) attachments.value = await response.json()
  } catch { attachments.value = [] }
}

async function loadTasks(objectId) {
  try {
    const response = await fetch(`${API}/api/surveyor/tasks?map_object_id=${objectId}`)
    if (response.ok) tasks.value = await response.json()
  } catch { tasks.value = [] }
}

async function createTask(payload) {
  try {
    const response = await fetch(`${API}/api/surveyor/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || 'Could not create follow-up')
    tasks.value.unshift(result)
  } catch (err) { error.value = err.message }
}

async function updateTask(task, status) {
  try {
    const response = await fetch(`${API}/api/surveyor/tasks/${task.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || 'Could not update follow-up')
    tasks.value = tasks.value.map(item => item.id === task.id ? result : item)
  } catch (err) { error.value = err.message }
}

async function saveEvidence(properties) {
  if (!selected.value) return
  saving.value = true
  try {
    const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ properties }) })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || 'Could not save evidence details')
    objects.value = objects.value.map(item => item.id === result.id ? result : item); selected.value = result; refreshSource()
  } catch (err) { error.value = err.message }
  finally { saving.value = false }
}

async function uploadAttachment(event) {
  const input = event?.target?.files ? event.target : null
  const file = input ? input.files?.[0] : event
  if (!file || !selected.value) return
  uploadingAttachment.value = true
  try {
    const form = new FormData(); form.append('file', file); form.append('caption', attachmentCaption.value); form.append('observed_at', new Date().toISOString())
    const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}/attachments`, { method: 'POST', body: form })
    if (!response.ok) throw new Error((await response.json()).detail || 'Could not upload attachment')
    attachments.value.unshift(await response.json()); attachmentCaption.value = ''; if (input) input.value = ''
  } catch (err) { error.value = err.message }
  finally { uploadingAttachment.value = false }
}

async function deleteAttachment(attachment) {
  if (!confirm('Delete this evidence attachment?')) return
  try {
    const response = await fetch(`${API}/api/surveyor/attachments/${attachment.id}`, { method: 'DELETE' })
    if (!response.ok) throw new Error((await response.json()).detail || 'Could not delete attachment')
    attachments.value = attachments.value.filter(item => item.id !== attachment.id)
  } catch (err) { error.value = err.message }
}

function chooseCandidate(event) {
  const id = Number(event.features?.[0]?.properties?.id)
  selectedCandidate.value = candidates.value.find(post => post.id === id) || null
  selected.value = null
  selectedHistoricalPlacement.value = null
  refreshCameraSource()
}

function showCandidateCluster(feature) {
  selected.value = null; selectedCandidate.value = null; selectedHistoricalPlacement.value = null
  const source = map.getSource('candidate-reports')
  source.getClusterLeaves(feature.properties.cluster_id, 50, 0, (err, leaves) => {
    if (err) { error.value = 'Could not load candidate reports in this cluster'; return }
    candidateCluster.value = { clusterId: feature.properties.cluster_id, coordinates: feature.geometry.coordinates,
      count: Number(feature.properties.point_count), posts: leaves.map(leaf => candidates.value.find(post => post.id === Number(leaf.properties.id))).filter(Boolean) }
  })
}
function openClusterCandidate(id) {
  const post = candidates.value.find(item => item.id === Number(id))
  if (!post) return
  candidateCluster.value = null; selected.value = null; selectedCandidate.value = post
}
async function createEvidenceForCandidate(id) {
  const post = candidates.value.find(item => item.id === Number(id))
  if (!post) return
  selectedCandidate.value = post; candidateCluster.value = null
  await createEvidenceFromCandidate()
}
function zoomCandidateCluster() {
  if (!candidateCluster.value) return
  const source = map.getSource('candidate-reports'), cluster = candidateCluster.value
  source.getClusterExpansionZoom(cluster.clusterId, (err, zoom) => { if (!err) { map.easeTo({ center: cluster.coordinates, zoom }); candidateCluster.value = null } })
}

async function saveSelected(saveAsNewPlacement = false) {
  if (!selected.value) return
  saving.value = true
  try {
    if (selected.value.object_type === 'trail_camera') {
      const camera = cameras.value.find(item => item.map_object_id === selected.value.id)
      if (!camera) throw new Error('Camera record unavailable')
      const cameraResponse = await fetch(`${API}/api/surveyor/cameras/${camera.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: title.value || camera.name, notes: notes.value, heading_degrees: cameraHeading.value,
          fov_degrees: cameraFov.value, range_meters: cameraRange.value, save_as_new_placement: saveAsNewPlacement }) })
      if (!cameraResponse.ok) throw new Error('Could not update camera placement')
      const updatedCamera = await cameraResponse.json()
      cameras.value = cameras.value.map(item => item.id === updatedCamera.id ? updatedCamera : item)
      const objectResponse = await fetch(`${API}/api/surveyor/objects/${selected.value.id}`)
      const canonical = await objectResponse.json()
      objects.value = objects.value.map(item => item.id === canonical.id ? canonical : item)
      selected.value = canonical; refreshSource(); refreshCameraSource()
      return
    }
    const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: title.value || null, subtype: subtype.value, notes: notes.value })
    })
    if (!response.ok) throw new Error('Could not update map object')
    const canonical = await response.json()
    objects.value = objects.value.map(item => item.id === canonical.id ? canonical : item)
    selected.value = canonical; refreshSource()
  } catch (err) { error.value = err.message }
  finally { saving.value = false }
}

async function deleteSelected() {
  if (!selected.value || !window.confirm('Delete this map object?')) return
  if (selected.value.object_type === 'trail_camera') {
    const camera = cameras.value.find(item => item.map_object_id === selected.value.id)
    if (!camera) return
    const response = await fetch(`${API}/api/surveyor/cameras/${camera.id}/deactivate`, { method: 'POST' })
    if (!response.ok) { error.value = 'Could not deactivate camera'; return }
    const updated = await response.json()
    cameras.value = cameras.value.map(item => item.id === updated.id ? updated : item)
    objects.value = objects.value.map(item => item.id === updated.map_object_id ? { ...item, status: 'inactive' } : item)
    selected.value = null; refreshSource(); refreshCameraSource(); return
  }
  const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}`, { method: 'DELETE' })
  if (!response.ok) { error.value = 'Could not delete map object'; return }
  objects.value = objects.value.filter(item => item.id !== selected.value.id); selected.value = null; refreshSource()
}

function onMapClick(event) {
  if (activeTool.value === 'move-camera') {
    moveSelectedCamera([event.lngLat.lng, event.lngLat.lat]).catch(err => { error.value = err.message })
    return
  }
  if (activeTool.value === 'move-object') {
    moveSelectedObject([event.lngLat.lng, event.lngLat.lat]).catch(err => { error.value = err.message })
    return
  }
  if (activeTool.value === 'link') {
    const feature = map.queryRenderedFeatures(event.point, { layers: ['surveyor-points', 'trail-camera-points'] })[0]
    if (!feature) return
    const objectId = Number(feature.properties.id)
    createLink(objectId).catch(err => { error.value = err.message; linkStartId.value = null })
    return
  }
  if (!['pin', 'note', 'camera', 'access'].includes(activeTool.value)) return
  const overlays = map.queryRenderedFeatures(event.point, { layers: ['surveyor-points', 'trail-camera-points', 'camera-history-points', 'selected-camera-handles', 'candidate-reports-point'] })
  if (overlays.length) return
  const coordinates = [event.lngLat.lng, event.lngLat.lat]
  if (activeTool.value === 'access') { accessDraftCoordinates.value = coordinates; return }
  const create = activeTool.value === 'note' ? createNote : activeTool.value === 'camera' ? createCamera : createPin
  create(coordinates)
}

function activateTool(tool) {
  if (tool === 'link') linkStartId.value = null
  activeTool.value = tool
  if (tool === 'zone') draw?.setMode('polygon')
  else if (tool === 'line') draw?.setMode('linestring')
  else draw?.setMode('select')
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  map = new maplibregl.Map({
    container: mapEl.value, style: 'https://tiles.openfreemap.org/styles/positron',
    center: [-79.117282, 35.845701], zoom: 12, attributionControl: true
  })
  map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right')
  map.on('load', () => {
    applyCatMapStyle(map)
    const snapper = createMapFeatureSnapper(map, () => snapSettings.value, target => { snapTarget.value = target })
    draw = new TerraDraw({ adapter: new TerraDrawMapLibreGLAdapter({ map }), modes: [
      new TerraDrawSelectMode(), new TerraDrawPolygonMode({ snapping: { toCustom: snapper } }),
      new TerraDrawLineStringMode({ snapping: { toCustom: snapper } })
    ] })
    draw.start()
    draw.on('finish', id => persistDrawn(id).catch(err => { error.value = err.message }))
    map.addSource('surveyor-objects', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('candidate-reports', { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, cluster: true, clusterRadius: 48, clusterMaxZoom: 13 })
    map.addSource('camera-cones', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('camera-history-points', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('selected-camera-handles', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('surveyor-links', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('active-search-track', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('search-coverage-preview', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('annual-landcover-source', { type: 'raster', tileSize: 256, attribution: 'Annual NLCD · USGS / MRLC', tiles: [
      'https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wms?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=Land-Cover-Native_conus_year_data&STYLES=&FORMAT=image/png&TRANSPARENT=TRUE&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&TIME=2025-01-01T00:00:00Z'
    ] })
    map.addLayer({ id: 'annual-landcover', type: 'raster', source: 'annual-landcover-source', paint: { 'raster-opacity': 0.32 } })
    map.addLayer({ id: 'active-search-track-line', type: 'line', source: 'active-search-track', paint: {
      'line-color': '#b75d34', 'line-width': 4, 'line-opacity': 0.9
    } })
    map.addLayer({ id: 'search-coverage-preview-fill', type: 'fill', source: 'search-coverage-preview', paint: { 'fill-color': '#d39a42', 'fill-opacity': 0.2 } })
    map.addLayer({ id: 'search-coverage-preview-outline', type: 'line', source: 'search-coverage-preview', paint: { 'line-color': '#a97129', 'line-width': 2, 'line-dasharray': [2, 2] } })
    map.addLayer({ id: 'camera-cones-fill', type: 'fill', source: 'camera-cones', paint: {
      'fill-color': '#477b7a', 'fill-opacity': ['*', ['get', 'opacity'], 0.18]
    } })
    map.addLayer({ id: 'camera-cones-outline', type: 'line', source: 'camera-cones', paint: {
      'line-color': '#477b7a', 'line-width': ['case', ['==', ['get', 'current'], true], 1.5, 1],
      'line-opacity': ['get', 'opacity'], 'line-dasharray': ['case', ['==', ['get', 'current'], true], ['literal', [1, 0]], ['literal', [2, 2]]]
    } })
    map.addLayer({ id: 'trail-camera-history-points', type: 'circle', source: 'camera-history-points', paint: {
      'circle-radius': 5, 'circle-color': '#477b7a', 'circle-opacity': ['get', 'opacity'], 'circle-stroke-color': '#f6f4e8', 'circle-stroke-width': 1.5
    } })
    map.addLayer({ id: 'selected-camera-handles', type: 'circle', source: 'selected-camera-handles', paint: {
      'circle-radius': 14, 'circle-color': ['match', ['get', 'handle'], 'center', '#f6f4e8', '#d66a16'],
      'circle-stroke-color': '#264d40', 'circle-stroke-width': 2
    } })
    map.addLayer({ id: 'candidate-reports-point', type: 'circle', source: 'candidate-reports', filter: ['!', ['has', 'point_count']], paint: {
      'circle-radius': 7, 'circle-color': '#416f72', 'circle-stroke-color': '#f6f4e8', 'circle-stroke-width': 2, 'circle-opacity': 0.92
    } })
    map.addLayer({ id: 'candidate-reports-cluster', type: 'circle', source: 'candidate-reports', filter: ['has', 'point_count'], paint: {
      'circle-radius': ['step', ['get', 'point_count'], 14, 10, 18, 30, 23], 'circle-color': '#416f72', 'circle-stroke-color': '#f6f4e8', 'circle-stroke-width': 2
    } })
    map.addLayer({ id: 'candidate-reports-cluster-count', type: 'symbol', source: 'candidate-reports', filter: ['has', 'point_count'], layout: {
      'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11
    }, paint: { 'text-color': '#ffffff' } })
    map.addLayer({ id: 'surveyor-zones-fill', type: 'fill', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Polygon'], paint: {
      'fill-color': ['match', ['get', 'subtype'], 'needs_search', '#dfad58', 'searched', '#667d69', 'known_cat_highway', '#58836f', 'wildlife_hotspot', '#9b7f61', '#75866e'],
      'fill-opacity': ['case', ['==', ['get', 'search_freshness'], 'stale'], 0.04, ['==', ['get', 'search_freshness'], 'aging'], 0.1, ['==', ['get', 'epistemic_state'], 'planning'], 0.08, ['==', ['get', 'confidence'], 'uncertain'], 0.09, 0.17]
    } })
    map.addLayer({ id: 'surveyor-zones-outline', type: 'line', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Polygon'], paint: {
      'line-color': ['match', ['get', 'subtype'], 'needs_search', '#c4943f', 'searched', '#667d69', 'known_cat_highway', '#58836f', '#75866e'],
      'line-width': 1.8, 'line-opacity': ['case', ['==', ['get', 'search_freshness'], 'stale'], 0.38, ['==', ['get', 'search_freshness'], 'aging'], 0.68, 0.95],
      'line-dasharray': ['match', ['get', 'epistemic_state'], 'hypothesis', ['literal', [1, 2]], 'inferred', ['literal', [4, 2]], 'planning', ['literal', [2, 2]], ['literal', [1, 0]]]
    } })
    map.addLayer({ id: 'surveyor-lines', type: 'line', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'LineString'], paint: {
      'line-color': '#4c705a', 'line-width': 3, 'line-opacity': ['case', ['==', ['get', 'confidence'], 'uncertain'], 0.48, 0.92],
      'line-dasharray': ['match', ['get', 'epistemic_state'], 'hypothesis', ['literal', [1, 2]], 'inferred', ['literal', [4, 2]], 'planning', ['literal', [2, 2]], ['literal', [1, 0]]]
    } })
    map.addLayer({ id: 'surveyor-links-line', type: 'line', source: 'surveyor-links', paint: {
      'line-color': ['match', ['get', 'link_type'], 'observed_movement', '#344f40', 'hypothesized_movement', '#98724a', 'possible_corridor', '#517c6a', 'evidence_against', '#a04d43', '#677b70'],
      'line-width': 2.5, 'line-opacity': 0.88,
      'line-dasharray': ['match', ['get', 'line_style'], 'dashed', ['literal', [3, 2]], 'dotted', ['literal', [1, 2]], ['literal', [1, 0]]]
    } })
    map.addLayer({ id: 'surveyor-links-labels', type: 'symbol', source: 'surveyor-links', layout: {
      'symbol-placement': 'line', 'text-field': ['get', 'label'], 'text-size': 10, 'text-keep-upright': true
    }, paint: { 'text-color': '#37483d', 'text-halo-color': '#f6f4e8', 'text-halo-width': 1.5 } })
    map.addLayer({ id: 'surveyor-links-arrows', type: 'symbol', source: 'surveyor-links', layout: {
      'symbol-placement': 'line-center', 'text-field': ['case', ['==', ['get', 'line_style'], 'double_arrow'], '↔', '➤'],
      'text-size': 15, 'text-keep-upright': false
    }, paint: { 'text-color': '#344f40', 'text-halo-color': '#f6f4e8', 'text-halo-width': 1.5 } })
    map.addLayer({ id: 'surveyor-points', type: 'circle', source: 'surveyor-objects', filter: ['all', ['==', ['geometry-type'], 'Point'], ['!=', ['get', 'object_type'], 'trail_camera']], paint: {
      'circle-radius': 8, 'circle-color': ['get', 'color'], 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2,
      'circle-opacity': ['case', ['==', ['get', 'confidence'], 'uncertain'], 0.55, 0.96]
    } })
    map.addLayer({ id: 'trail-camera-points', type: 'circle', source: 'surveyor-objects', filter: ['all', ['==', ['geometry-type'], 'Point'], ['==', ['get', 'object_type'], 'trail_camera']], paint: {
      'circle-radius': 9, 'circle-color': '#477b7a', 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2
    } })
    map.addLayer({ id: 'surveyor-labels', type: 'symbol', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Point'], layout: {
      'text-field': ['get', 'name'], 'text-offset': [0, 1.25], 'text-size': 12, 'text-anchor': 'top'
    }, paint: { 'text-color': '#24372e', 'text-halo-color': '#faf9f2', 'text-halo-width': 1.5 } })
    map.on('click', 'surveyor-points', chooseObject)
    map.on('click', 'trail-camera-points', chooseObject)
    map.on('mousedown', 'selected-camera-handles', beginCameraHandleDrag)
    map.on('touchstart', 'selected-camera-handles', beginCameraHandleDrag)
    map.on('click', 'camera-history-points', chooseHistoricalPlacement)
    map.on('mouseenter', 'selected-camera-handles', () => { map.getCanvas().style.cursor = 'grab' })
    map.on('mouseleave', 'selected-camera-handles', () => { if (!cameraHandleDrag) map.getCanvas().style.cursor = '' })
    map.on('click', 'candidate-reports-point', chooseCandidate)
    map.on('click', 'candidate-reports-cluster', event => {
      const feature = event.features?.[0]
      if (!feature) return
      showCandidateCluster(feature)
    })
    map.on('mouseenter', 'surveyor-points', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'surveyor-points', () => { map.getCanvas().style.cursor = '' })
    map.on('mouseenter', 'trail-camera-points', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'trail-camera-points', () => { map.getCanvas().style.cursor = '' })
    map.on('click', onMapClick)
    registerSurveyorIcons(map).then(({ registered }) => {
      if (!registered.length || !map.getLayer('surveyor-points')) return
      map.addLayer({ id: 'surveyor-icons', type: 'symbol', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Point'], layout: {
        'icon-image': ['get', 'icon'], 'icon-size': 0.72, 'icon-allow-overlap': true, 'icon-ignore-placement': true
      } })
      const available = ['literal', registered]
      map.setFilter('surveyor-points', ['all', ['==', ['geometry-type'], 'Point'], ['!=', ['get', 'object_type'], 'trail_camera'], ['!', ['in', ['get', 'icon'], available]]])
      map.setFilter('trail-camera-points', ['all', ['==', ['geometry-type'], 'Point'], ['==', ['get', 'object_type'], 'trail_camera'], ['!', ['in', ['get', 'icon'], available]]])
      map.setLayoutProperty('surveyor-icons', 'visibility', layerSettings.value.objects ? 'visible' : 'none')
    })
    layerSettings.value = { ...layerSettings.value }
    loadObjects()
  })
  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(mapEl.value)
})

function onVisibilityChange() {
  if (document.visibilityState === 'hidden' && activeSession.value) saveSessionCheckpoint()
  if (document.visibilityState === 'visible' && activeSession.value) requestScreenWakeLock()
}

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  releaseScreenWakeLock()
  resizeObserver?.disconnect(); draw?.stop()
  if (geoWatchId != null) navigator.geolocation?.clearWatch(geoWatchId)
  if (activeSession.value) saveSessionCheckpoint()
  map?.remove()
})
</script>

<template>
  <main class="surveyor-page">
    <header class="surveyor-topbar">
      <div><p class="eyebrow">FIELD MAP · {{ objects.length }} OBJECTS</p><h1>Surveyor</h1></div>
      <SearchSessionBar :active-session="activeSession" :method="sessionMethod" :distance="sessionDistance()" :loading="loading" @start="startSearch" @end="endSearch" @update:method="sessionMethod=$event" @layers="layerDrawerOpen=!layerDrawerOpen" />
    </header>
    <p v-if="error" class="surveyor-error">{{ error }}</p><p v-if="locationWarning" class="location-warning">{{ locationWarning }}</p>
    <div class="surveyor-workspace">
      <SurveyorToolbar :active-tool="activeTool" @tool="activateTool" @more="mobileMoreOpen=!mobileMoreOpen" />
      <section class="surveyor-map-shell"><div ref="mapEl" class="surveyor-map"></div><div v-if="snapTarget" class="snap-indicator" :style="{ left: `${snapTarget.x}px`, top: `${snapTarget.y}px` }"><i></i><small>{{ snapTarget.kind.replace('_', ' ').toUpperCase() }}</small></div><div v-if="['pin','note','camera','access','move-camera','move-object'].includes(activeTool)" class="map-hint">{{ activeTool === 'pin' ? 'Choose a marker type, then tap the map' : activeTool === 'camera' ? 'Tap the map to place a trail camera' : activeTool === 'access' ? 'Tap a property to record access details' : ['move-camera','move-object'].includes(activeTool) ? 'Tap the new object location' : 'Tap the map to add a field note' }}</div><div v-if="activeTool === 'link'" class="map-hint">{{ linkStartId ? 'Choose the second object to connect' : 'Choose the first object to connect' }}</div><select v-if="activeTool === 'link'" v-model="linkType" class="pin-type-picker"><option value="observed_movement">Observed movement</option><option value="hypothesized_movement">Hypothesized movement</option><option value="association">Association</option><option value="possible_corridor">Possible corridor</option><option value="evidence_for">Evidence for</option><option value="evidence_against">Evidence against</option><option value="custom">Custom connection</option></select><select v-if="activeTool === 'zone'" v-model="zoneSubtype" class="pin-type-picker"><option value="searched">Searched</option><option value="needs_search">Needs search</option><option value="needs_recheck">Needs re-check</option><option value="known_cat_highway">Known cat highway</option><option value="wildlife_hotspot">Wildlife hotspot</option><option value="likely_shelter">Likely shelter</option><option value="dog_territory">Dog territory</option><option value="private_no_access">Private / no access</option></select><div v-if="['zone','line'].includes(activeTool)" class="snap-controls"><button @click="snapMenuOpen = !snapMenuOpen">Snap {{ snapMenuOpen ? '▴' : '▾' }}</button><div v-if="snapMenuOpen" class="snap-menu"><label><input v-model="snapSettings.roads" type="checkbox" /> Roads</label><label><input v-model="snapSettings.trails" type="checkbox" /> Trails</label><label><input v-model="snapSettings.waterways" type="checkbox" /> Waterways</label><label><input v-model="snapSettings.objects" type="checkbox" /> Pins</label><label><input v-model="snapSettings.cameras" type="checkbox" /> Trail cameras</label><label><input v-model="snapSettings.zoneBoundaries" type="checkbox" /> Zone boundaries</label></div></div></section>
      <LayerDrawer v-if="layerDrawerOpen" :model-value="layerSettings" :counts="{ objects: objects.length, links: links.length, cameras: cameras.length, candidates: candidates.length }" @update:model-value="layerSettings = $event" @close="layerDrawerOpen = false" />
      <aside v-if="selectedHistoricalPlacement" class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">HISTORICAL CAMERA PLACEMENT</p><h2>{{ selectedHistoricalPlacement.name }}</h2></div><button aria-label="Close history" @click="selectedHistoricalPlacement=null">×</button></div><p>{{ new Date(selectedHistoricalPlacement.installed_at).toLocaleString() }} – {{ selectedHistoricalPlacement.removed_at ? new Date(selectedHistoricalPlacement.removed_at).toLocaleString() : 'Current' }}</p><p>Heading {{ Math.round(selectedHistoricalPlacement.heading_degrees) }}° · FOV {{ Math.round(selectedHistoricalPlacement.fov_degrees) }}° · range {{ Math.round(selectedHistoricalPlacement.range_meters) }} m</p><p class="inspector-meta">Historical placements cannot be edited as the active camera.</p></aside>
      <CandidateInspector v-if="selectedCandidate" :candidate="selectedCandidate" @close="selectedCandidate=null" @evidence="createEvidenceFromCandidate" />
      <ObjectInspector v-else-if="selected" v-model:title="title" v-model:subtype="subtype" v-model:notes="notes" v-model:camera-heading="cameraHeading" v-model:camera-fov="cameraFov" v-model:camera-range="cameraRange" v-model:attachment-caption="attachmentCaption" :selected="selected" :types="types" :attachments="attachments" :tasks="tasks" :camera-history="cameras.find(item => item.map_object_id === selected.id)?.history || []" :uploading="uploadingAttachment" :saving="saving" :api="API" :active-tool="activeTool" @close="selected=null" @save="saveSelected" @save-historical="saveSelected(true)" @move="activeTool=selected.object_type === 'trail_camera' ? 'move-camera' : 'move-object'" @deactivate="deleteSelected" @delete="deleteSelected" @edit-geometry="beginGeometryEdit" @save-geometry="finishGeometryEdit(true)" @cancel-geometry="finishGeometryEdit(false)" @upload="uploadAttachment" @delete-attachment="deleteAttachment" @media-error="error=$event" @create-task="createTask" @update-task="updateTask" @save-evidence="saveEvidence" />
    </div>

    <div v-if="mobileMoreOpen" class="mobile-more-menu"><button @click="activateTool('line'); mobileMoreOpen=false">Line</button><button @click="activateTool('link'); mobileMoreOpen=false">Link</button><button @click="activateTool('access'); mobileMoreOpen=false">Property / access</button><button disabled>Measure · coming soon</button><button @click="layerDrawerOpen=true; mobileMoreOpen=false">Layers</button><button v-if="!activeSession" @click="startSearch">Start search</button><button v-else @click="endSearch">End search</button></div>
    <MobileInspectorSheet :open="Boolean(selected || selectedCandidate || selectedHistoricalPlacement)" @close="selected=null; selectedCandidate=null; selectedHistoricalPlacement=null">
      <template v-if="selectedCandidate"><p class="eyebrow">CANDIDATE REPORT · {{ selectedCandidate.source }}</p><h2>{{ selectedCandidate.name || 'Found cat report' }}</h2><p>{{ selectedCandidate.location_text }}</p><a class="primary candidate-open-link" :href="`/#post-${selectedCandidate.id}`">Open Candidate</a><button class="secondary-button" @click="createEvidenceFromCandidate">Create evidence marker</button></template>
      <template v-else-if="selectedHistoricalPlacement"><p class="eyebrow">HISTORICAL CAMERA PLACEMENT</p><h2>{{ selectedHistoricalPlacement.name }}</h2><p>{{ new Date(selectedHistoricalPlacement.installed_at).toLocaleDateString() }} – {{ selectedHistoricalPlacement.removed_at ? new Date(selectedHistoricalPlacement.removed_at).toLocaleDateString() : 'Current' }}</p><p>Heading {{ Math.round(selectedHistoricalPlacement.heading_degrees) }}° · FOV {{ Math.round(selectedHistoricalPlacement.fov_degrees) }}° · {{ Math.round(selectedHistoricalPlacement.range_meters) }} m</p></template>
      <template v-else-if="selected"><p class="eyebrow">{{ selected.object_type }} · #{{ selected.id }}</p><h2>{{ selected.name || 'Field object' }}</h2><label>Name<input v-model="title" /></label><label>Notes<textarea v-model="notes" rows="3"></textarea></label><p v-if="selected.subtype === 'searched'">{{ searchFreshness(selected) }} coverage · {{ selected.properties?.searched_at ? new Date(selected.properties.searched_at).toLocaleDateString() : 'Date unknown' }}</p><button class="primary" @click="saveSelected">Save changes</button><button v-if="selected.object_type==='trail_camera'" class="secondary-button" @click="activeTool='move-camera'">Move camera</button><section class="attachment-list"><h3>Evidence media</h3><article v-for="attachment in attachments" :key="attachment.id" class="evidence-attachment"><img v-if="attachment.attachment_type==='image'" :src="`${API}${attachment.media_url}`" :alt="attachment.caption || 'Evidence photo'"/><audio v-else-if="attachment.attachment_type==='audio'" :src="`${API}${attachment.media_url}`" controls preload="none"></audio><p>{{ attachment.caption || attachment.source }}</p><small>{{ attachment.observed_at ? new Date(attachment.observed_at).toLocaleString() : new Date(attachment.created_at).toLocaleString() }}</small><button class="danger-button" @click="deleteAttachment(attachment)">Delete</button></article><input v-model="attachmentCaption" placeholder="Caption (optional)"/><PhotoCapture @select="uploadAttachment"/><AudioRecorder @select="uploadAttachment" @error="error=$event"/><label class="attachment-upload">Add file<input type="file" accept="application/pdf,text/plain,audio/*,image/*" @change="uploadAttachment"/></label></section></template>
    </MobileInspectorSheet>
    <CandidateClusterSheet v-if="candidateCluster" :cluster="candidateCluster" @close="candidateCluster=null" @open="openClusterCandidate" @evidence="createEvidenceForCandidate" @zoom="zoomCandidateCluster" />
    <div v-if="draftObject" class="field-sheet-backdrop"><DraftObjectSheet :kind="draftObject.kind" :geometry="draftObject.geometry" :default-subtype="draftObject.subtype" :camera-defaults="{ heading: cameraHeading, fov: cameraFov, range: cameraRange }" @save="saveDraft($event).catch(err => error=err.message)" @cancel="cancelDraft" /></div>
    <div v-if="accessDraftCoordinates" class="field-sheet-backdrop"><AccessEditor :coordinates="accessDraftCoordinates" :api="API" @save="accessSaved($event).catch(err => error=err.message)" @cancel="accessDraftCoordinates=null" /></div>
    <div v-if="searchResultOpen" class="field-sheet-backdrop"><SearchResultSheet :route="trackCoords.length >= 2 ? { type: 'LineString', coordinates: trackCoords } : null" :method="activeSession?.method || sessionMethod" @coverage-preview="setCoveragePreview" @save="finishSearch" @cancel="searchResultOpen=false; setCoveragePreview(null)" /></div>
    <footer class="surveyor-footer"><SurveyTimeline v-model="timelineWindow" /><span v-if="activeSession" class="active-session-status">SEARCH ACTIVE · {{ Math.round(sessionDistance()) }} m</span></footer>
  </main>
</template>
