function segmentNearest(point, start, end) {
  const dx = end[0] - start[0], dy = end[1] - start[1]
  const lengthSq = dx * dx + dy * dy
  const t = lengthSq ? Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSq)) : 0
  const coordinate = [start[0] + t * dx, start[1] + t * dy]
  return { coordinate, distance: Math.hypot(point[0] - coordinate[0], point[1] - coordinate[1]) }
}

function coordinatePairs(geometry) {
  const pairs = []
  function visit(value) {
    if (!Array.isArray(value)) return
    if (value.length >= 2 && value.slice(0, 2).every(Number.isFinite)) pairs.push(value.slice(0, 2))
    else value.forEach(visit)
  }
  visit(geometry?.coordinates)
  return pairs
}

function lineSegments(geometry) {
  const paths = []
  function walk(value) {
    if (!Array.isArray(value)) return
    if (value.length && Array.isArray(value[0]) && value[0].length >= 2 && value[0].slice(0, 2).every(Number.isFinite)) paths.push(value)
    else value.forEach(walk)
  }
  walk(geometry?.coordinates)
  return paths.flatMap(path => path.slice(1).map((point, index) => [path[index], point]))
}

export function createMapFeatureSnapper(map, getSettings, setTarget, threshold = 12) {
  return event => {
    const settings = getSettings()
    const screenPoint = [event.containerX, event.containerY]
    const bounds = [[screenPoint[0] - threshold, screenPoint[1] - threshold], [screenPoint[0] + threshold, screenPoint[1] + threshold]]
    let features = []
    try { features = map.queryRenderedFeatures(bounds) } catch { setTarget(null); return undefined }
    let best = null
    const accept = (candidate, coordinate, kind, authoritativeHydro = false) => {
      if (candidate.distance > threshold) return
      const preferred = !best || (authoritativeHydro && !best.authoritativeHydro && candidate.distance <= best.distance + 4) ||
        (!authoritativeHydro && best.authoritativeHydro && candidate.distance < best.distance - 4) ||
        (authoritativeHydro === best?.authoritativeHydro && candidate.distance < best.distance)
      if (preferred) {
        best = { ...candidate, coordinate, kind, authoritativeHydro }
      }
    }
    for (const feature of features) {
      const layerName = `${feature.layer?.id || ''} ${feature.sourceLayer || feature.layer?.['source-layer'] || ''}`.toLowerCase()
      const isUserGeometry = feature.source === 'surveyor-objects'
      const isRoad = /road|transport|highway|street/.test(layerName)
      const isTrail = /trail|path|track/.test(layerName)
      const isWater = /water|stream|river|canal|drain|hydro/.test(layerName)
      const isAuthoritativeHydro = layerName.includes('survey-hydro')
      const objectType = feature.properties?.object_type
      const isCamera = objectType === 'trail_camera'
      const isZone = objectType === 'zone' || feature.geometry?.type === 'Polygon'
      if (!(isUserGeometry ? (isCamera ? settings.cameras : isZone ? settings.zoneBoundaries : settings.objects) :
        (isRoad && settings.roads) || (isTrail && settings.trails) || (isWater && settings.waterways))) continue
      const kind = isUserGeometry ? (isCamera ? 'camera' : isZone ? 'zone_boundary' : 'object') : isWater ? 'waterway' : isTrail ? 'trail' : 'road'
      const coords = coordinatePairs(feature.geometry)
      if (feature.geometry?.type === 'Point' || feature.geometry?.type === 'MultiPoint') {
        for (const coordinate of coords) {
          const screen = map.project(coordinate)
          accept({ distance: Math.hypot(screen.x - screenPoint[0], screen.y - screenPoint[1]) }, coordinate, kind, isAuthoritativeHydro)
        }
        continue
      }
      for (const [start, end] of lineSegments(feature.geometry)) {
        const a = map.project(start), b = map.project(end)
        const nearest = segmentNearest(screenPoint, [a.x, a.y], [b.x, b.y])
        const coordinate = map.unproject(nearest.coordinate)
        accept({ distance: nearest.distance }, [coordinate.lng, coordinate.lat], kind, isAuthoritativeHydro)
      }
    }
    const snappedScreen = best ? map.project(best.coordinate) : null
    setTarget(best ? { x: snappedScreen.x, y: snappedScreen.y, coordinate: best.coordinate, kind: best.kind } : null)
    return best?.coordinate
  }
}
