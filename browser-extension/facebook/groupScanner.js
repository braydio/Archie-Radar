(() => {
  function groupDetails() {
    const match = location.pathname.match(/^\/groups\/([^/?]+)/)
    if (!match) return null
    const groupId = /^\d+$/.test(match[1]) ? match[1] : null
    const name = document.querySelector('h1')?.innerText?.trim() || document.title || 'Facebook group'
    return { group_url: `https://www.facebook.com/groups/${match[1]}`, facebook_group_id: groupId, group_name: name }
  }

  function addGroupButton() {
    const group = groupDetails()
    if (!group || document.getElementById('archie-radar-add-group')) return
    const button = document.createElement('button')
    button.id = 'archie-radar-add-group'
    button.type = 'button'
    button.textContent = 'Add this group to Archie Radar'
    Object.assign(button.style, {
      position: 'fixed', right: '18px', bottom: '18px', zIndex: '2147483647',
      padding: '12px 16px', border: '0', borderRadius: '10px',
      background: '#294f40', color: 'white', font: '600 14px system-ui',
      boxShadow: '0 4px 18px #0005', cursor: 'pointer'
    })
    button.addEventListener('click', async () => {
      button.disabled = true
      button.textContent = 'Adding…'
      try {
        const result = await chrome.runtime.sendMessage({ type: 'ARCHIE_ADD_GROUP', group })
        if (!result?.ok) throw new Error(result?.error || 'Could not add group')
        button.textContent = 'Added to Archie Radar ✓'
      } catch (error) {
        button.disabled = false
        button.textContent = error.message || 'Connect helper first'
      }
    })
    document.body.append(button)
  }

  addGroupButton()
  new MutationObserver(addGroupButton).observe(document.documentElement, { childList: true, subtree: true })
})()
