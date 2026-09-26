<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const props = defineProps({ home: { type: Object, required: true }, match: { type: Object, required: true } })
const element = ref(null)
let map

onMounted(() => {
  map = new maplibregl.Map({ container: element.value, style: 'https://tiles.openfreemap.org/styles/positron',
    center: [props.match.longitude, props.match.latitude], zoom: 12, attributionControl: true, interactive: true })
  map.on('load', () => {
    const features = [
      { type: 'Feature', properties: { role: 'home' }, geometry: { type: 'Point', coordinates: [props.home.longitude, props.home.latitude] } },
      { type: 'Feature', properties: { role: 'target' }, geometry: { type: 'Point', coordinates: [props.match.longitude, props.match.latitude] } },
      { type: 'Feature', properties: { role: 'route' }, geometry: { type: 'LineString', coordinates: [[props.home.longitude, props.home.latitude], [props.match.longitude, props.match.latitude]] } }
    ]
    map.addSource('place-focus', { type: 'geojson', data: { type: 'FeatureCollection', features } })
    map.addLayer({ id: 'place-focus-line', type: 'line', source: 'place-focus', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': '#bd753e', 'line-width': 2, 'line-dasharray': [2, 2] } })
    map.addLayer({ id: 'place-focus-points', type: 'circle', source: 'place-focus', filter: ['==', ['geometry-type'], 'Point'], paint: {
      'circle-radius': ['match', ['get', 'role'], 'target', 8, 6], 'circle-color': ['match', ['get', 'role'], 'target', '#bd753e', '#314f41'],
      'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 2
    } })
    map.addLayer({ id: 'place-focus-labels', type: 'symbol', source: 'place-focus', filter: ['==', ['geometry-type'], 'Point'], layout: {
      'text-field': ['match', ['get', 'role'], 'target', 'ADDRESS', 'HOME'], 'text-size': 10, 'text-offset': [0, 1.3], 'text-allow-overlap': true
    }, paint: { 'text-color': '#273b30', 'text-halo-color': '#fffaf0', 'text-halo-width': 2 } })
    const bounds = new maplibregl.LngLatBounds([props.home.longitude, props.home.latitude], [props.match.longitude, props.match.latitude])
    map.fitBounds(bounds, { padding: { top: 38, bottom: 38, left: 38, right: 38 }, maxZoom: 14, duration: 0 })
  })
})

onBeforeUnmount(() => map?.remove())
</script>

<template><div ref="element" class="assistant-mini-map" aria-label="Map showing home and the selected address"></div></template>
