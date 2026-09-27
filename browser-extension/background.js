importScripts('storage.js')

let activeSync = false
const AUTO_SYNC_ALARM = 'archie-facebook-auto-sync'

chrome.runtime.onInstalled.addListener(() => chrome.alarms.create('archie-facebook-poll', { periodInMinutes: 0.5 }))
chrome.runtime.onStartup.addListener(() => chrome.alarms.create('archie-facebook-poll', { periodInMinutes: 0.5 }))
chrome.runtime.onInstalled.addListener(configureAutoSync)
chrome.runtime.onStartup.addListener(configureAutoSync)
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.facebookAutoSyncCadence) configureAutoSync()
})

async function configureAutoSync() {
  const { facebookAutoSyncCadence = 'off' } = await chrome.storage.local.get('facebookAutoSyncCadence')
  const cadence = { hour: 60, three_hours: 180, twice_daily: 720 }[facebookAutoSyncCadence]
  if (cadence) chrome.alarms.create(AUTO_SYNC_ALARM, { periodInMinutes: cadence })
  else chrome.alarms.clear(AUTO_SYNC_ALARM)
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === 'archie-facebook-poll') pollForSync()
  if (alarm.name === AUTO_SYNC_ALARM) queueAutomaticSync()
})

async function queueAutomaticSync() {
  try {
    await jsonRequest('/api/facebook/sync', {})
    await pollForSync()
  } catch (error) {
    if (!String(error.message).includes('401') && !String(error.message).includes('Select at least one')) {
      console.warn('Archie Radar automatic Facebook sync:', error.message)
    }
  }
}

async function jsonRequest(path, body = null) {
  const response = await bridgeFetch(path, body ? { method: 'POST', body: JSON.stringify(body) } : {})
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.detail || `Archie Radar returned ${response.status}`)
  return result
}

async function hashImage(image) {
  try {
    const response = await fetch(image.url, { credentials: 'include', signal: AbortSignal.timeout(8000) })
    if (!response.ok) return image
    const bytes = await response.arrayBuffer()
    if (bytes.byteLength > 5_000_000) return image
    const digest = await crypto.subtle.digest('SHA-256', bytes)
    const sha256 = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
    return { ...image, sha256 }
  } catch { return image }
}

async function tabComplete(tabId, timeoutMs = 30000) {
  const existing = await chrome.tabs.get(tabId).catch(() => null)
  if (!existing) throw new Error('Facebook group tab was closed while loading')
  if (existing.status === 'complete') return
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      reject(new Error('Facebook group page timed out while loading'))
    }, timeoutMs)
    const listener = (changedId, info) => {
      if (changedId !== tabId || info.status !== 'complete') return
      clearTimeout(timeout)
      chrome.tabs.onUpdated.removeListener(listener)
      resolve()
    }
    chrome.tabs.onUpdated.addListener(listener)
  })
}

async function scanSubscription(group) {
  const tab = await chrome.tabs.create({ url: group.group_url, active: false })
  try {
    if (tab.status !== 'complete') await tabComplete(tab.id)
    await new Promise(resolve => setTimeout(resolve, 2500))
    let result
    try {
      result = await chrome.tabs.sendMessage(tab.id, { type: 'ARCHIE_SCAN_GROUP', group })
    } catch {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['facebook/postExtractor.js', 'facebook/groupScanner.js'] })
      await new Promise(resolve => setTimeout(resolve, 500))
      result = await chrome.tabs.sendMessage(tab.id, { type: 'ARCHIE_SCAN_GROUP', group })
    }
    if (result?.error) throw new Error(result.error)
    const posts = []
    for (const post of result?.posts || []) {
      const images = []
      for (const image of (post.images || []).slice(0, 3)) images.push(await hashImage(image))
      posts.push({ ...post, images })
      await new Promise(resolve => setTimeout(resolve, 180))
    }
    const batch = await jsonRequest('/api/facebook/ingest-batch', {
      sync_run_id: group.sync_run_id,
      group_subscription_id: group.id,
      scanned: result?.scanned || 0,
      parser_warning: result?.parser_warning || '',
      posts
    })
    return { ok: true, receipt: batch }
  } finally {
    await chrome.tabs.remove(tab.id).catch(() => {})
  }
}

async function pollForSync() {
  if (activeSync) return
  activeSync = true
  let jobId = null
  let errors = []
  try {
    const payload = await jsonRequest('/api/facebook/sync/next')
    const job = payload.job
    if (!job) return
    jobId = job.id
    for (const group of job.groups) {
      try {
        await scanSubscription({ ...group, sync_run_id: job.id })
      } catch (error) {
        errors.push(`${group.group_name}: ${error.message}`)
        await jsonRequest(`/api/facebook/sync/${job.id}/groups/${group.id}/fail`, {
          scanned: 0,
          parser_warning: error.message.includes('article') || error.message.includes('layout') ? error.message : '',
          error: error.message
        }).catch(() => {})
      }
      await new Promise(resolve => setTimeout(resolve, 1800 + Math.round(Math.random() * 900)))
    }
  } catch (error) {
    if (!String(error.message).includes('401')) console.warn('Archie Radar Facebook collector:', error.message)
  } finally {
    if (jobId) {
      await jsonRequest(`/api/facebook/sync/${jobId}/complete`, { error_summary: errors.join('\n') }).catch(error => {
        console.warn('Could not complete Facebook sync receipt:', error.message)
      })
    }
    activeSync = false
  }
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
})
