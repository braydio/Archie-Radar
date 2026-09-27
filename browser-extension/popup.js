const apiInput = document.querySelector('#api')
const tokenInput = document.querySelector('#token')
const status = document.querySelector('#status')
const cadenceInput = document.querySelector('#cadence')

async function load() {
  const config = await chrome.storage.local.get(['archieRadarApi', 'facebookBridgeToken', 'facebookAutoSyncCadence'])
  apiInput.value = config.archieRadarApi || 'http://127.0.0.1:8000'
  tokenInput.value = config.facebookBridgeToken || ''
  cadenceInput.value = config.facebookAutoSyncCadence || 'off'
  if (tokenInput.value) status.textContent = 'This browser has a saved pairing. Check connection…'
}

document.querySelector('#save').addEventListener('click', async () => {
  status.textContent = 'Connecting…'
  try {
    const api = apiInput.value.trim().replace(/\/$/, '')
    const origin = new URL(api).origin
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] })
    if (!granted) throw new Error('Allow the extension to connect to this Archie Radar server.')
    await chrome.storage.local.set({ archieRadarApi: api, facebookBridgeToken: tokenInput.value.trim(), facebookAutoSyncCadence: cadenceInput.value })
    const result = await chrome.runtime.sendMessage({ type: 'ARCHIE_TEST_PAIR' })
    if (!result?.ok) throw new Error(result?.error || 'Pairing failed')
    status.textContent = 'Connected. Sync runs while this browser is open.'
  } catch (error) { status.textContent = error.message }
})

document.querySelector('#disconnect').addEventListener('click', async () => {
  await chrome.storage.local.remove(['facebookBridgeToken'])
  tokenInput.value = ''
  status.textContent = 'Disconnected from Archie Radar.'
})

load()
