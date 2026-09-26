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

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const route = useRoute()
const timelineWindow = ref({ preset: '30d', from: new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 16), to: new Date().toISOString().slice(0, 16) })
const LAYER_STORAGE = 'archie-radar-surveyor-layers'
const defaultLayers = { objects: true, links: true, cameras: true, cameraHistory: false, candidates: true, landcover: false }
const layerSettings = ref((() => { try { return { ...defaultLayers, ...JSON.parse(localStorage.getItem(LAYER_STORAGE) || '{}') } } catch { return { ...defaultLayers } } })())
const layerDrawerOpen = ref(false)
const mapEl = ref(null)
const objects = ref([])
const candidates = ref([])
const cameras = ref([])
const links = ref([])
const linkStartId = ref(null)
const linkType = ref('association')
const attachments = ref([])
const attachmentCaption = ref('')
const uploadingAttachment = ref(false)
const activeSession = ref(null)
const sessionMethod = ref('walking')
const trackCoords = ref([])
const selected = ref(null)
const selectedCandidate = ref(null)
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
const snapSettings = ref({ roads: true, trails: true, waterways: true, objects: true })
const snapMenuOpen = ref(false)
const snapTarget = ref(null)
const notes = ref('')
const saving = ref(false)
let map
let draw
let resizeObserver
let geoWatchId = null
let checkpointBusy = false

