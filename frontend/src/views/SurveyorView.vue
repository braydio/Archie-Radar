<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { TerraDraw, TerraDrawLineStringMode, TerraDrawPolygonMode, TerraDrawSelectMode } from 'terra-draw'
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter'
import { applyCatMapStyle } from '../surveyor/catMapStyle.js'

const API = import.meta.env.VITE_API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`
const mapEl = ref(null)
const objects = ref([])
const selected = ref(null)
const activeTool = ref('select')
const loading = ref(true)
const error = ref('')
const title = ref('')
const subtype = ref('sighting')
const zoneSubtype = ref('needs_search')
const notes = ref('')
const saving = ref(false)
let map
let draw
let resizeObserver

const types = [
  { value: 'sighting', label: 'Sighting' }, { value: 'possible_sighting', label: 'Possible sighting' },
  { value: 'checked_location', label: 'Checked location' }, { value: 'food_station', label: 'Food station' },
  { value: 'coyote', label: 'Coyote' }, { value: 'fox', label: 'Fox' }, { value: 'raccoon', label: 'Raccoon' },
  { value: 'culvert', label: 'Culvert' }, { value: 'dense_cover', label: 'Dense cover' }, { value: 'other', label: 'Other' }
]
const featureCollection = computed(() => ({
  type: 'FeatureCollection',
  features: objects.value.map(object => ({
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
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}

function refreshSource() {
  const source = map?.getSource('surveyor-objects')
  if (source) source.setData(featureCollection.value)
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
  const id = event.features?.[0]?.properties?.id
  selected.value = objects.value.find(object => object.id === Number(id)) || null
  if (selected.value) { title.value = selected.value.name || ''; subtype.value = selected.value.subtype || ''; notes.value = selected.value.notes || '' }
}

async function saveSelected() {
  if (!selected.value) return
  saving.value = true
  try {
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
  const response = await fetch(`${API}/api/surveyor/objects/${selected.value.id}`, { method: 'DELETE' })
  if (!response.ok) { error.value = 'Could not delete map object'; return }
  objects.value = objects.value.filter(item => item.id !== selected.value.id); selected.value = null; refreshSource()
}

function onMapClick(event) {
  if (activeTool.value === 'pin') createPin([event.lngLat.lng, event.lngLat.lat]).catch(err => { error.value = err.message })
}

onMounted(() => {
  map = new maplibregl.Map({
    container: mapEl.value, style: 'https://tiles.openfreemap.org/styles/positron',
    center: [-79.117282, 35.845701], zoom: 12, attributionControl: true
  })
  map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right')
  map.on('load', () => {
    applyCatMapStyle(map)
    draw = new TerraDraw({ adapter: new TerraDrawMapLibreGLAdapter({ map }), modes: [
      new TerraDrawSelectMode(), new TerraDrawPolygonMode(), new TerraDrawLineStringMode()
    ] })
    draw.start()
    draw.on('finish', id => persistDrawn(id).catch(err => { error.value = err.message }))
    map.addSource('surveyor-objects', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addLayer({ id: 'surveyor-zones-fill', type: 'fill', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Polygon'], paint: {
      'fill-color': ['match', ['get', 'subtype'], 'needs_search', '#dfad58', 'searched', '#667d69', 'known_cat_highway', '#58836f', 'wildlife_hotspot', '#9b7f61', '#75866e'],
      'fill-opacity': 0.17
    } })
    map.addLayer({ id: 'surveyor-lines', type: 'line', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'LineString'], paint: {
      'line-color': '#4c705a', 'line-width': 3, 'line-dasharray': ['case', ['==', ['get', 'object_type'], 'corridor'], ['literal', [2, 2]], ['literal', [1, 0]]]
    } })
    map.addLayer({ id: 'surveyor-points', type: 'circle', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Point'], paint: {
      'circle-radius': 8, 'circle-color': '#d66a16', 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2,
      'circle-opacity': 0.96
    } })
    map.addLayer({ id: 'surveyor-labels', type: 'symbol', source: 'surveyor-objects', filter: ['==', ['geometry-type'], 'Point'], layout: {
      'text-field': ['get', 'name'], 'text-offset': [0, 1.25], 'text-size': 12, 'text-anchor': 'top'
    }, paint: { 'text-color': '#24372e', 'text-halo-color': '#faf9f2', 'text-halo-width': 1.5 } })
    map.on('click', 'surveyor-points', chooseObject)
    map.on('mouseenter', 'surveyor-points', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'surveyor-points', () => { map.getCanvas().style.cursor = '' })
    map.on('click', onMapClick)
    loadObjects()
  })
  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(mapEl.value)
})

onBeforeUnmount(() => { resizeObserver?.disconnect(); draw?.stop(); map?.remove() })
</script>

<template>
  <main class="surveyor-page">
    <header class="surveyor-topbar">
      <div><p class="eyebrow">FIELD MAP · {{ objects.length }} OBJECTS</p><h1>Surveyor</h1></div>
      <div class="surveyor-actions"><span v-if="loading">Loading field data…</span><button :class="{ active: activeTool === 'select' }" @click="activeTool = 'select'; draw?.setMode('select')">Select</button><button :class="{ active: activeTool === 'pin' }" @click="activeTool = 'pin'; draw?.setMode('select')">＋ Pin</button><button :class="{ active: activeTool === 'zone' }" @click="activeTool = 'zone'; draw?.setMode('polygon')">Zone</button><button :class="{ active: activeTool === 'line' }" @click="activeTool = 'line'; draw?.setMode('linestring')">Line</button></div>
    </header>
    <p v-if="error" class="surveyor-error">{{ error }}</p>
    <div class="surveyor-workspace">
      <aside class="surveyor-tools"><p>TOOLS</p><button :class="{ active: activeTool === 'select' }" @click="activeTool = 'select'; draw?.setMode('select')">↖<span>Select</span></button><button :class="{ active: activeTool === 'pin' }" @click="activeTool = 'pin'; draw?.setMode('select')">⌖<span>Pin</span></button><button :class="{ active: activeTool === 'zone' }" @click="activeTool = 'zone'; draw?.setMode('polygon')">▱<span>Zone</span></button><button :class="{ active: activeTool === 'line' }" @click="activeTool = 'line'; draw?.setMode('linestring')">⌁<span>Line</span></button></aside>
      <section class="surveyor-map-shell"><div ref="mapEl" class="surveyor-map"></div><div v-if="activeTool === 'pin'" class="map-hint">Choose a marker type, then tap the map</div><select v-if="activeTool === 'pin'" v-model="subtype" class="pin-type-picker"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select><select v-if="activeTool === 'zone'" v-model="zoneSubtype" class="pin-type-picker"><option value="searched">Searched</option><option value="needs_search">Needs search</option><option value="needs_recheck">Needs re-check</option><option value="known_cat_highway">Known cat highway</option><option value="wildlife_hotspot">Wildlife hotspot</option><option value="likely_shelter">Likely shelter</option><option value="dog_territory">Dog territory</option><option value="private_no_access">Private / no access</option></select></section>
      <aside v-if="selected" class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">{{ selected.object_type }} · #{{ selected.id }}</p><h2>Field object</h2></div><button aria-label="Close inspector" @click="selected = null">×</button></div><label>Name<input v-model="title" maxlength="180" /></label><label>Type<select v-model="subtype"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>Notes<textarea v-model="notes" rows="5"></textarea></label><p class="inspector-meta">Added {{ new Date(selected.created_at).toLocaleString() }}</p><div class="inspector-buttons"><button class="primary" :disabled="saving" @click="saveSelected">{{ saving ? 'Saving…' : 'Save changes' }}</button><button class="danger-button" @click="deleteSelected">Delete</button></div></aside>
    </div>
    <footer class="surveyor-footer"><span>Field journal map</span><span>{{ activeTool === 'pin' ? 'Pin tool active' : 'Select or explore' }}</span><span>Surveyor v1 · Phase 1</span></footer>
  </main>
</template>
