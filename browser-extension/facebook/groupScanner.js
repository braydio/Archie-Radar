(() => {
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms))

  async function scanGroup(group) {
    const seenIds = new Set(group.watermark_post_ids || [])
    const byKey = new Map()
    const seenWatermarks = new Set()
    const seenOldPosts = new Set()
    let repeatedWatermark = 0
    let olderThanCutoff = 0
    let scannedArticles = 0
    const cutoff = group.first_sync_cutoff ? new Date(group.first_sync_cutoff).getTime() : 0
    const scrollRoot = document.scrollingElement || document.documentElement

    for (let pass = 0; pass < 12; pass += 1) {
      const snapshot = window.ArchieFacebookPostExtractor.extractFeed()
      scannedArticles = Math.max(scannedArticles, snapshot.article_count)
      for (const post of snapshot.posts) {
        const key = post.facebook_post_id || post.canonical_url
        if (key) byKey.set(key, post)
        if (post.facebook_post_id && seenIds.has(post.facebook_post_id) && !seenWatermarks.has(post.facebook_post_id)) {
          seenWatermarks.add(post.facebook_post_id)
          repeatedWatermark += 1
        }
        if (key && cutoff && post.posted_at && new Date(post.posted_at).getTime() < cutoff && !seenOldPosts.has(key)) {
          seenOldPosts.add(key)
          olderThanCutoff += 1
        }
      }
      if (repeatedWatermark >= 20 || olderThanCutoff >= 10) break
      const before = scrollRoot.scrollHeight
      scrollRoot.scrollTo({ top: scrollRoot.scrollHeight, behavior: 'instant' })
      await pause(950 + Math.round(Math.random() * 350))
      if (scrollRoot.scrollHeight === before && pass >= 2) break
    }

    const posts = [...byKey.values()]
    return {
      group_name: window.ArchieFacebookPostExtractor.extractFeed().group_name,
      scanned: scannedArticles,
      posts,
      parser_warning: scannedArticles === 0 ? 'No rendered feed articles detected; Facebook layout or permissions may have changed.' : ''
    }
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'ARCHIE_SCAN_GROUP') {
      scanGroup(message.group).then(sendResponse).catch(error => sendResponse({ error: error.message, posts: [], scanned: 0 }))
      return true
    }
  })

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
        button.textContent = error.message || 'Pair extension first'
      }
    })
    document.body.append(button)
  }

  addGroupButton()
  new MutationObserver(addGroupButton).observe(document.documentElement, { childList: true, subtree: true })
})()
