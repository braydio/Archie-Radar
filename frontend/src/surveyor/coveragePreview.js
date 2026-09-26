// A local equirectangular approximation used only to show the user's draft.
// The authoritative buffer is calculated server-side in a projected CRS.
export function coveragePreviewGeometry(line, bufferMeters) {
  if (!line || line.type !== 'LineString' || line.coordinates.length < 2) return null
  const coordinates = line.coordinates
  const lat0 = coordinates.reduce((sum, point) => sum + point[1], 0) / coordinates.length
  const xScale = 111320 * Math.max(0.01, Math.cos(lat0 * Math.PI / 180))
  const yScale = 110574
  const points = coordinates.map(([lon, lat]) => [lon * xScale, lat * yScale])
  const halfWidth = Number(bufferMeters)
  const side = direction => points.map((point, index) => {
    const before = points[Math.max(0, index - 1)], after = points[Math.min(points.length - 1, index + 1)]
    const dx = after[0] - before[0], dy = after[1] - before[1]
    const length = Math.hypot(dx, dy) || 1
    let nx = -dy / length, ny = dx / length
    if (index > 0 && index < points.length - 1) {
      const previous = points[index - 1], next = points[index + 1]
      const a = [-(point[1] - previous[1]), point[0] - previous[0]]
      const b = [-(next[1] - point[1]), next[0] - point[0]]
      const al = Math.hypot(...a) || 1, bl = Math.hypot(...b) || 1
      const mx = a[0] / al + b[0] / bl, my = a[1] / al + b[1] / bl
      const ml = Math.hypot(mx, my) || 1
      const scale = Math.min(halfWidth * 2, halfWidth / Math.max(0.25, (mx / ml * nx + my / ml * ny)))
      nx = mx / ml; ny = my / ml
      return [(point[0] + nx * scale * direction) / xScale, (point[1] + ny * scale * direction) / yScale]
    }
    return [(point[0] + nx * halfWidth * direction) / xScale, (point[1] + ny * halfWidth * direction) / yScale]
  })
  const ring = [...side(1), ...side(-1).reverse()]
  if (ring.length) ring.push([...ring[0]])
  return { type: 'Polygon', coordinates: [ring] }
}
