const METERS_PER_MILE = 1609.344
const METERS_PER_FOOT = 0.3048

export const metersToFeet = meters => Number(meters || 0) / METERS_PER_FOOT
export const feetToMeters = feet => Number(feet || 0) * METERS_PER_FOOT
export const metersToMiles = meters => Number(meters || 0) / METERS_PER_MILE
export function formatDistance(meters) {
  const value = Number(meters || 0)
  if (value >= METERS_PER_MILE) return `${metersToMiles(value).toFixed(1)} mi`
  return `${Math.round(metersToFeet(value))} ft`
}
