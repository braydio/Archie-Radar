const KEY = 'archie-radar-surveyor-location-focus'

export function setLocationFocus(value) {
  try { sessionStorage.setItem(KEY, JSON.stringify(value)) } catch {}
}

export function getLocationFocus() {
  try { return JSON.parse(sessionStorage.getItem(KEY) || 'null') } catch { return null }
}

export function clearLocationFocus() {
  try { sessionStorage.removeItem(KEY) } catch {}
}
