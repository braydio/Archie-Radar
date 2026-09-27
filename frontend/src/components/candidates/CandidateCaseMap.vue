<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const props = defineProps({ caseData: { type: Object, required: true }, home: { type: Object, default: null } })
const element = ref(null)
let map

function features() {
  const output = []
  const current = props.caseData.current_location
  if (props.home?.latitude != null && props.home?.longitude != null) output.push({
    type: 'Feature', properties: { role: 'home', label: 'Home' },
    geometry: { type: 'Point', coordinates: [props.home.longitude, props.home.latitude] }
  })
  if (current?.map_latitude != null && current?.map_longitude != null) output.push({
    type: 'Feature', properties: { role: 'current', label: 'Current location' },
    geometry: { type: 'Point', coordinates: [current.map_longitude, current.map_latitude] }
  })
  for (const record of props.caseData.source_records || []) {
    const lat = record.map_latitude ?? record.latitude
    const lon = record.map_longitude ?? record.longitude
    if (lat == null || lon == null || record.post_id === current?.record_id) continue
    output.push({ type: 'Feature', properties: { role: 'history', label: record.holding_entity || record.custody_label || record.source_label },
      geometry: { type: 'Point', coordinates: [lon, lat] } })
  }
  for (const object of props.caseData.field_objects || []) {
    if (object.geometry) output.push({ type: 'Feature', properties: { role: 'field', label: object.name || object.subtype || object.object_type }, geometry: object.geometry })
  }
  return { type: 'FeatureCollection', features: output }
}

onMounted(() => {
  const all = features().features.flatMap(feature => feature.geometry.type === 'Point' ? [feature.geometry.coordinates] : [])
  const current = props.caseData.current_location
  const center = current?.map_latitude != null ? [current.map_longitude, current.map_latitude] : all[0] || [-79.1, 35.85]
  map = new maplibregl.Map({ container: element.value, style: 'https://tiles.openfreemap.org/styles/positron', center, zoom: 12, attributionControl: true })
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  map.on('load', () => {
    map.addSource('candidate-case', { type: 'geojson', data: features() })
    map.addLayer({ id: 'candidate-case-areas', type: 'fill', source: 'candidate-case', filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#547c6e', 'fill-opacity': 0.18 } })
    map.addLayer({ id: 'candidate-case-points', type: 'circle', source: 'candidate-case', filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': ['match', ['get', 'role'], 'current', 9, 'home', 7, 6],
        'circle-color': ['match', ['get', 'role'], 'current', '#bd753e', 'home', '#314f41', 'history', '#817e72', '#647c91'],
        'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2 } })
    map.addLayer({ id: 'candidate-case-labels', type: 'symbol', source: 'candidate-case', filter: ['==', ['geometry-type'], 'Point'],
      layout: { 'text-field': ['get', 'label'], 'text-size': 10, 'text-offset': [0, 1.35], 'text-optional': true },
      paint: { 'text-color': '#273b30', 'text-halo-color': '#fffaf0', 'text-halo-width': 2 } })
    if (all.length > 1) {
      const bounds = all.reduce((result, point) => result.extend(point), new maplibregl.LngLatBounds(all[0], all[0]))
      map.fitBounds(bounds, { padding: 48, maxZoom: 14, duration: 0 })
    }
  })
})

onBeforeUnmount(() => map?.remove())
</script>

<template><div ref="element" class="candidate-case-map" aria-label="Map showing home, current location, source history, and linked field observations"></div></template>
