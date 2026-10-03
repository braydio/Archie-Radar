const COUNTY_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2025/State_County/MapServer/12/query?where=STATE%20IN%20(%2737%27%2C%2751%27%2C%2745%27%2C%2747%27)&outFields=NAME%2CBASENAME%2CGEOID%2CSTATE&returnGeometry=true&outSR=4326&f=geojson"
const STATE_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2025/State_County/MapServer/8/query?where=STATE%20IN%20(%2737%27%2C%2751%27%2C%2745%27%2C%2747%27)&outFields=NAME%2CSTUSAB%2CGEOID%2CSTATE&returnGeometry=true&outSR=4326&f=geojson"
const CACHE_MS = 7 * 24 * 60 * 60 * 1000
const empty = () => ({ type: 'FeatureCollection', features: [] })

export function createEnvironmentLayers({ map, api, getTimeline, onStatus, onSelect, isPlacementMode = () => false }) {
  let timer, controller, destroyed = false, installed = false, currentSettings = {}
  const statuses = { hydrography: 'off', wetlands: 'off', boundaries: 'loading', wildlife: 'off', landcover: 'ready' }
  const providerHealth = { wetlands: 'ready', boundaries: 'loading', landcover: 'ready' }
  const listeners = []
  const setStatus = (key, value) => { statuses[key] = value; onStatus({ ...statuses }) }
  const click = event => {
    const feature = event.features?.[0]
    if (!feature) return
    event.originalEvent?.stopPropagation?.()
    onSelect({ ...feature, properties: { ...feature.properties, inspection_coordinates: [event.lngLat.lng, event.lngLat.lat] } })
  }
  const boundaries = async (key, url, force = false) => {
    if (!force) try {
      const cached = JSON.parse(localStorage.getItem(key) || 'null')
      if (cached?.at && cached.data && Date.now() - cached.at < CACHE_MS) return cached.data
    } catch {}
    const aborter = new AbortController(), timeout = setTimeout(() => aborter.abort(), 3500)
    try {
      const response = await fetch(url, { mode: 'cors', signal: aborter.signal })
      if (!response.ok) throw new Error(`Census ${response.status}`)
      const data = await response.json()
      try { localStorage.setItem(key, JSON.stringify({ at: Date.now(), data })) } catch {}
      return data
    } finally { clearTimeout(timeout) }
  }
  function firstBaseLabelLayer() { return map.getStyle()?.layers?.find(layer => layer.type === 'symbol')?.id }
  function addLayer(layer, before) { if (!map.getLayer(layer.id)) map.addLayer(layer, before) }
  async function loadBoundaries({ force = false } = {}) {
    if (!installed || destroyed) return
    setStatus('boundaries', 'loading')
    try {
      const [counties, states] = await Promise.all([boundaries('archie-map-counties-v1', COUNTY_URL, force), boundaries('archie-map-states-v1', STATE_URL, force)])
      if (destroyed) return
      for (const feature of counties.features || []) feature.properties = { ...feature.properties, provider: 'U.S. Census TIGERweb', feature_type: 'county', name: feature.properties?.BASENAME || feature.properties?.NAME }
      for (const feature of states.features || []) feature.properties = { ...feature.properties, provider: 'U.S. Census TIGERweb', feature_type: 'state', name: feature.properties?.NAME || feature.properties?.STUSAB }
      map.getSource('survey-county-source')?.setData(counties); map.getSource('survey-state-source')?.setData(states)
      providerHealth.boundaries = 'ready'
      setStatus('boundaries', currentSettings.boundaries ? 'ready' : 'off')
    } catch { providerHealth.boundaries = 'unavailable'; setStatus('boundaries', currentSettings.boundaries ? 'unavailable' : 'off') }
  }
  async function install(settings) {
    if (installed || destroyed) return
    currentSettings = settings
    installed = true
    const belowLabels = firstBaseLabelLayer()
    map.addSource('annual-landcover-source', { type: 'raster', tileSize: 256, attribution: 'Annual NLCD · 2025 · USGS/MRLC', tiles: [
      'https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wms?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=Land-Cover-Native_conus_year_data&STYLES=&FORMAT=image/png&TRANSPARENT=TRUE&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&TIME=2025-01-01T00:00:00Z'
    ] })
    addLayer({ id: 'annual-landcover', type: 'raster', source: 'annual-landcover-source', paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.22, 13, 0.20, 15, 0.12, 17, 0.04, 18, 0] } }, belowLabels)
    map.addSource('survey-wetlands-source', { type: 'raster', tileSize: 256, attribution: 'USFWS National Wetlands Inventory', tiles: [
      'https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/export?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png32&transparent=true&layers=show:0&f=image'
    ] })
    addLayer({ id: 'survey-wetlands', type: 'raster', source: 'survey-wetlands-source', minzoom: 10, paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 10, 0.26, 14, 0.20, 16, 0.10, 18, 0.04] } }, belowLabels)
    map.addSource('survey-hydro-streams', { type: 'geojson', data: empty() })
    map.addSource('survey-hydro-waterbodies', { type: 'geojson', data: empty() })
    map.addSource('survey-wildlife', { type: 'geojson', data: empty(), cluster: true, clusterRadius: 35, clusterMaxZoom: 13 })
    addLayer({ id: 'survey-hydro-waterbodies-fill', type: 'fill', source: 'survey-hydro-waterbodies', paint: { 'fill-color': '#bfd6dc', 'fill-opacity': 0.55 } }, belowLabels)
    addLayer({ id: 'survey-hydro-waterbodies-outline', type: 'line', source: 'survey-hydro-waterbodies', paint: { 'line-color': '#789fa7', 'line-width': 1 } }, belowLabels)
    addLayer({ id: 'survey-hydro-streams-line', type: 'line', source: 'survey-hydro-streams', paint: { 'line-color': '#6f9ca6', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.2, 14, 2.8] } }, belowLabels)
    addLayer({ id: 'survey-hydro-stream-labels', type: 'symbol', source: 'survey-hydro-streams', minzoom: 11, layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'], 'text-size': 10 }, paint: { 'text-color': '#527c85', 'text-halo-color': '#f5f3e9', 'text-halo-width': 1.2 } })
    addLayer({ id: 'survey-wildlife-clusters', type: 'circle', source: 'survey-wildlife', filter: ['has', 'point_count'], paint: { 'circle-radius': ['step', ['get', 'point_count'], 14, 10, 18, 40, 23], 'circle-color': '#7e684d', 'circle-opacity': .86, 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 1.5 } })
    addLayer({ id: 'survey-wildlife-cluster-count', type: 'symbol', source: 'survey-wildlife', filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11 }, paint: { 'text-color': '#fffaf0' } })
    addLayer({ id: 'survey-wildlife-points', type: 'circle', source: 'survey-wildlife', filter: ['!', ['has', 'point_count']], paint: {
      'circle-radius': 5, 'circle-color': ['match', ['get', 'species_key'], 'coyote', '#bb7047', 'red_fox', '#c45d3d', 'gray_fox', '#77766d', 'bobcat', '#bc9b63', 'raccoon', '#596a72', '#7e8c52'],
      'circle-opacity': ['case', ['==', ['get', 'geoprivacy'], 'obscured'], 0.55, 0.82], 'circle-stroke-color': '#fffaf0', 'circle-stroke-width': 1.5
    } })
    map.addSource('survey-county-source', { type: 'geojson', data: empty() }); map.addSource('survey-state-source', { type: 'geojson', data: empty() })
    addLayer({ id: 'survey-county-lines', type: 'line', source: 'survey-county-source', maxzoom: 15, paint: { 'line-color': '#52645d', 'line-opacity': ['interpolate', ['linear'], ['zoom'], 6, .10, 9, .26, 12, .34, 13, .12, 15, 0], 'line-width': ['interpolate', ['linear'], ['zoom'], 6, .45, 10, 1.15, 13, 1.6], 'line-dasharray': [3, 3] } })
    addLayer({ id: 'survey-county-labels', type: 'symbol', source: 'survey-county-source', minzoom: 8.6, maxzoom: 15, layout: { 'text-field': ['coalesce', ['get', 'BASENAME'], ['get', 'NAME']], 'text-size': ['interpolate', ['linear'], ['zoom'], 8.6, 9, 11, 11], 'text-transform': 'uppercase', 'text-letter-spacing': .09 }, paint: { 'text-color': '#6f7c76', 'text-opacity': ['interpolate', ['linear'], ['zoom'], 9, .45, 13, .16, 15, 0], 'text-halo-color': '#f4f1e9', 'text-halo-width': 1.2 } })
    addLayer({ id: 'survey-state-lines', type: 'line', source: 'survey-state-source', maxzoom: 13, paint: { 'line-color': '#263a32', 'line-opacity': .48, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.1, 10, 2, 13, 2.5] } })
    const clickIds = ['survey-hydro-streams-line', 'survey-hydro-waterbodies-fill', 'survey-hydro-waterbodies-outline', 'survey-hydro-stream-labels', 'survey-wildlife-points', 'survey-county-lines', 'survey-county-labels', 'survey-state-lines']
    for (const id of clickIds) { map.on('click', id, click); listeners.push(['click', id, click]) }
    const onEnter = () => { map.getCanvas().style.cursor = isPlacementMode() ? 'crosshair' : 'pointer' }, onLeave = () => { map.getCanvas().style.cursor = isPlacementMode() ? 'crosshair' : '' }
    for (const id of [...clickIds, 'survey-wildlife-clusters']) { map.on('mouseenter', id, onEnter); map.on('mouseleave', id, onLeave); listeners.push(['mouseenter', id, onEnter], ['mouseleave', id, onLeave]) }
    const clusterClick = event => {
      const feature = event.features?.[0]
      if (!feature) return
      map.getSource('survey-wildlife').getClusterExpansionZoom(feature.properties.cluster_id, (error, zoom) => { if (!error) map.easeTo({ center: feature.geometry.coordinates, zoom }) })
    }
    map.on('click', 'survey-wildlife-clusters', clusterClick); listeners.push(['click', 'survey-wildlife-clusters', clusterClick])
    const onMove = () => refreshViewport(currentSettings)
    map.on('moveend', onMove); listeners.push(['moveend', null, onMove])
    applyVisibility(settings)
    loadBoundaries()
    refreshViewport(settings)
  }
  function applyVisibility(nextSettings) {
    const previous = currentSettings
    currentSettings = nextSettings
    const entries = [['annual-landcover', nextSettings.landcover], ['survey-wetlands', nextSettings.wetlands], ['survey-county-lines', nextSettings.boundaries], ['survey-county-labels', nextSettings.boundaries], ['survey-state-lines', nextSettings.boundaries], ['survey-hydro-streams-line', nextSettings.hydrography], ['survey-hydro-waterbodies-fill', nextSettings.hydrography], ['survey-hydro-waterbodies-outline', nextSettings.hydrography], ['survey-hydro-stream-labels', nextSettings.hydrography], ['survey-wildlife-points', nextSettings.wildlife], ['survey-wildlife-clusters', nextSettings.wildlife], ['survey-wildlife-cluster-count', nextSettings.wildlife]]
    for (const [id, enabled] of entries) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none')
    setStatus('landcover', nextSettings.landcover ? providerHealth.landcover : 'off')
    setStatus('wetlands', nextSettings.wetlands ? providerHealth.wetlands : 'off')
    setStatus('boundaries', nextSettings.boundaries ? providerHealth.boundaries : 'off')
    const changed = !previous || previous.hydrography !== nextSettings.hydrography || previous.wildlife !== nextSettings.wildlife || JSON.stringify(previous.wildlifeSpecies) !== JSON.stringify(nextSettings.wildlifeSpecies)
    if (changed) refreshViewport(nextSettings)
  }
  function refreshViewport(nextSettings = currentSettings, force = false) {
    currentSettings = nextSettings
    clearTimeout(timer); controller?.abort()
    timer = setTimeout(async () => {
      if (destroyed || !installed || !map.getSource('survey-hydro-streams')) return
      controller = new AbortController()
      const signal = controller.signal, bounds = map.getBounds(), zoom = map.getZoom()
      const params = new URLSearchParams({ west: bounds.getWest().toFixed(4), south: bounds.getSouth().toFixed(4), east: bounds.getEast().toFixed(4), north: bounds.getNorth().toFixed(4) })
      const requests = []
      if (!nextSettings.hydrography) setStatus('hydrography', 'off')
      else if (zoom < 8) setStatus('hydrography', 'zoom_in')
      else { setStatus('hydrography', 'loading'); const hydroParams = new URLSearchParams(params); if (force) hydroParams.set('force', 'true'); requests.push(fetch(`${api}/api/surveyor/environment/hydrography?${hydroParams}`, { signal }).then(r => { if (!r.ok) throw new Error(); return r.json() }).then(data => { if (signal.aborted) return; map.getSource('survey-hydro-streams')?.setData(data.streams); map.getSource('survey-hydro-waterbodies')?.setData(data.waterbodies); setStatus('hydrography', data.degraded_layers?.length ? 'degraded' : 'ready') }).catch(() => { if (!signal.aborted) setStatus('hydrography', 'degraded') })) }
      const selected = Object.entries(nextSettings.wildlifeSpecies || {}).filter(([, enabled]) => enabled).map(([key]) => key)
      if (!nextSettings.wildlife) { map.getSource('survey-wildlife')?.setData(empty()); setStatus('wildlife', 'off') }
      else if (!selected.length) { map.getSource('survey-wildlife')?.setData(empty()); setStatus('wildlife', 'select_species') }
      else if (zoom < 9) { map.getSource('survey-wildlife')?.setData(empty()); setStatus('wildlife', 'zoom_in') }
      else {
        const timeline = getTimeline(), from = timeline?.preset === 'all' ? '2000-01-01' : new Date(timeline.from).toISOString().slice(0, 10), to = timeline?.preset === 'all' ? new Date().toISOString().slice(0, 10) : new Date(timeline.to).toISOString().slice(0, 10)
        params.set('from_date', from); params.set('to_date', to); selected.forEach(key => params.append('species', key)); if (force) params.set('force', 'true')
        setStatus('wildlife', 'loading'); requests.push(fetch(`${api}/api/surveyor/environment/wildlife?${params}`, { signal }).then(r => { if (!r.ok) throw new Error(); return r.json() }).then(data => { if (!signal.aborted) { map.getSource('survey-wildlife')?.setData(data); setStatus('wildlife', 'ready') } }).catch(() => { if (!signal.aborted) setStatus('wildlife', 'degraded') }))
      }
      await Promise.all(requests)
    }, 350)
  }
  function retry(providerKey) {
    if (!installed) return
    if (providerKey === 'boundaries') loadBoundaries({ force: true })
    else if (providerKey === 'hydrography' || providerKey === 'wildlife') refreshViewport(currentSettings, true)
  }
  function reportFailure(providerKey) {
    if (!Object.hasOwn(providerHealth, providerKey)) return
    providerHealth[providerKey] = 'degraded'
    if (currentSettings[providerKey]) setStatus(providerKey, 'degraded')
  }
  function destroy() { destroyed = true; clearTimeout(timer); controller?.abort(); for (const [event, layer, handler] of listeners) map.off(event, ...(layer ? [layer, handler] : [handler])) }
  return { install, applyVisibility, refreshViewport, retry, reportFailure, destroy }
}
