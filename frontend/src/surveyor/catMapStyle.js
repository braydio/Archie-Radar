const paint = {
  forest: '#dfe7da', open: '#dfe7da', developed: '#ddd8cc', water: '#c9dde1', road: '#d6d0c1',
  major: '#a58e70', primary: '#baa37e', secondary: '#c7b794', boundary: '#899387', label: '#59635d', halo: '#f5f2ea', background: '#f3f0e7'
}

const match = (value, pattern) => pattern.test(value)

/** Style only semantic families recognized in the current vector style. */
export function applyCatMapStyle(map) {
  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    const identity = `${layer.id || ''} ${layer['source-layer'] || ''}`.toLowerCase()
    try {
      if (layer.type === 'background') {
        map.setPaintProperty(layer.id, 'background-color', paint.background)
        continue
      }
      if (layer.type === 'symbol') {
        if (match(identity, /housenumber|house_number|address/)) {
          map.setLayoutProperty(layer.id, 'visibility', 'visible')
          try { map.setLayerZoomRange(layer.id, 16, 24) } catch {}
          try { map.setLayoutProperty(layer.id, 'text-size', 10.5) } catch {}
          for (const [property, value] of Object.entries({ 'text-color': '#6b6256', 'text-halo-color': '#faf7ef', 'text-halo-width': 1.3, 'text-opacity': 0.82 })) try { map.setPaintProperty(layer.id, property, value) } catch {}
        } else if (match(identity, /poi|shop|restaurant|transit|station|amenity|building/)) {
          map.setLayoutProperty(layer.id, 'visibility', 'none')
        } else {
          map.setPaintProperty(layer.id, 'text-color', match(identity, /road|transport/ ) ? '#6f6d66' : paint.label)
          map.setPaintProperty(layer.id, 'text-halo-color', paint.halo)
          map.setPaintProperty(layer.id, 'text-halo-width', 1.4)
          map.setPaintProperty(layer.id, 'text-opacity', match(identity, /place|settlement|city|town|village/) ? 0.82 : 0.58)
        }
      } else if (layer.type === 'fill') {
        if (match(identity, /water/)) {
          map.setPaintProperty(layer.id, 'fill-color', paint.water)
          map.setPaintProperty(layer.id, 'fill-opacity', 0.92)
        } else if (match(identity, /park|wood|forest|grass|landcover/)) {
          map.setPaintProperty(layer.id, 'fill-color', paint.forest)
          map.setPaintProperty(layer.id, 'fill-opacity', 0.66)
        } else if (match(identity, /building/)) {
          map.setPaintProperty(layer.id, 'fill-color', '#d8d0c1')
          map.setPaintProperty(layer.id, 'fill-opacity', ['interpolate', ['linear'], ['zoom'], 14, 0.30, 16, 0.58, 18, 0.72])
          try { map.setPaintProperty(layer.id, 'fill-outline-color', '#a99f90') } catch {}
        } else if (match(identity, /industrial|commercial/)) {
          map.setPaintProperty(layer.id, 'fill-color', '#e7e0d6')
          map.setPaintProperty(layer.id, 'fill-opacity', 0.42)
        }
      } else if (layer.type === 'line') {
        if (match(identity, /fence|wall|barrier|hedge/)) {
          try { map.setLayerZoomRange(layer.id, 16, 24) } catch {}
          map.setPaintProperty(layer.id, 'line-color', match(identity, /hedge/) ? '#78896f' : '#7f8278')
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 16, 0.6, 19, 1.1])
          map.setPaintProperty(layer.id, 'line-opacity', 0.7)
        } else if (match(identity, /building|structure/)) {
          map.setPaintProperty(layer.id, 'line-color', '#a99f90')
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 15, 0.6, 19, 1.2])
          map.setPaintProperty(layer.id, 'line-opacity', 0.75)
        } else if (match(identity, /boundary|admin/)) {
          map.setPaintProperty(layer.id, 'line-opacity', 0.08)
        } else if (match(identity, /water|river|stream|canal|ditch|drain/)) {
          map.setPaintProperty(layer.id, 'line-color', '#8db4bd')
          map.setPaintProperty(layer.id, 'line-opacity', 0.86)
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 7, 0.8, 14, 1.2, 17, 2.2, 19, 3])
        } else if (match(identity, /service|driveway|parking_aisle|parking-aisle/)) {
          map.setPaintProperty(layer.id, 'line-color', '#c7bca9')
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 14, 0.7, 18, 2.2])
          map.setPaintProperty(layer.id, 'line-opacity', 0.82)
        } else if (match(identity, /footway|path|trail|track|pedestrian|steps/)) {
          map.setPaintProperty(layer.id, 'line-color', '#8d826d')
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 14, 0.7, 18, 1.8])
          map.setPaintProperty(layer.id, 'line-opacity', 0.8)
          try { map.setPaintProperty(layer.id, 'line-dasharray', [1.4, 1.2]) } catch {}
        } else if (match(identity, /motorway|trunk/)) {
          map.setPaintProperty(layer.id, 'line-color', paint.major)
          map.setPaintProperty(layer.id, 'line-opacity', 0.78)
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 7, 1.3, 12, 3.2, 16, 6.3])
        } else if (match(identity, /primary/)) {
          map.setPaintProperty(layer.id, 'line-color', paint.primary)
          map.setPaintProperty(layer.id, 'line-opacity', 0.78)
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 8, 1, 13, 2.8, 16, 5])
        } else if (match(identity, /secondary/)) {
          map.setPaintProperty(layer.id, 'line-color', paint.secondary)
          map.setPaintProperty(layer.id, 'line-opacity', 0.74)
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 9, 0.8, 14, 2.25, 16, 3.8])
        } else if (match(identity, /tertiary|minor|street|road|transport/)) {
          map.setPaintProperty(layer.id, 'line-color', paint.road)
          map.setPaintProperty(layer.id, 'line-opacity', 0.78)
        } else if (match(identity, /rail/)) {
          map.setPaintProperty(layer.id, 'line-color', '#8e9690')
          map.setPaintProperty(layer.id, 'line-opacity', 0.34)
        }
      }
    } catch { /* A style revision can omit a paint property; skip only that layer. */ }
  }
}

export function auditCatMapStyle(map) {
  const layers = map.getStyle()?.layers || []
  const ids = layers.map(layer => `${layer.id || ''} ${layer['source-layer'] || ''}`.toLowerCase())
  const has = regex => ids.some(id => regex.test(id))
  const roads = has(/road|transportation|highway/)
  const water = has(/water|river|lake|stream/)
  const labels = layers.some(layer => layer.type === 'symbol' && /place|road|water|label|name/.test(`${layer.id || ''} ${layer['source-layer'] || ''}`.toLowerCase()))
  const natural = has(/wood|forest|grass|meadow|park|landcover/)
  const baseSourceIds = [...new Set(layers.filter(layer => {
    const identity = `${layer.id || ''} ${layer['source-layer'] || ''}`.toLowerCase()
    return /road|transportation|highway|water|river|lake|stream|place|label|name/.test(identity)
  }).map(layer => layer.source).filter(Boolean))]
  return { status: roads && water && labels ? 'ready' : 'degraded', roads, water, labels, natural, buildings: has(/building|structure/), addresses: has(/housenumber|house_number|address/), paths: has(/footway|path|trail|track|pedestrian/), baseSourceIds }
}

export const CAT_MAP_PALETTE = paint
