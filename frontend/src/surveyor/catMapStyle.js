const PALETTE = {
  woodland: '#788a73', water: '#87a9b0', wetland: '#a2c5c1', developed: '#d6d4ca',
  road: '#d8d1bd', minorRoad: '#e5dfd0', boundary: '#a8b3a5'
}

export function applyCatMapStyle(map) {
  for (const layer of map.getStyle()?.layers || []) {
    const id = String(layer.id || '').toLowerCase()
    const sourceLayer = String(layer['source-layer'] || '').toLowerCase()
    const key = `${id} ${sourceLayer}`
    try {
      if (layer.type === 'symbol') {
        const poi = /poi|shop|restaurant|transit|address|housenumber/.test(key)
        if (poi) map.setLayoutProperty(layer.id, 'visibility', 'none')
        else if (/place|road|water|park|state|county/.test(key)) {
          map.setPaintProperty(layer.id, 'text-color', '#5c685e')
          map.setPaintProperty(layer.id, 'text-halo-color', '#f0efe6')
          map.setPaintProperty(layer.id, 'text-halo-width', 1.1)
        }
      } else if (layer.type === 'fill') {
        if (/water|river|lake|ocean|stream/.test(key)) map.setPaintProperty(layer.id, 'fill-color', PALETTE.water)
        else if (/park|wood|forest|landcover|grass|nature|green/.test(key)) map.setPaintProperty(layer.id, 'fill-color', PALETTE.woodland)
        else if (/building|urban|residential|landuse/.test(key)) map.setPaintProperty(layer.id, 'fill-color', PALETTE.developed)
      } else if (layer.type === 'line') {
        if (/water|river|stream|canal/.test(key)) map.setPaintProperty(layer.id, 'line-color', PALETTE.water)
        else if (/highway|motorway|trunk/.test(key)) {
          map.setPaintProperty(layer.id, 'line-color', '#b88f66')
          map.setPaintProperty(layer.id, 'line-width', ['interpolate', ['linear'], ['zoom'], 8, 1.2, 14, 4.5])
        } else if (/road|street/.test(key)) map.setPaintProperty(layer.id, 'line-color', PALETTE.minorRoad)
        else if (/boundary/.test(key)) map.setPaintProperty(layer.id, 'line-color', PALETTE.boundary)
      }
    } catch { /* Styles vary by OpenFreeMap style version; one unsupported layer is harmless. */ }
  }
}

export const CAT_MAP_PALETTE = PALETTE
