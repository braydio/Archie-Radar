const ARCHIE_DEFAULTS = {
  sex: 'male', color: 'orange', pattern: 'striped', coat: 'short', altered: 'neutered',
  collar: 'none', microchip: 'none', whiteChest: 'yes', whiteBelly: 'any', whitePaws: 'any', whiteFace: 'any',
  ageCompatible: false, archieCompatible: false
}

function traitBoost(post, filters) {
  const traits = post.parsed_traits || {}
  let boost = 0
  if (filters.sex && post.sex === filters.sex) boost += 4
  if (filters.color && (traits.colors || []).includes(filters.color)) boost += 7
  if (filters.pattern && (traits.patterns || []).includes(filters.pattern)) boost += 5
  if (filters.coat && traits.coat === filters.coat) boost += 3
  if (filters.altered && traits.altered_status === filters.altered) boost += 4
  if (filters.whiteChest === 'yes' && traits.white_chest === true) boost += 4
  if (filters.whiteChest === 'no' && traits.white_chest === false) boost += 2
  if (filters.whiteBelly === 'yes' && traits.white_belly === true) boost += 1
  if (filters.whiteBelly === 'no' && traits.white_belly === false) boost += 1
  if (filters.whitePaws === 'yes' && traits.white_paws === true) boost += 2
  if (filters.whitePaws === 'no' && traits.white_paws === false) boost += 1
  if (filters.whiteFace === 'yes' && traits.white_face === true) boost += 2
  if (filters.whiteFace === 'no' && traits.white_face === false) boost += 1
  if (filters.collar && traits.collar === filters.collar) boost += 3
  if (filters.microchip && traits.microchip === filters.microchip) boost += 3
  if (filters.ageCompatible && traits.age_years != null && Math.abs(Number(traits.age_years) - 8) <= 2.5) boost += 2
  if (filters.archieCompatible && (post.archie_trait_conflicts || []).length === 0) boost += 5
  return boost
}

function eventTime(post) {
  const value = post.reported_at || post.posted_at || post.first_seen_at
  const parsed = value ? new Date(value).getTime() : 0
  return Number.isFinite(parsed) ? parsed : 0
}

export function clientPrioritize(list, filters, sort) {
  if (sort !== 'smart' || filters.traitMode !== 'prioritize') return list
  const isDefaults = Object.keys(ARCHIE_DEFAULTS).every(key => filters[key] === ARCHIE_DEFAULTS[key])
  if (isDefaults) return list
  return list.map((post, index) => ({ post, index, boost: traitBoost(post, filters) })).sort((a, b) => {
    const scoreA = Number(a.post.match_score || 0), scoreB = Number(b.post.match_score || 0)
    const band = Math.floor(scoreB / 10) - Math.floor(scoreA / 10)
    if (band) return band
    const photo = Number(Boolean(b.post.primary_image?.url || b.post.image_url)) - Number(Boolean(a.post.primary_image?.url || a.post.image_url))
    if (photo) return photo
    if (a.boost !== b.boost) return b.boost - a.boost
    if (scoreA !== scoreB) return scoreB - scoreA
    const freshness = eventTime(b.post) - eventTime(a.post)
    return freshness || a.index - b.index
  }).map(row => row.post)
}
