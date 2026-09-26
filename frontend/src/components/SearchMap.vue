<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { exactDate, relativeTime, sourceLabel, statusLabel } from '../lib/format.js'

const BASE_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const COUNTY_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2025/State_County/MapServer/12/query?where=STATE%20IN%20(%2737%27%2C%2751%27%2C%2745%27%2C%2747%27)&outFields=NAME%2CBASENAME%2CGEOID%2CSTATE&returnGeometry=true&outSR=4326&f=geojson"
const STATE_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2025/State_County/MapServer/8/query?where=STATE%20IN%20(%2737%27%2C%2751%27%2C%2745%27%2C%2747%27)&outFields=NAME%2CSTUSAB%2CGEOID%2CSTATE&returnGeometry=true&outSR=4326&f=geojson"
const CACHE_MS = 7 * 24 * 60 * 60 * 1000

export default {
  name: 'SearchMap',
  props: {
    posts: { type: Array, default: () => [] },
    config: { type: Object, default: null },
    reviewRadius: { type: Number, default: 25 }
  },
  setup(props) {
    const el = ref(null)
    const ready = ref(false)
    const labelsVisible = ref(true)
    const boundaryStatus = ref('loading')
    const radar = ref({ distance: 0, bearing: 0, direction: 'HOME', zoom: 10, scale: 'regional' })
    const probe = ref(null)
    const clusterList = ref(null)
    let map = null
    let popup = null
    let styleLabelLayers = []
    let mapFontStack = ['Noto Sans Regular']
    let resizeObserver = null

    const mappable = computed(() => props.posts.filter(p => p.map_latitude != null && p.map_longitude != null))
    const preciseCount = computed(() => mappable.value.filter(p => p.location_precision === 'exact').length)
    const approximateCount = computed(() => mappable.value.filter(p => p.location_precision === 'city').length)

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>'"]/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[ch]))
    }

    function safeHref(value) {
      try {
        const url = new URL(value)
        return ['http:', 'https:'].includes(url.protocol) ? escapeHtml(url.href) : ''
      } catch { return '' }
    }

    function radians(value) { return value * Math.PI / 180 }
    function degrees(value) { return value * 180 / Math.PI }

    function haversineMiles(aLat, aLng, bLat, bLng) {
      const R = 3958.7613
      const dLat = radians(bLat - aLat)
      const dLng = radians(bLng - aLng)
      const x = Math.sin(dLat / 2) ** 2 + Math.cos(radians(aLat)) * Math.cos(radians(bLat)) * Math.sin(dLng / 2) ** 2
      return 2 * R * Math.asin(Math.sqrt(x))
    }

    function bearingDegrees(aLat, aLng, bLat, bLng) {
      const y = Math.sin(radians(bLng - aLng)) * Math.cos(radians(bLat))
      const x = Math.cos(radians(aLat)) * Math.sin(radians(bLat)) - Math.sin(radians(aLat)) * Math.cos(radians(bLat)) * Math.cos(radians(bLng - aLng))
      return (degrees(Math.atan2(y, x)) + 360) % 360
    }

    function compassName(bearing) {
      const names = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
      return names[Math.round(bearing / 22.5) % 16]
    }

    function zoomScale(z) {
      if (z < 8.2) return 'regional'
      if (z < 10.3) return 'county'
      if (z < 12.2) return 'town'
      if (z < 14.2) return 'neighborhood'
      return 'street'
    }

    function updateRadar() {
      if (!map || !props.config) return
      const center = map.getCenter()
      const distance = haversineMiles(props.config.home_latitude, props.config.home_longitude, center.lat, center.lng)
      const bearing = bearingDegrees(props.config.home_latitude, props.config.home_longitude, center.lat, center.lng)
      radar.value = {
        distance,
        bearing,
        direction: distance < 0.25 ? 'HOME' : compassName(bearing),
        zoom: map.getZoom(),
        scale: zoomScale(map.getZoom())
      }
    }

    function circlePolygon(lng, lat, miles, points = 96) {
      const radiusKm = miles * 1.609344
      const earth = 6371.0088
      const angular = radiusKm / earth
      const lat1 = radians(lat)
      const lng1 = radians(lng)
      const coords = []
      for (let i = 0; i <= points; i++) {
        const brng = 2 * Math.PI * (i / points)
        const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(brng))
        const lng2 = lng1 + Math.atan2(Math.sin(brng) * Math.sin(angular) * Math.cos(lat1), Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2))
        coords.push([degrees(lng2), degrees(lat2)])
      }
      return coords
    }

    function distanceRingsGeoJSON() {
      if (!props.config) return { type: 'FeatureCollection', features: [] }
      const radius = Number(props.reviewRadius >= 500 ? 100 : props.reviewRadius || 25)
      const ringMiles = [...new Set([10, 25, radius].filter(v => v > 0 && v <= radius))]
      return {
        type: 'FeatureCollection',
        features: ringMiles.map(mi => ({
          type: 'Feature',
          properties: { miles: mi, outer: mi === radius },
          geometry: { type: 'Polygon', coordinates: [circlePolygon(props.config.home_longitude, props.config.home_latitude, mi)] }
        }))
      }
    }

    function postsGeoJSON() {
      return {
        type: 'FeatureCollection',
        features: mappable.value.map(post => ({
          type: 'Feature',
          id: post.id,
          properties: {
            id: post.id,
            rank: Math.max(1, props.posts.findIndex(item => item.id === post.id) + 1),
            title: post.name || `${statusLabel(post.status) || 'Found'} cat`,
            score: Math.round(Number(post.match_score || 0)),
            review_state: post.review_state || 'new',
            precision: post.location_precision || 'unknown',
            source: sourceLabel(post.source),
            status: statusLabel(post.status) || 'Found',
            location: post.location_text || '',
            distance: post.distance_from_home_miles == null ? '' : `${post.distance_is_approximate ? '~' : ''}${Number(post.distance_from_home_miles).toFixed(1)} mi`,
            time: post.posted_at || post.reported_at || post.first_seen_at || '',
            posted: post.posted_at || '',
            reported: post.reported_at || '',
            source_url: post.source_url || '',
            traits: (post.archie_trait_matches || []).slice(0, 4).join(' · ')
          },
          geometry: { type: 'Point', coordinates: [Number(post.map_longitude), Number(post.map_latitude)] }
        }))
      }
    }

    async function cachedGeoJSON(key, url) {
      try {
        const cached = JSON.parse(localStorage.getItem(key) || 'null')
        if (cached?.at && cached?.data && Date.now() - cached.at < CACHE_MS) return cached.data
      } catch {}
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), 3500)
      try {
        const response = await fetch(url, { mode: 'cors', signal: controller.signal })
        if (!response.ok) throw new Error(`boundary ${response.status}`)
        const data = await response.json()
        try { localStorage.setItem(key, JSON.stringify({ at: Date.now(), data })) } catch {}
        return data
      } finally {
        clearTimeout(timer)
      }
    }

    function classifyLayer(layer) {
      const id = `${layer.id || ''} ${layer['source-layer'] || ''}`.toLowerCase()
      return id
    }

    function setPaint(id, key, value) {
      try { map.setPaintProperty(id, key, value) } catch {}
    }

    function setLayout(id, key, value) {
      try { map.setLayoutProperty(id, key, value) } catch {}
    }

    function restyleBase() {
      if (!map) return
      const layers = map.getStyle()?.layers || []
      styleLabelLayers = []
      for (const layer of layers) {
        const id = classifyLayer(layer)
        const type = layer.type
        const declaredFont = layer?.layout?.['text-font']
        if (type === 'symbol' && Array.isArray(declaredFont) && declaredFont.every(item => typeof item === 'string')) {
          mapFontStack = declaredFont
        }
        if (type === 'background') {
          setPaint(layer.id, 'background-color', '#f3f0e7')
          continue
        }
        if (type === 'symbol') {
          if (/poi|amenity|shop|transit|station|housenumber|building/.test(id)) {
            setLayout(layer.id, 'visibility', 'none')
            continue
          }
          styleLabelLayers.push(layer.id)
          setPaint(layer.id, 'text-color', /road|transport/.test(id) ? '#6f6d66' : '#59635d')
          setPaint(layer.id, 'text-halo-color', '#f5f2ea')
          setPaint(layer.id, 'text-halo-width', 1.4)
          setPaint(layer.id, 'text-opacity', /place|settlement|city|town|village/.test(id) ? 0.82 : 0.58)
          continue
        }
        if (type === 'fill') {
          if (/water/.test(id)) {
            setPaint(layer.id, 'fill-color', '#c9dde1')
            setPaint(layer.id, 'fill-opacity', 0.92)
          } else if (/park|wood|forest|grass|landcover/.test(id)) {
            setPaint(layer.id, 'fill-color', '#dfe7da')
            setPaint(layer.id, 'fill-opacity', 0.66)
          } else if (/building/.test(id)) {
            setPaint(layer.id, 'fill-color', '#ddd8cc')
            setPaint(layer.id, 'fill-opacity', 0.42)
          } else if (/industrial|commercial/.test(id)) {
            setPaint(layer.id, 'fill-color', '#e7e0d6')
            setPaint(layer.id, 'fill-opacity', 0.42)
          }
          continue
        }
        if (type === 'line') {
          if (/boundary|admin/.test(id)) {
            setPaint(layer.id, 'line-opacity', 0.08)
          } else if (/water|river|stream|canal/.test(id)) {
            setPaint(layer.id, 'line-color', '#8db4bd')
            setPaint(layer.id, 'line-opacity', 0.86)
            setPaint(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 7, 0.8, 13, 2.1, 16, 3.1])
          } else if (/motorway|trunk/.test(id)) {
            setPaint(layer.id, 'line-color', '#a58e70')
            setPaint(layer.id, 'line-opacity', 0.78)
            setPaint(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 7, 1.3, 12, 3.2, 16, 6.3])
          } else if (/primary/.test(id)) {
            setPaint(layer.id, 'line-color', '#baa37e')
            setPaint(layer.id, 'line-opacity', 0.78)
            setPaint(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 8, 1.0, 13, 2.8, 16, 5.0])
          } else if (/secondary/.test(id)) {
            setPaint(layer.id, 'line-color', '#c7b794')
            setPaint(layer.id, 'line-opacity', 0.74)
            setPaint(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 9, 0.8, 14, 2.25, 16, 3.8])
          } else if (/tertiary|minor|street|road|transport/.test(id)) {
            setPaint(layer.id, 'line-color', '#d6d0c1')
            setPaint(layer.id, 'line-opacity', 0.78)
          } else if (/rail/.test(id)) {
            setPaint(layer.id, 'line-color', '#8e9690')
            setPaint(layer.id, 'line-opacity', 0.34)
          }
        }
      }
    }

    async function addBoundaryLayers() {
      if (!map || !map.isStyleLoaded()) return
      boundaryStatus.value = 'loading'
      try {
        const [counties, states] = await Promise.all([
          cachedGeoJSON('archie-map-counties-v1', COUNTY_URL),
          cachedGeoJSON('archie-map-states-v1', STATE_URL)
        ])
        if (!map.getSource('census-counties')) map.addSource('census-counties', { type: 'geojson', data: counties })
        if (!map.getSource('census-states')) map.addSource('census-states', { type: 'geojson', data: states })
        if (!map.getLayer('census-county-lines')) {
          map.addLayer({
            id: 'census-county-lines', type: 'line', source: 'census-counties',
            paint: {
              'line-color': '#52645d',
              'line-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.10, 9, 0.26, 12, 0.34],
              'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.45, 10, 1.15, 13, 1.6],
              'line-dasharray': [3, 3]
            }
          }, 'distance-ring-fill')
        }
        if (!map.getLayer('census-county-labels')) {
          map.addLayer({
            id: 'census-county-labels', type: 'symbol', source: 'census-counties', minzoom: 8.6,
            layout: {
              'text-field': ['coalesce', ['get', 'BASENAME'], ['get', 'NAME']],
              'text-size': ['interpolate', ['linear'], ['zoom'], 8.6, 9, 11, 11],
              'text-transform': 'uppercase',
              'text-letter-spacing': 0.09
            },
            paint: {
              'text-color': '#6f7c76', 'text-opacity': 0.45,
              'text-halo-color': '#f4f1e9', 'text-halo-width': 1.2
            }
          }, 'distance-ring-fill')
        }
        if (!map.getLayer('census-state-lines')) {
          map.addLayer({
            id: 'census-state-lines', type: 'line', source: 'census-states',
            paint: {
              'line-color': '#263a32',
              'line-opacity': 0.48,
              'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.1, 10, 2.0, 13, 2.5]
            }
          }, 'distance-ring-fill')
        }
        boundaryStatus.value = 'ready'
      } catch (e) {
        console.warn('Archie Radar boundary context unavailable', e)
        boundaryStatus.value = 'unavailable'
      }
    }

    function addRadarLayers() {
      if (!map || !props.config) return
      const home = [Number(props.config.home_longitude), Number(props.config.home_latitude)]
      if (!map.getSource('home-point')) map.addSource('home-point', { type: 'geojson', data: { type: 'Point', coordinates: home } })
      if (!map.getSource('distance-rings')) map.addSource('distance-rings', { type: 'geojson', data: distanceRingsGeoJSON() })
      if (!map.getSource('archie-posts')) map.addSource('archie-posts', { type: 'geojson', data: postsGeoJSON(), cluster: true, clusterRadius: 48, clusterMaxZoom: 14 })
      if (!map.getSource('probe-line')) map.addSource('probe-line', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })

      if (!map.getLayer('distance-ring-fill')) map.addLayer({
        id: 'distance-ring-fill', type: 'fill', source: 'distance-rings',
        filter: ['==', ['get', 'outer'], true],
        paint: { 'fill-color': '#d9b16e', 'fill-opacity': 0.035 }
      })
      if (!map.getLayer('distance-ring-lines')) map.addLayer({
        id: 'distance-ring-lines', type: 'line', source: 'distance-rings',
        paint: {
          'line-color': ['case', ['get', 'outer'], '#9b6e39', '#647b70'],
          'line-opacity': ['case', ['get', 'outer'], 0.62, 0.22],
          'line-width': ['case', ['get', 'outer'], 2.2, 1.0],
          'line-dasharray': [5, 4]
        }
      })
      if (!map.getLayer('probe-line')) map.addLayer({
        id: 'probe-line', type: 'line', source: 'probe-line',
        paint: { 'line-color': '#b45b35', 'line-width': 4.2, 'line-opacity': 0.9, 'line-dasharray': [2, 1.6] }
      })
      if (!map.getLayer('probe-point')) map.addLayer({
        id: 'probe-point', type: 'circle', source: 'probe-line',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 7, 'circle-color': '#f2c36f', 'circle-stroke-color': '#b45b35', 'circle-stroke-width': 3 }
      })
      if (!map.getLayer('probe-halo')) map.addLayer({
        id: 'probe-halo', type: 'circle', source: 'probe-line',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 15, 'circle-color': 'rgba(180,91,53,.10)', 'circle-stroke-color': '#b45b35', 'circle-stroke-width': 2, 'circle-stroke-opacity': .8 }
      })
      if (!map.getLayer('probe-label')) map.addLayer({
        id: 'probe-label', type: 'symbol', source: 'probe-line',
        filter: ['==', ['geometry-type'], 'Point'],
        layout: { 'text-field': 'PROBE', 'text-size': 10, 'text-offset': [0, 2.2], 'text-letter-spacing': .08 },
        paint: { 'text-color': '#8d3f23', 'text-halo-color': '#fffaf0', 'text-halo-width': 1.4 }
      })
      if (!map.getLayer('clusters')) map.addLayer({
        id: 'clusters', type: 'circle', source: 'archie-posts', filter: ['has', 'point_count'],
        paint: {
          'circle-color': '#273a32',
          'circle-radius': ['step', ['get', 'point_count'], 18, 8, 22, 20, 27],
          'circle-stroke-color': '#f7f3e9', 'circle-stroke-width': 3,
          'circle-opacity': 0.92
        }
      })
      if (!map.getLayer('cluster-count')) map.addLayer({
        id: 'cluster-count', type: 'symbol', source: 'archie-posts', filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': mapFontStack },
        paint: { 'text-color': '#ffffff' }
      })
      if (!map.getLayer('possible-halo')) map.addLayer({
        id: 'possible-halo', type: 'circle', source: 'archie-posts',
        filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'review_state'], 'possible']],
        paint: { 'circle-radius': 20, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#c96b42', 'circle-stroke-width': 4, 'circle-stroke-opacity': 0.85 }
      })
      if (!map.getLayer('candidate-points')) map.addLayer({
        id: 'candidate-points', type: 'circle', source: 'archie-posts', filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 7, 10, 11, 13, 14, 16],
          'circle-color': ['step', ['get', 'score'], '#d8ddd7', 48, '#e5bf78', 70, '#db7d55'],
          'circle-stroke-color': ['case', ['==', ['get', 'precision'], 'city'], '#43574e', '#fffdf6'],
          'circle-stroke-width': ['case', ['==', ['get', 'precision'], 'city'], 2, 3],
          'circle-opacity': ['case', ['==', ['get', 'precision'], 'city'], 0.80, 0.96]
        }
      })
      if (!map.getLayer('candidate-scores')) map.addLayer({
        id: 'candidate-scores', type: 'symbol', source: 'archie-posts', filter: ['!', ['has', 'point_count']],
        layout: { 'text-field': ['concat', '#', ['to-string', ['get', 'rank']]], 'text-size': 10.5, 'text-font': mapFontStack },
        paint: { 'text-color': '#24332d', 'text-halo-color': 'rgba(255,255,255,.5)', 'text-halo-width': 0.8 }
      })
      if (!map.getLayer('approx-symbol')) map.addLayer({
        id: 'approx-symbol', type: 'symbol', source: 'archie-posts',
        filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'precision'], 'city']],
        layout: { 'text-field': '≈', 'text-size': 10, 'text-offset': [1.45, -1.25] },
        paint: { 'text-color': '#43574e', 'text-halo-color': '#f7f3e9', 'text-halo-width': 1 }
      })
      if (!map.getLayer('home-halo')) map.addLayer({
        id: 'home-halo', type: 'circle', source: 'home-point',
        paint: { 'circle-radius': 17, 'circle-color': 'rgba(246,242,232,.85)', 'circle-stroke-color': '#24362f', 'circle-stroke-width': 2 }
      })
      if (!map.getLayer('home-core')) map.addLayer({
        id: 'home-core', type: 'circle', source: 'home-point',
        paint: { 'circle-radius': 7, 'circle-color': '#24362f', 'circle-stroke-color': '#f6f2e8', 'circle-stroke-width': 2 }
      })
      if (!map.getLayer('home-label')) map.addLayer({
        id: 'home-label', type: 'symbol', source: 'home-point', minzoom: 8.5,
        layout: { 'text-field': 'HOME', 'text-size': 10, 'text-offset': [0, 2.5], 'text-letter-spacing': 0.12 },
        paint: { 'text-color': '#24362f', 'text-halo-color': '#f6f2e8', 'text-halo-width': 1.4 }
      })
    }

    function updateData() {
      if (!map || !map.isStyleLoaded()) return
      const postSource = map.getSource('archie-posts')
      if (postSource) postSource.setData(postsGeoJSON())
      const rings = map.getSource('distance-rings')
      if (rings) rings.setData(distanceRingsGeoJSON())
      const home = map.getSource('home-point')
      if (home && props.config) home.setData({ type: 'Point', coordinates: [Number(props.config.home_longitude), Number(props.config.home_latitude)] })
    }

    function popupHtml(propsData, coords) {
      const score = Number(propsData.score || 0)
      const original = safeHref(propsData.source_url)
      const when = propsData.time ? relativeTime(propsData.time) : ''
      const postedExact = propsData.posted ? exactDate(propsData.posted) : ''
      const reportedExact = propsData.reported ? exactDate(propsData.reported) : ''
      const distance = propsData.distance || (() => {
        if (!props.config) return ''
        const mi = haversineMiles(props.config.home_latitude, props.config.home_longitude, coords[1], coords[0])
        return `${mi.toFixed(1)} mi`
      })()
      const bearing = props.config ? bearingDegrees(props.config.home_latitude, props.config.home_longitude, coords[1], coords[0]) : 0
      const direction = props.config ? compassName(bearing) : ''
      return `
        <div class="map-popup">
          <div class="map-popup-title"><strong>#${escapeHtml(propsData.rank || '')} · ${escapeHtml(propsData.status)} cat</strong><b>${score} signals</b></div>
          <div class="map-popup-route"><strong>${escapeHtml(distance)} ${direction ? direction : ''}</strong><span>from home</span></div>
          <span>${escapeHtml(propsData.source)}</span>
          ${postedExact ? `<span><strong>Posted</strong> ${escapeHtml(postedExact)}${when ? ` · ${escapeHtml(when)}` : ''}</span>` : when ? `<span>${escapeHtml(when)}</span>` : ''}
          ${reportedExact && reportedExact !== postedExact ? `<span><strong>Found/reported</strong> ${escapeHtml(reportedExact)}</span>` : ''}
          ${propsData.precision === 'city' ? '<span class="popup-approx">≈ city-level location</span>' : ''}
          ${propsData.location ? `<p>${escapeHtml(propsData.location)}</p>` : ''}
          ${propsData.traits ? `<div class="popup-traits"><span class="popup-trait">${escapeHtml(propsData.traits)}</span></div>` : ''}
          <div class="map-popup-links"><a href="#post-${escapeHtml(propsData.id)}">View card</a>${original ? `<a href="${original}" target="_blank" rel="noopener">Original ↗</a>` : ''}</div>
        </div>`
    }

    function setProbe(lng, lat, label = 'Map probe') {
      if (!map || !props.config) return
      const distance = haversineMiles(props.config.home_latitude, props.config.home_longitude, lat, lng)
      const bearing = bearingDegrees(props.config.home_latitude, props.config.home_longitude, lat, lng)
      clusterList.value = null
      probe.value = { lng, lat, distance, bearing, direction: compassName(bearing), label }
      const source = map.getSource('probe-line')
      if (source) source.setData({
        type: 'FeatureCollection',
        features: [
          { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [[props.config.home_longitude, props.config.home_latitude], [lng, lat]] } },
          { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [lng, lat] } }
        ]
      })
    }

    function clearProbe() {
      probe.value = null
      const source = map?.getSource('probe-line')
      if (source) source.setData({ type: 'FeatureCollection', features: [] })
    }

    function fit() {
      if (!map || !props.config) return
      const bounds = new maplibregl.LngLatBounds()
      bounds.extend([props.config.home_longitude, props.config.home_latitude])
      for (const post of mappable.value) bounds.extend([post.map_longitude, post.map_latitude])
      if (mappable.value.length) map.fitBounds(bounds, { padding: window.innerWidth < 700 ? 42 : 72, maxZoom: 12.5, duration: 450 })
      else map.easeTo({ center: [props.config.home_longitude, props.config.home_latitude], zoom: 9.6, duration: 350 })
    }

    function goHome() {
      if (!map || !props.config) return
      clearProbe()
      map.easeTo({ center: [props.config.home_longitude, props.config.home_latitude], zoom: 10.5, duration: 400 })
    }

    function zoomBy(amount) { map?.easeTo({ zoom: Math.max(5, Math.min(18, map.getZoom() + amount)), duration: 220 }) }

    function toggleLabels() {
      labelsVisible.value = !labelsVisible.value
      for (const id of styleLabelLayers) setLayout(id, 'visibility', labelsVisible.value ? 'visible' : 'none')
      if (map?.getLayer('census-county-labels')) setLayout('census-county-labels', 'visibility', labelsVisible.value ? 'visible' : 'none')
    }

    function installInteractions() {
      if (!map) return
      map.on('move', updateRadar)
      map.on('click', e => {
        const hits = map.queryRenderedFeatures(e.point, { layers: ['candidate-points', 'clusters'] })
        if (hits.length) return
        setProbe(e.lngLat.lng, e.lngLat.lat)
      })
      map.on('mouseenter', 'candidate-points', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'candidate-points', () => { map.getCanvas().style.cursor = '' })
      map.on('mouseenter', 'clusters', () => { map.getCanvas().style.cursor = 'zoom-in' })
      map.on('mouseleave', 'clusters', () => { map.getCanvas().style.cursor = '' })
      map.on('click', 'clusters', async e => {
        const feature = e.features?.[0]
        if (!feature) return
        const clusterId = feature.properties.cluster_id
        const source = map.getSource('archie-posts')
        try {
          const leaves = await source.getClusterLeaves(clusterId, 50, 0)
          clusterList.value = {
            clusterId,
            coords: [...feature.geometry.coordinates],
            total: Number(feature.properties.point_count || leaves.length),
            items: leaves.map(item => ({ ...item.properties })).sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
          }
          clearProbe()
        } catch {}
      })
      map.on('click', 'candidate-points', e => {
        const feature = e.features?.[0]
        if (!feature) return
        const coords = [...feature.geometry.coordinates]
        clusterList.value = null
        setProbe(coords[0], coords[1], `Candidate #${feature.properties.id}`)
        popup?.remove()
        popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true, maxWidth: '290px', offset: 18 })
          .setLngLat(coords)
          .setHTML(popupHtml(feature.properties, coords))
          .addTo(map)
      })
    }

    async function expandCluster() {
      if (!map || !clusterList.value) return
      const source = map.getSource('archie-posts')
      try {
        const zoom = await source.getClusterExpansionZoom(clusterList.value.clusterId)
        map.easeTo({ center: clusterList.value.coords, zoom: Math.min(15, Math.max(zoom, map.getZoom() + 1)), duration: 300 })
      } catch {}
    }

    function clearCluster() { clusterList.value = null }

    function ensureMap() {
      if (map || !props.config || !el.value) return
      map = new maplibregl.Map({
        container: el.value,
        style: BASE_STYLE,
        center: [props.config.home_longitude, props.config.home_latitude],
        zoom: 9.6,
        minZoom: 5.5,
        maxZoom: 18,
        attributionControl: false,
        cooperativeGestures: window.innerWidth < 760,
        dragRotate: false,
        pitchWithRotate: false
      })
      map.touchZoomRotate.disableRotation()
      map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
      map.on('load', async () => {
        restyleBase()
        addRadarLayers()
        installInteractions()
        addBoundaryLayers()
        updateData()
        ready.value = true
        updateRadar()
        nextTick(() => {
          map?.resize()
          window.setTimeout(fit, 80)
        })
      })
      map.on('error', event => {
        if (event?.error) console.warn('Map rendering warning', event.error)
      })
      resizeObserver = new ResizeObserver(() => map?.resize())
      resizeObserver.observe(el.value)
    }

    onMounted(ensureMap)
    watch(() => props.config, () => { ensureMap(); updateData() }, { deep: true })
    watch(() => props.posts, () => updateData(), { deep: true })
    watch(() => props.reviewRadius, () => updateData())
    onBeforeUnmount(() => {
      resizeObserver?.disconnect()
      popup?.remove()
      map?.remove()
      map = null
    })

    return {
      el, ready, labelsVisible, boundaryStatus, radar, probe, clusterList,
      mappable, preciseCount, approximateCount,
      fit, goHome, zoomBy, toggleLabels, clearProbe, expandCluster, clearCluster
    }
  }
}
</script>

