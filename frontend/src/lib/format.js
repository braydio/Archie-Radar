export const SOURCE_LABELS = {
  pawboost: 'PawBoost',
  orange_county_found: 'Orange County',
  orange_county_24petconnect: 'Orange County',
  regional_24petconnect: '24PetConnect',
  durham_24petconnect: 'APS Durham',
  aps_durham_found: 'APS Durham community',
  chatham_24petconnect: 'Chatham County',
  wake_24petconnect: 'Wake County',
  wake_county_lostfound: 'Wake County',
  burlington_24petconnect: 'Burlington',
  pet911: 'Pet911',
  petkey: 'Petkey',
  facebook_bridge: 'Facebook capture',
  facebook_group: 'Facebook'
}

export function sourceLabel(value) {
  if (!value) return 'Source'
  return SOURCE_LABELS[value] || String(value).replaceAll('_', ' ').replace(/\b\w/g, m => m.toUpperCase())
}

export function statusLabel(value) {
  if (!value || value === 'unknown') return ''
  const labels = {
    found: 'Found',
    sighting: 'Sighting',
    shelter_intake: 'Shelter intake',
    found_with_finder: 'With finder'
  }
  return labels[value] || String(value).replaceAll('_', ' ').replace(/\b\w/g, m => m.toUpperCase())
}

export function relativeTime(value, now = Date.now()) {
  if (!value) return ''
  const parsed = new Date(value).getTime()
  if (!Number.isFinite(parsed)) return ''
  const seconds = Math.max(0, Math.round((now - parsed) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 14) return `${days}d ago`
  const weeks = Math.floor(days / 7)
  if (days < 60) return `${weeks}w ago`
  const months = Math.floor(days / 30)
  if (days < 730) return `${months}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

export function exactDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export function dateOnly(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })
}