const types = PIN_TYPES
watch(layerSettings, settings => {
  try { localStorage.setItem(LAYER_STORAGE, JSON.stringify(settings)) } catch {}
  candidatesVisible.value = settings.candidates
  cameraHistoryVisible.value = settings.cameraHistory
  for (const layer of ['surveyor-zones-fill', 'surveyor-lines', 'surveyor-points', 'surveyor-labels']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.objects ? 'visible' : 'none')
  }
  for (const layer of ['surveyor-links-line', 'surveyor-links-labels', 'surveyor-links-arrows']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.links ? 'visible' : 'none')
  }
  for (const layer of ['camera-cones-fill', 'camera-cones-outline', 'trail-camera-points']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', settings.cameras ? 'visible' : 'none')
  }
  if (map?.getLayer('annual-landcover')) map.setLayoutProperty('annual-landcover', 'visibility', settings.landcover ? 'visible' : 'none')
}, { deep: true })
watch(() => selected.value?.id, id => { attachments.value = []; if (id) loadAttachments(id) })
function inTimeline(value) {
  if (timelineWindow.value.preset === 'all' || !value) return true
  const time = new Date(value).getTime()
  return time >= new Date(timelineWindow.value.from).getTime() && time <= new Date(timelineWindow.value.to).getTime()
}
const featureCollection = computed(() => ({
  type: 'FeatureCollection',
  features: objects.value.filter(object => object.id !== editingGeometryId.value && inTimeline(object.occurred_at || object.valid_from || object.created_at)).map(object => ({
    type: 'Feature', id: object.id, geometry: object.geometry,
    properties: { id: object.id, name: object.name || object.subtype || object.object_type, subtype: object.subtype || '', object_type: object.object_type }
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

function destination(lon, lat, distanceMeters, bearing) {
  const radius = 6371008.8, angular = distanceMeters / radius, brng = bearing * Math.PI / 180
  const lat1 = lat * Math.PI / 180, lon1 = lon * Math.PI / 180
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(brng))
  const lon2 = lon1 + Math.atan2(Math.sin(brng) * Math.sin(angular) * Math.cos(lat1), Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2))
  return [lon2 * 180 / Math.PI, lat2 * 180 / Math.PI]
}

function cameraGeoJSON() {
  const features = []
  for (const camera of cameras.value) {
    const overlapping = camera.history.filter(placement => timelineWindow.value.preset === 'all' || (
      new Date(placement.installed_at) <= new Date(timelineWindow.value.to) &&
      (!placement.removed_at || new Date(placement.removed_at) >= new Date(timelineWindow.value.from))))
    const placements = cameraHistoryVisible.value ? overlapping : overlapping.filter(placement =>
      !placement.removed_at || new Date(placement.removed_at) >= new Date(timelineWindow.value.to)).slice(0, 1)
    for (const placement of placements) {
      const start = Number(placement.heading_degrees) - Number(placement.fov_degrees) / 2
      const end = Number(placement.heading_degrees) + Number(placement.fov_degrees) / 2
      const center = [Number(placement.longitude), Number(placement.latitude)]
      const ring = [center]
      for (let step = 0; step <= 24; step++) ring.push(destination(center[0], center[1], Number(placement.range_meters), start + (end - start) * step / 24))
      ring.push(center)
      features.push({ type: 'Feature', properties: { camera_id: camera.id, name: camera.name, current: !placement.removed_at,
        installed_at: placement.installed_at, removed_at: placement.removed_at || '' }, geometry: { type: 'Polygon', coordinates: [ring] } })
    }
  }
  return { type: 'FeatureCollection', features }
}

function refreshCameraSource() { map?.getSource('camera-cones')?.setData(cameraGeoJSON()) }
watch(timelineWindow, () => { refreshSource(); refreshCandidates(); refreshCameraSource() }, { deep: true })

function trackCollection() {
  return { type: 'FeatureCollection', features: trackCoords.value.length >= 2 ? [{ type: 'Feature', properties: {},
    geometry: { type: 'LineString', coordinates: trackCoords.value } }] : [] }
}

function refreshTrack() { map?.getSource('active-search-track')?.setData(trackCollection()) }

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
    if (!previous || distanceBetween(previous, coordinate) > 2) {
      trackCoords.value.push(coordinate); refreshTrack()
      if (trackCoords.value.length % 5 === 0) saveSessionCheckpoint()
    }
  }, () => { error.value = 'Location tracking is unavailable. The search session is still active.' }, { enableHighAccuracy: true, maximumAge: 5000 })
}

async function loadActiveSession() {
  try {
    const response = await fetch(`${API}/api/surveyor/sessions`)
    if (!response.ok) return
    const sessions = await response.json()
    const requestedId = Number(route.query.session)
    const session = sessions.find(item => item.id === requestedId) || sessions.find(item => !item.ended_at)
    if (!session) return
    if (!session.ended_at) activeSession.value = session
    trackCoords.value = session.track_geojson?.type === 'LineString' ? session.track_geojson.coordinates : []
    refreshTrack()
    if (trackCoords.value.length) map?.flyTo({ center: trackCoords.value.at(-1), zoom: Math.max(map.getZoom(), 14) })
    if (!session.ended_at) beginLocationWatch()
  } catch { /* Running field work will still load if the session service is unavailable. */ }
}

async function startSearch() {
  const response = await fetch(`${API}/api/surveyor/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method: sessionMethod.value }) })
  if (!response.ok) { error.value = 'Could not start search session'; return }
  activeSession.value = await response.json(); trackCoords.value = []; refreshTrack()
  beginLocationWatch()
}

async function endSearch() {
  if (!activeSession.value) return
  const response = await fetch(`${API}/api/surveyor/sessions/${activeSession.value.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_geojson: trackCoords.value.length >= 2 ? { type: 'LineString', coordinates: trackCoords.value } : null,
      distance_meters: sessionDistance(), result_summary: window.prompt('Search result', 'No cat activity reported') || '' }) })
  if (!response.ok) { error.value = 'Could not finish search session'; return }
  if (geoWatchId != null) navigator.geolocation?.clearWatch(geoWatchId)
  geoWatchId = null; activeSession.value = null
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
      source_id: post.source_id, source_url: post.source_url || '', reported_at: post.reported_at || '',
      location_text: post.location_text || '' },
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
  const name = window.prompt('Name this field observation')
  if (name === null) return
  const response = await fetch(`${API}/api/surveyor/objects`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_type: 'pin', subtype: subtype.value, name: name.trim() || null,
      geometry: { type: 'Point', coordinates }, notes: '', epistemic_state: 'observed', confidence: 'possible' })
  })
  if (!response.ok) throw new Error('Could not save map marker')
  const object = await response.json()
  objects.value.unshift(object); refreshSource(); selected.value = object; activeTool.value = 'select'
}