<template>
  <section class="map-panel" v-if="config">
    <div class="map-heading">
      <div>
        <p class="eyebrow">SEARCH MAP</p>
        <h2>{{ mappable.length }} candidates · {{ preciseCount }} precise · {{ approximateCount }} approximate</h2>
        <p class="map-subtitle">Candidates, roads, waterways, county context, and distance from home.</p>
      </div>
      <div class="map-heading-actions">
        <button class="map-tool-button" @click="toggleLabels">{{ labelsVisible ? 'Labels on' : 'Labels off' }}</button>
        <button class="map-tool-button" @click="goHome">Home</button>
        <button class="map-tool-button strong" @click="fit">Fit reports</button>
      </div>
    </div>

    <div class="map-stage">
      <div class="map-canvas" ref="el"></div>
      <div class="map-reticle" aria-hidden="true"><span></span></div>

      <div class="map-radar-hud">
        <div class="radar-arrow" :style="{ transform: `rotate(${radar.bearing}deg)` }"><span>↑</span></div>
        <div class="radar-copy">
          <strong v-if="radar.distance < .25">Home centered</strong>
          <strong v-else>{{ radar.distance.toFixed(radar.distance < 10 ? 1 : 0) }} mi {{ radar.direction }} of home</strong>
          <span>{{ radar.scale }} view · center reticle</span>
        </div>
      </div>

      <div v-if="clusterList" class="map-cluster-hud">
        <div class="cluster-hud-top"><div><small>REPORT CLUSTER</small><strong>{{ clusterList.total }} reports at this location</strong></div><button @click="clearCluster" aria-label="Close report cluster">×</button></div>
        <div class="cluster-hud-list">
          <a v-for="item in clusterList.items" :key="item.id" :href="`#post-${item.id}`"><b>#{{ item.rank || item.id }}</b><span>{{ item.title || item.status }} · {{ item.source }}</span><em>{{ item.score }} signals</em></a>
        </div>
        <button class="map-tool-button strong cluster-zoom" @click="expandCluster">Zoom toward cluster</button>
      </div>

      <div v-if="probe" class="map-probe-hud">
        <i class="probe-link-dot"></i><div><small>{{ probe.label }} · linked to orange probe marker</small><strong>{{ probe.distance.toFixed(probe.distance < 10 ? 1 : 0) }} mi {{ probe.direction }}</strong><span>straight-line from home</span></div>
        <button @click="clearProbe" aria-label="Clear distance probe">×</button>
      </div>

      <div class="map-zoom-stack" aria-label="Map zoom controls">
        <button @click="zoomBy(1)" aria-label="Zoom in">+</button>
        <button @click="zoomBy(-1)" aria-label="Zoom out">−</button>
      </div>

      <div v-if="!mappable.length" class="map-empty"><strong>No candidate coordinates in this view</strong><span>Reports remain in the queue while exact geocoding catches up.</span></div>
    </div>

    <div class="map-footer">
      <div class="map-legend" aria-label="Map legend">
        <span><i class="legend-home"></i> Home</span>
        <span><i class="legend-dot high"></i> 70+ priority</span>
        <span><i class="legend-dot medium"></i> 48–69</span>
        <span><i class="legend-dot low"></i> Under 48</span>
        <span><i class="legend-approx">≈</i> City-level location</span>
        <span><i class="legend-county"></i> County</span>
        <span><i class="legend-state"></i> State</span>
      </div>
      <span class="boundary-note" :class="boundaryStatus">{{ boundaryStatus === 'ready' ? 'Census boundaries' : boundaryStatus === 'loading' ? 'Loading boundaries…' : 'Boundary overlay unavailable' }}</span>
    </div>
  </section>
</template>
