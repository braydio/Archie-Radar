(() => {
  const canonicalUrl = href => {
    try {
      const url = new URL(href, location.href)
      url.search = ''
      url.hash = ''
      return url.href.replace(/\/$/, '')
    } catch { return '' }
  }

  function extractPost(article) {
    const text = (article.innerText || '').trim().slice(0, 30000)
    if (!text) return null
    const permalink = article.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid="]')
    const postUrl = canonicalUrl(permalink?.href || '')
    const idMatch = postUrl.match(/\/posts\/(\d+)|\/permalink\/(\d+)|story_fbid=(\d+)/)
    const times = [...article.querySelectorAll('time[datetime]')]
    const postedAt = times.map(time => time.getAttribute('datetime')).find(Boolean) || null
    const images = [...article.querySelectorAll('img')]
      .filter(image => (image.naturalWidth || Number(image.getAttribute('width')) || 0) >= 120 &&
        (image.naturalHeight || Number(image.getAttribute('height')) || 0) >= 120)
      .filter(image => image.currentSrc || image.src)
      .slice(0, 8)
      .map(image => ({
        url: image.currentSrc || image.src,
        width: image.naturalWidth || Number(image.getAttribute('width')) || null,
        height: image.naturalHeight || Number(image.getAttribute('height')) || null
      }))
    return {
      facebook_post_id: idMatch?.[1] || idMatch?.[2] || idMatch?.[3] || null,
      canonical_url: postUrl || null,
      text,
      posted_at: postedAt,
      images,
      video_present: !!article.querySelector('video, a[href*="/videos/"]'),
      captured_at: new Date().toISOString()
    }
  }

  function extractFeed() {
    const articles = [...document.querySelectorAll('[role="article"], article')]
    const posts = []
    const seen = new Set()
    for (const article of articles) {
      const post = extractPost(article)
      if (!post) continue
      const key = post.facebook_post_id || post.canonical_url || post.text.slice(0, 160)
      if (seen.has(key)) continue
      seen.add(key)
      posts.push(post)
    }
    const heading = document.querySelector('h1')?.innerText?.trim()
    return { posts, article_count: articles.length, group_name: heading || document.title || 'Facebook group' }
  }

  window.ArchieFacebookPostExtractor = { extractFeed }
})()
