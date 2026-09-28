importScripts('storage.js')

async function jsonRequest(path, body = null) {
  const response = await bridgeFetch(path, body ? { method: 'POST', body: JSON.stringify(body) } : {})
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.detail || `Archie Radar returned ${response.status}`)
  return result
}

async function handoffFacebookSession() {
  const cookies = await chrome.cookies.getAll({ domain: 'facebook.com' })
  if (!cookies.some(cookie => cookie.name === 'c_user')) {
    throw new Error('Sign in to Facebook in this browser first.')
  }
  return jsonRequest('/api/facebook/session/import', { cookies })
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'ARCHIE_ADD_GROUP') {
    jsonRequest('/api/facebook/groups', message.group)
      .then(group => sendResponse({ ok: true, group }))
      .catch(error => sendResponse({ ok: false, error: error.message }))
    return true
  }

  if (message?.type === 'ARCHIE_TEST_PAIR') {
    jsonRequest('/api/facebook/bridge/status')
      .then(result => sendResponse({ ok: true, result }))
      .catch(error => sendResponse({ ok: false, error: error.message }))
    return true
  }

  if (message?.type === 'ARCHIE_HANDOFF_SESSION') {
    handoffFacebookSession()
      .then(result => sendResponse({ ok: true, result }))
      .catch(error => sendResponse({ ok: false, error: error.message }))
    return true
  }
})