async function createNote(coordinates) {
  const name = window.prompt('Note title')
  if (name === null) return
  const noteText = window.prompt('Field note')
  if (noteText === null) return
  const response = await fetch(`${API}/api/surveyor/objects`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_type: 'note', subtype: 'field_note', name: name.trim() || 'Field note', notes: noteText,
      geometry: { type: 'Point', coordinates }, epistemic_state: 'observed' }) })
  if (!response.ok) throw new Error('Could not save field note')
  const object = await response.json(); objects.value.unshift(object); refreshSource(); selected.value = object
  title.value = object.name; subtype.value = object.subtype; notes.value = object.notes; activeTool.value = 'select'; draw?.setMode('select')
}

async function createCamera(coordinates) {
  const name = window.prompt('Name this trail camera')
  if (name === null) return
  const response = await fetch(`${API}/api/surveyor/cameras`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim() || 'Trail camera', longitude: coordinates[0], latitude: coordinates[1],
      heading_degrees: cameraHeading.value, fov_degrees: cameraFov.value, range_meters: cameraRange.value }) })
  if (!response.ok) throw new Error('Could not save trail camera')
  const camera = await response.json(); cameras.value.unshift(camera)
  const objectResponse = await fetch(`${API}/api/surveyor/objects/${camera.map_object_id}`)
  if (!objectResponse.ok) throw new Error('Camera was saved but its map object could not be loaded')
  const object = await objectResponse.json(); objects.value.unshift(object); refreshSource(); refreshCameraSource()
  selected.value = object; selectedCandidate.value = null; title.value = object.name; subtype.value = 'camera'; notes.value = object.notes
  cameraHeading.value = camera.placement.heading_degrees; cameraFov.value = camera.placement.fov_degrees; cameraRange.value = camera.placement.range_meters
  activeTool.value = 'select'; draw?.setMode('select')
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
  const name = window.prompt(isZone ? 'Name this zone' : 'Name this line')
  if (name === null) { draw.removeFeatures([id]); return }
  const response = await fetch(`${API}/api/surveyor/objects`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_type: isZone ? 'zone' : 'corridor', subtype: isZone ? zoneSubtype.value : 'cat_highway',
      name: name.trim() || null, geometry: feature.geometry, epistemic_state: 'planning',
      confidence: 'possible', status: isZone ? zoneSubtype.value : 'active' })
  })
  draw.removeFeatures([id])
  if (!response.ok) throw new Error('Could not save drawing')
  const object = await response.json()
  objects.value.unshift(object); refreshSource(); activeTool.value = 'select'; draw.setMode('select')
}

function chooseObject(event) {
  selectedCandidate.value = null
  const id = event.features?.[0]?.properties?.id
  selected.value = objects.value.find(object => object.id === Number(id)) || null
  if (selected.value) { title.value = selected.value.name || ''; subtype.value = selected.value.subtype || ''; notes.value = selected.value.notes || '' }
  const camera = cameras.value.find(item => item.map_object_id === selected.value?.id)
  if (camera?.placement) {
    cameraHeading.value = camera.placement.heading_degrees; cameraFov.value = camera.placement.fov_degrees; cameraRange.value = camera.placement.range_meters
  }
  if (selected.value) loadAttachments(selected.value.id)
}

async function loadAttachments(objectId) {
  try {
    const response = await fetch(`${API}/api/surveyor/objects/${objectId}/attachments`)
    if (response.ok) attachments.value = await response.json()
  } catch { attachments.value = [] }
}

