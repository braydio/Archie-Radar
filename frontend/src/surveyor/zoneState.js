export const SEARCH_FRESH_DAYS = 7
export const SEARCH_AGING_DAYS = 30

export function searchFreshness(object, now = new Date()) {
  if (object?.subtype !== 'searched') return 'unknown'
  const searchedAt = object.properties?.searched_at
  if (!searchedAt) return 'unknown'
  const ageDays = (now.getTime() - new Date(searchedAt).getTime()) / 86400000
  if (!Number.isFinite(ageDays) || ageDays < 0) return 'unknown'
  if (ageDays <= SEARCH_FRESH_DAYS) return 'fresh'
  if (ageDays <= SEARCH_AGING_DAYS) return 'aging'
  return 'stale'
}
