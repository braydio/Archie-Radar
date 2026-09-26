const EARTH_RADIUS = 6371008.8

export function destinationPoint(lon, lat, meters, bearing) {
  const angular = meters / EARTH_RADIUS, brng = bearing * Math.PI / 180
  const lat1 = lat * Math.PI / 180, lon1 = lon * Math.PI / 180
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(brng))
  const lon2 = lon1 + Math.atan2(Math.sin(brng) * Math.sin(angular) * Math.cos(lat1), Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2))
  return [lon2 * 180 / Math.PI, lat2 * 180 / Math.PI]
}

export function cameraConePolygon(placement) {
  const lon = Number(placement.longitude), lat = Number(placement.latitude)
  const heading = Number(placement.heading_degrees), fov = Number(placement.fov_degrees), range = Number(placement.range_meters)
  const ring = [[lon, lat]]
  for (let step = 0; step <= 24; step++) ring.push(destinationPoint(lon, lat, range, heading - fov / 2 + fov * step / 24))
  ring.push([lon, lat])
  return { type: 'Polygon', coordinates: [ring] }
}

export function cameraHandlePoints(placement) {
  const { longitude, latitude, heading_degrees: heading, fov_degrees: fov, range_meters: range } = placement
  const center = [Number(longitude), Number(latitude)]
  return {
    center,
    heading: destinationPoint(center[0], center[1], Number(range) * 1.45, Number(heading)),
    leftFov: destinationPoint(center[0], center[1], Number(range), Number(heading) - Number(fov) / 2),
    rightFov: destinationPoint(center[0], center[1], Number(range), Number(heading) + Number(fov) / 2),
    range: destinationPoint(center[0], center[1], Number(range), Number(heading))
  }
}