async function uploadAttachment(event) {
  const file = event.target.files?.[0]
  if (!file || !selected.value) return
  uploadingAttachment.value = true
  try {
    const form = new FormData(); form.append('file', file); form.append('caption', attachmentCaption.value)
    const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}/attachments`, { method: 'POST', body: form })
    if (!response.ok) throw new Error((await response.json()).detail || 'Could not upload attachment')
    attachments.value.unshift(await response.json()); attachmentCaption.value = ''; event.target.value = ''
  } catch (err) { error.value = err.message }
  finally { uploadingAttachment.value = false }
}

function chooseCandidate(event) {
  const id = Number(event.features?.[0]?.properties?.id)
  selectedCandidate.value = candidates.value.find(post => post.id === id) || null
  selected.value = null
}

async function saveSelected() {
  if (!selected.value) return
  saving.value = true
  try {
    if (selected.value.object_type === 'trail_camera') {
      const camera = cameras.value.find(item => item.map_object_id === selected.value.id)
      if (!camera) throw new Error('Camera record unavailable')
      const cameraResponse = await fetch(`${API}/api/surveyor/cameras/${camera.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: title.value || camera.name, notes: notes.value, heading_degrees: cameraHeading.value,
          fov_degrees: cameraFov.value, range_meters: cameraRange.value }) })
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
  if (!['pin', 'note', 'camera'].includes(activeTool.value)) return
  const overlays = map.queryRenderedFeatures(event.point, { layers: ['surveyor-points', 'trail-camera-points', 'candidate-reports-point'] })
  if (overlays.length) return
  const coordinates = [event.lngLat.lng, event.lngLat.lat]
  const create = activeTool.value === 'note' ? createNote : activeTool.value === 'camera' ? createCamera : createPin
  create(coordinates).catch(err => { error.value = err.message })
}

onMounted(() => {
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
    map.addSource('surveyor-links', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('active-search-track', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('annual-landcover-source', { type: 'raster', tileSize: 256, attribution: 'Annual NLCD · USGS / MRLC', tiles: [
      'https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wms?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=Land-Cover-Native_conus_year_data&STYLES=&FORMAT=image/png&TRANSPARENT=TRUE&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&TIME=2025-01-01T00:00:00Z'
    ] })
    map.addLayer({ id: 'annual-landcover', type: 'raster', source: 'annual-landcover-source', paint: { 'raster-opacity': 0.32 } })
    map.addLayer({ id: 'active-search-track-line', type: 'line', source: 'active-search-track', paint: {
      'line-color': '#b75d34', 'line-width': 4, 'line-opacity': 0.9
    } })
    map.addLayer({ id: 'camera-cones-fill', type: 'fill', source: 'camera-cones', paint: {
      'fill-color': '#477b7a', 'fill-opacity': ['case', ['==', ['get', 'current'], true], 0.18, 0.075]
    } })
    map.addLayer({ id: 'camera-cones-outline', type: 'line', source: 'camera-cones', paint: {
      'line-color': '#477b7a', 'line-width': ['case', ['==', ['get', 'current'], true], 1.5, 1],
      'line-dasharray': ['case', ['==', ['get', 'current'], true], ['literal', [1, 0]], ['literal', [2, 2]]]
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
      'fill-opacity': 0.17
    } })
    map.addLayer({ id: 'surveyor-lines', type: 'line', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'LineString'], paint: {
      'line-color': '#4c705a', 'line-width': 3, 'line-dasharray': ['case', ['==', ['get', 'object_type'], 'corridor'], ['literal', [2, 2]], ['literal', [1, 0]]]
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
      'circle-radius': 8, 'circle-color': ['match', ['get', 'object_type'], 'note', '#c59043', '#d66a16'], 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2,
      'circle-opacity': 0.96
    } })
    map.addLayer({ id: 'trail-camera-points', type: 'circle', source: 'surveyor-objects', filter: ['all', ['==', ['geometry-type'], 'Point'], ['==', ['get', 'object_type'], 'trail_camera']], paint: {
      'circle-radius': 9, 'circle-color': '#477b7a', 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2
    } })
    map.addLayer({ id: 'surveyor-labels', type: 'symbol', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Point'], layout: {
      'text-field': ['get', 'name'], 'text-offset': [0, 1.25], 'text-size': 12, 'text-anchor': 'top'
    }, paint: { 'text-color': '#24372e', 'text-halo-color': '#faf9f2', 'text-halo-width': 1.5 } })
    map.on('click', 'surveyor-points', chooseObject)
    map.on('click', 'trail-camera-points', chooseObject)
    map.on('click', 'candidate-reports-point', chooseCandidate)
    map.on('click', 'candidate-reports-cluster', event => {
      const feature = event.features?.[0]
      if (!feature) return
      map.getSource('candidate-reports').getClusterExpansionZoom(feature.properties.cluster_id, (err, zoom) => {
        if (!err) map.easeTo({ center: feature.geometry.coordinates, zoom })
      })
    })
    map.on('mouseenter', 'surveyor-points', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'surveyor-points', () => { map.getCanvas().style.cursor = '' })
    map.on('mouseenter', 'trail-camera-points', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'trail-camera-points', () => { map.getCanvas().style.cursor = '' })
    map.on('click', onMapClick)
    layerSettings.value = { ...layerSettings.value }
    loadObjects()
  })
  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(mapEl.value)
})

