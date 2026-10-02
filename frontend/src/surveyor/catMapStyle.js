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
        if (match(identity, /poi|shop|restaurant|transit|station|address|housenumber|amenity|building/)) {
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
          map.setPaintProperty(layer.id, 'fill-color', paint.developed)
          map.setPaintProperty(layer.id, 'fill-opacity', 0.42)
        } else if (match(identity, /industrial|commercial/)) {
          map.setPaintProperty(layer.id, 'fill-color', '#e7e0d6')
          map.setPaintProperty(layer.id, 'fill-opacity', 0.42)
        }
      } else if (layer.type === 'line') {
        if (match(identity, /boundary|admin/)) {
          map.setPaintProperty(layer.id, 'line-opacity', 0.08)
        } else if (match(identity, /water|river|stream|canal/)) {
          map.setPaintProperty(layer.id, 'line-color', '#8db4bd')
          map.setPaintProperty(layer.id, 'line-opacity', 0.86)
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 7, 0.8, 13, 2.1, 16, 3.1])
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
  return { status: roads && water && labels ? 'ready' : 'degraded', roads, water, labels, natural }
}

export const CAT_MAP_PALETTE = paint
