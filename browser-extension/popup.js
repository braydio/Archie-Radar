const apiInput = document.querySelector('#api')
const tokenInput = document.querySelector('#token')
const status = document.querySelector('#status')

async function load() {
  const config = await chrome.storage.local.get(['archieRadarApi', 'facebookBridgeToken'])
  apiInput.value = config.archieRadarApi || 'http://127.0.0.1:8000'
  tokenInput.value = config.facebookBridgeToken || ''
  if (tokenInput.value) status.textContent = 'Helper pairing saved. You can refresh the server Facebook session at any time.'
}

document.querySelector('#save').addEventListener('click', async () => {
  status.textContent = 'Connecting…'
  try {
    const api = apiInput.value.trim().replace(/\/$/, '')
    const origin = new URL(api).origin
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] })
    if (!granted) throw new Error('Allow the helper to connect to this Archie Radar server.')
    await chrome.storage.local.set({ archieRadarApi: api, facebookBridgeToken: tokenInput.value.trim() })

    const paired = await chrome.runtime.sendMessage({ type: 'ARCHIE_TEST_PAIR' })
    if (!paired?.ok) throw new Error(paired?.error || 'Pairing failed')

    status.textContent = 'Handing off logged-in Facebook session…'
    const handedOff = await chrome.runtime.sendMessage({ type: 'ARCHIE_HANDOFF_SESSION' })
    if (!handedOff?.ok) throw new Error(handedOff?.error || 'Session handoff failed')

    status.textContent = 'Server session ready ✓ You can close this browser. Archie Radar will scan selected groups on its own.'
  } catch (error) {
    status.textContent = error.message
  }
})

document.querySelector('#disconnect').addEventListener('click', async () => {
  await chrome.storage.local.remove(['facebookBridgeToken'])
  tokenInput.value = ''
  status.textContent = 'Helper pairing forgotten. The server session remains active until cleared in Archie Radar.'
})

load()