onBeforeUnmount(() => {
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
      <div class="surveyor-actions"><span v-if="loading">Loading field data…</span><select v-if="!activeSession" v-model="sessionMethod" class="session-method"><option value="walking">Walking</option><option value="bike">Bike</option><option value="car">Car</option><option value="stationary_observation">Observation</option><option value="camera_maintenance">Camera care</option><option value="flyering">Flyering</option></select><button v-if="!activeSession" class="session-button" @click="startSearch">Start search</button><button v-else class="session-button active" @click="endSearch">End search · {{ Math.round(sessionDistance()) }} m</button><button :class="{ active: layerDrawerOpen }" @click="layerDrawerOpen = !layerDrawerOpen">Layers</button><button :class="{ active: activeTool === 'select' }" @click="activeTool = 'select'; draw?.setMode('select')">Select</button><button :class="{ active: activeTool === 'pin' }" @click="activeTool = 'pin'; draw?.setMode('select')">＋ Pin</button><button :class="{ active: activeTool === 'camera' }" @click="activeTool = 'camera'; draw?.setMode('select')">Camera</button><button :class="{ active: activeTool === 'zone' }" @click="activeTool = 'zone'; draw?.setMode('polygon')">Zone</button><button :class="{ active: activeTool === 'line' }" @click="activeTool = 'line'; draw?.setMode('linestring')">Line</button><button :class="{ active: activeTool === 'link' }" @click="linkStartId = null; activeTool = 'link'; draw?.setMode('select')">Link</button><button :class="{ active: activeTool === 'note' }" @click="activeTool = 'note'; draw?.setMode('select')">Note</button></div>
    </header>
    <p v-if="error" class="surveyor-error">{{ error }}</p>
    <div class="surveyor-workspace">
      <aside class="surveyor-tools"><p>TOOLS</p><button :class="{ active: activeTool === 'select' }" @click="activeTool = 'select'; draw?.setMode('select')">↖<span>Select</span></button><button :class="{ active: activeTool === 'pin' }" @click="activeTool = 'pin'; draw?.setMode('select')">⌖<span>Pin</span></button><button :class="{ active: activeTool === 'camera' }" @click="activeTool = 'camera'; draw?.setMode('select')">◉<span>Camera</span></button><button :class="{ active: activeTool === 'zone' }" @click="activeTool = 'zone'; draw?.setMode('polygon')">▱<span>Zone</span></button><button :class="{ active: activeTool === 'line' }" @click="activeTool = 'line'; draw?.setMode('linestring')">⌁<span>Line</span></button><button :class="{ active: activeTool === 'link' }" @click="linkStartId = null; activeTool = 'link'; draw?.setMode('select')">⟷<span>Link</span></button><button :class="{ active: activeTool === 'note' }" @click="activeTool = 'note'; draw?.setMode('select')">✎<span>Note</span></button></aside>
      <section class="surveyor-map-shell"><div ref="mapEl" class="surveyor-map"></div><div v-if="snapTarget" class="snap-indicator" :style="{ left: `${snapTarget.x}px`, top: `${snapTarget.y}px` }"></div><div v-if="['pin','note','camera','move-camera','move-object'].includes(activeTool)" class="map-hint">{{ activeTool === 'pin' ? 'Choose a marker type, then tap the map' : activeTool === 'camera' ? 'Tap the map to place a trail camera' : ['move-camera','move-object'].includes(activeTool) ? 'Tap the new object location' : 'Tap the map to add a field note' }}</div><div v-if="activeTool === 'link'" class="map-hint">{{ linkStartId ? 'Choose the second object to connect' : 'Choose the first object to connect' }}</div><select v-if="activeTool === 'link'" v-model="linkType" class="pin-type-picker"><option value="observed_movement">Observed movement</option><option value="hypothesized_movement">Hypothesized movement</option><option value="association">Association</option><option value="possible_corridor">Possible corridor</option><option value="evidence_for">Evidence for</option><option value="evidence_against">Evidence against</option><option value="custom">Custom connection</option></select><select v-if="activeTool === 'pin'" v-model="subtype" class="pin-type-picker"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select><select v-if="activeTool === 'zone'" v-model="zoneSubtype" class="pin-type-picker"><option value="searched">Searched</option><option value="needs_search">Needs search</option><option value="needs_recheck">Needs re-check</option><option value="known_cat_highway">Known cat highway</option><option value="wildlife_hotspot">Wildlife hotspot</option><option value="likely_shelter">Likely shelter</option><option value="dog_territory">Dog territory</option><option value="private_no_access">Private / no access</option></select><div v-if="['zone','line'].includes(activeTool)" class="snap-controls"><button @click="snapMenuOpen = !snapMenuOpen">Snap {{ snapMenuOpen ? '▴' : '▾' }}</button><div v-if="snapMenuOpen" class="snap-menu"><label><input v-model="snapSettings.roads" type="checkbox" /> Roads</label><label><input v-model="snapSettings.trails" type="checkbox" /> Trails</label><label><input v-model="snapSettings.waterways" type="checkbox" /> Waterways</label><label><input v-model="snapSettings.objects" type="checkbox" /> Pins and zones</label></div></div></section>
      <LayerDrawer v-if="layerDrawerOpen" :model-value="layerSettings" :counts="{ objects: objects.length, links: links.length, cameras: cameras.length, candidates: candidates.length }" @update:model-value="layerSettings = $event" @close="layerDrawerOpen = false" />
      <aside v-if="selectedCandidate" class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">CANDIDATE REPORT</p><h2>{{ selectedCandidate.name || 'Found cat report' }}</h2></div><button aria-label="Close inspector" @click="selectedCandidate = null">×</button></div><p class="inspector-meta">{{ selectedCandidate.source }} · {{ selectedCandidate.reported_at ? new Date(selectedCandidate.reported_at).toLocaleDateString() : 'Report date unknown' }}</p><p>{{ selectedCandidate.location_text }}</p><div class="inspector-buttons"><a class="primary candidate-open-link" :href="`/#post-${selectedCandidate.id}`">Open Candidate</a><button class="secondary-button" @click="createEvidenceFromCandidate">Create evidence marker</button></div></aside>
      <aside v-else-if="selected" class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">{{ selected.object_type }} · #{{ selected.id }}</p><h2>{{ selected.name || 'Field object' }}</h2></div><button aria-label="Close inspector" @click="selected = null">×</button></div><label>Name<input v-model="title" maxlength="180" /></label><label v-if="selected.object_type !== 'trail_camera' && !['zone','corridor'].includes(selected.object_type)">Type<select v-model="subtype"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><template v-if="selected.object_type === 'trail_camera'"><label>Heading · degrees<input v-model.number="cameraHeading" type="number" min="0" max="360" /></label><label>Field of view · degrees<input v-model.number="cameraFov" type="number" min="1" max="179" /></label><label>Useful range · meters<input v-model.number="cameraRange" type="number" min="1" max="5000" /></label><div class="camera-history-list"><strong>Placement history</strong><p v-for="placement in (cameras.find(item => item.map_object_id === selected.id)?.history || [])" :key="placement.id">{{ placement.removed_at ? new Date(placement.installed_at).toLocaleDateString() + ' – ' + new Date(placement.removed_at).toLocaleDateString() : 'Current placement' }} · {{ Math.round(placement.heading_degrees) }}°</p></div></template><label>Notes<textarea v-model="notes" rows="5"></textarea></label><section class="attachment-list"><h3>Evidence attachments</h3><article v-for="attachment in attachments" :key="attachment.id"><img v-if="attachment.attachment_type === 'image'" :src="`${API}${attachment.media_url}`" :alt="attachment.caption || 'Evidence photo'" /><a v-else :href="`${API}${attachment.media_url}`" target="_blank" rel="noreferrer">{{ attachment.attachment_type === 'audio' ? 'Play audio evidence' : 'Open file' }}</a><p>{{ attachment.caption || attachment.source }}</p></article><label class="attachment-upload">{{ uploadingAttachment ? 'Uploading…' : '＋ Add photo, audio, or file' }}<input type="file" accept="image/jpeg,image/png,image/webp,audio/mpeg,audio/wav,application/pdf,text/plain" :disabled="uploadingAttachment" @change="uploadAttachment" /></label><input v-model="attachmentCaption" class="attachment-caption" placeholder="Attachment caption (optional)" /></section><div v-if="['Polygon','LineString'].includes(selected.geometry.type) && activeTool !== 'edit'" class="inspector-buttons"><button class="secondary-button" @click="beginGeometryEdit">Edit geometry</button></div><div v-if="selected.geometry.type === 'Point' && selected.object_type !== 'trail_camera'" class="inspector-buttons"><button class="secondary-button" @click="activeTool = 'move-object'">Move on map</button></div><div v-if="activeTool === 'edit'" class="inspector-buttons"><button class="primary" @click="finishGeometryEdit(true)">Save geometry</button><button class="secondary-button" @click="finishGeometryEdit(false)">Cancel</button></div><p class="inspector-meta">Added {{ new Date(selected.created_at).toLocaleString() }}</p><div class="inspector-buttons"><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="activeTool = 'move-camera'">Move on map</button><button v-if="activeTool !== 'edit'" class="primary" :disabled="saving" @click="saveSelected">{{ saving ? 'Saving…' : 'Save changes' }}</button><button v-if="selected.object_type === 'trail_camera'" class="danger-button" @click="deleteSelected">Deactivate</button><button v-else class="danger-button" @click="deleteSelected">Delete</button></div><p v-if="['move-camera','move-object'].includes(activeTool)" class="map-hint inline-map-hint">Tap the new object location</p></aside>
    </div>
    <footer class="surveyor-footer"><SurveyTimeline v-model="timelineWindow" /><span v-if="activeSession" class="active-session-status">SEARCH ACTIVE · {{ Math.round(sessionDistance()) }} m</span></footer>
  </main>
</template>
