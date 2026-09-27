const DEFAULT_API = 'http://127.0.0.1:8000'

async function getConfig() {
  const value = await chrome.storage.local.get(['archieRadarApi', 'facebookBridgeToken'])
  return { api: (value.archieRadarApi || DEFAULT_API).replace(/\/$/, ''), token: value.facebookBridgeToken || '' }
}

function bridgeHeaders(token) {
  return { 'Content-Type': 'application/json', 'X-Archie-Facebook-Token': token }
}

async function bridgeFetch(path, options = {}) {
  const { api, token } = await getConfig()
  if (!token) throw new Error('Pair this browser with Archie Radar first.')
  return fetch(`${api}${path}`, { ...options, headers: { ...bridgeHeaders(token), ...(options.headers || {}) } })
}
