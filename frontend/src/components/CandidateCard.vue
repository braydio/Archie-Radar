<script>
import { computed, ref, watch } from 'vue'
import { dateOnly, exactDate, relativeTime, sourceLabel, statusLabel } from '../lib/format.js'

const SOURCE_ACCENTS = {
  pawboost: '#cc8a3d',
  regional_24petconnect: '#557a78',
  aps_durham_found: '#5c6f9b',
  wake_county_lostfound: '#6d7a54',
  orange_county_found: '#b06d4f',
  pet911: '#7b5a92',
  petkey: '#6f6f8e',
  facebook_bridge: '#526aa5'
}

export default {
  name: 'CandidateCard',
  props: {
    post: { type: Object, required: true },
    rank: { type: Number, default: 1 }
  },
  emits: ['review'],
  setup(props, { emit }) {
    const imageFailed = ref(false)
    const descriptionOpen = ref(false)
    watch(() => props.post.image_url, () => { imageFailed.value = false })

    const priorityClass = computed(() => {
      const score = Number(props.post.match_score || 0)
      if (score >= 70) return 'high'
      if (score >= 48) return 'medium'
      return 'low'
    })
    const photoPct = computed(() => props.post.photo_similarity == null ? null : Math.round(props.post.photo_similarity * 100))
    const hasPhoto = computed(() => Boolean(props.post.image_url) && !imageFailed.value)
    const sourceAccent = computed(() => SOURCE_ACCENTS[props.post.source] || '#7b897f')

    const sourcePostedAt = computed(() => props.post.posted_at || null)
    const eventAt = computed(() => props.post.reported_at || null)
    const addedAt = computed(() => props.post.first_seen_at || null)
    const title = computed(() => props.post.name || `${statusLabel(props.post.status) || 'Found'} cat`)
    const detailsAvailable = computed(() => Boolean(props.post.nearest_landmark || props.post.finder_message || props.post.contact_info || props.post.contact_url))
    const mapHref = computed(() => {
      const lat = props.post.map_latitude
      const lon = props.post.map_longitude
      return lat == null || lon == null ? null : `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=14/${lat}/${lon}`
    })
    const distanceText = computed(() => {
      if (props.post.distance_from_home_miles == null) return ''
      const prefix = props.post.distance_is_approximate ? '~' : ''
      return `${prefix}${Number(props.post.distance_from_home_miles).toFixed(1)} mi from home`
    })

    const traitTokens = computed(() => {
      const traits = props.post.parsed_traits || {}
      const tokens = []
      const add = (label, state = 'neutral') => tokens.push({ label, state })
      const sex = String(props.post.sex || '').toLowerCase()
      if (sex && !['unknown', 'unsure'].includes(sex)) add(sex, sex === 'male' ? 'match' : 'conflict')
      const altered = String(traits.altered_status || props.post.altered_status || '').toLowerCase()
      if (altered && !['unknown', 'unsure'].includes(altered)) add(altered, altered === 'neutered' ? 'match' : 'conflict')
      for (const value of traits.colors || []) add(value === 'orange' ? 'orange' : value, value === 'orange' ? 'match' : 'conflict')
      for (const value of traits.patterns || []) add(value === 'striped' ? 'striped / tabby' : value, value === 'striped' ? 'match' : 'conflict')
      if (traits.coat) add(`${traits.coat} hair`, traits.coat === 'short' ? 'match' : 'conflict')
      if (traits.white_chest === true) add('white chest', 'match')
      if (traits.white_belly === true) add('white belly', 'conflict')
      if (traits.white_belly === false) add('no white belly', 'neutral')
      if (traits.white_paws === true) add('white paws', 'neutral')
      if (traits.white_face === true) add('white face', 'neutral')
      if (traits.collar === 'none') add('no collar', 'match')
      if (traits.collar === 'wearing') add('collar', 'conflict')
      if (traits.microchip === 'none') add('not microchipped', 'match')
      if (traits.microchip === 'yes') add('microchipped', 'conflict')
      if (traits.age_years != null) add(`~${traits.age_years} yr`, Math.abs(Number(traits.age_years) - 8) <= 2.5 ? 'match' : 'neutral')
      return tokens.slice(0, 10)
    })

    const reasonSummary = computed(() => {
      try {
        const skip = /^(Male|Neutered|Very close|Nearby|Regional|Farther away|Very recent|Recent|Orange coloring|Striped\/tabby|Short hair|White chest|No white belly|No collar|Not microchipped)/i
        return JSON.parse(props.post.match_reasons || '[]').filter(x => x && !skip.test(x)).slice(0, 4)
      } catch { return [] }
    })

    const descriptionLong = computed(() => String(props.post.description || '').length > 180)
    const colorClass = computed(() => {
      const colors = props.post.parsed_traits?.colors || []
      if (colors.includes('orange')) return 'coat-orange'
      if (colors.includes('gray')) return 'coat-gray'
      if (colors.includes('black')) return 'coat-black'
      if (colors.includes('white')) return 'coat-white'
      if (colors.includes('brown')) return 'coat-brown'
      return 'coat-unknown'
    })

    function review(reviewState) { emit('review', props.post, reviewState) }

    return {
      imageFailed, descriptionOpen, priorityClass, photoPct, hasPhoto, sourceAccent,
      sourcePostedAt, eventAt, addedAt, title, detailsAvailable, mapHref, distanceText,
      traitTokens, reasonSummary, descriptionLong, colorClass,
      sourceLabel, statusLabel, dateOnly, exactDate, relativeTime, review
    }
  }
}
</script>

<template>
  <article :id="`post-${post.id}`" :class="['candidate-card', `priority-${priorityClass}`, colorClass, { 'has-photo': hasPhoto }]" :style="{ '--source-accent': sourceAccent }">
    <div v-if="hasPhoto" class="candidate-photo">
      <img :src="post.image_url" :alt="title" loading="lazy" @error="imageFailed = true" />
      <span v-if="photoPct != null" class="photo-signal">visual {{ photoPct }}%</span>
    </div>

    <div class="candidate-body">
      <div class="candidate-topline">
        <div class="source-line">
          <span class="source-name">{{ sourceLabel(post.source) }}</span>
          <span v-if="statusLabel(post.status)" class="status-tag">{{ statusLabel(post.status) }}</span>
          <span v-if="!hasPhoto" class="no-photo-tag">No photo</span>
        </div>
        <div class="rank-badge" :title="'Top of the queue is #1. Score is shown separately.'">
          <strong>#{{ rank }}</strong><span>rank</span>
        </div>
      </div>

      <div class="title-row">
        <h2>{{ title }}</h2>
        <a v-if="post.source_url" class="original-link prominent" :href="post.source_url" target="_blank" rel="noopener">Original ↗</a>
      </div>

      <div class="date-facts primary-event-date">
        <template v-if="eventAt">
          <strong>{{ statusLabel(post.status) || 'Reported' }} {{ relativeTime(eventAt) }}</strong>
          <span>· {{ dateOnly(eventAt) }}</span>
        </template>
        <template v-else-if="sourcePostedAt">
          <strong>Posted {{ relativeTime(sourcePostedAt) }}</strong>
          <span>· {{ dateOnly(sourcePostedAt) }}</span>
        </template>
      </div>
      <div class="meta-bar">
        <span v-if="Number(post.match_score || 0) > 0" class="score-pill">match signals {{ Math.round(post.match_score || 0) }}/100</span>
        <span v-else class="score-pill weak">limited match signals</span>
        <span v-if="sourcePostedAt && (!eventAt || dateOnly(sourcePostedAt) !== dateOnly(eventAt))" class="date-primary">Posted {{ dateOnly(sourcePostedAt) }}</span>
      </div>

      <div v-if="post.location_text || distanceText" class="address-row">
        <div>
          <strong v-if="post.location_text">{{ post.location_text }}</strong>
          <span v-if="distanceText" :class="{ approximate: post.distance_is_approximate }">{{ distanceText }}</span>
        </div>
        <a v-if="mapHref" :href="mapHref" target="_blank" rel="noopener">Map ↗</a>
      </div>

      <div v-if="traitTokens.length" class="trait-row" aria-label="Traits parsed from listing text">
        <span v-for="token in traitTokens" :key="`${token.label}-${token.state}`" :class="['trait-chip', token.state]">{{ token.label }}</span>
      </div>

      <div v-if="post.description" class="description-wrap">
        <p :class="['description', { clamped: descriptionLong && !descriptionOpen }]">{{ post.description }}</p>
        <button v-if="descriptionLong" class="inline-button" @click="descriptionOpen = !descriptionOpen">{{ descriptionOpen ? 'Show less' : 'More' }}</button>
      </div>

      <details v-if="reasonSummary.length" class="priority-details">
        <summary>Other priority reasons</summary>
        <ul><li v-for="reason in reasonSummary" :key="reason">{{ reason }}</li></ul>
      </details>

      <p v-if="post.duplicate_of_post_id" class="duplicate-note">Image matches candidate #{{ post.duplicate_of_post_id }}</p>

      <details v-if="detailsAvailable" class="finder-details">
        <summary>Contact & listing details</summary>
        <dl>
          <template v-if="post.nearest_landmark"><dt>Nearest landmark</dt><dd>{{ post.nearest_landmark }}</dd></template>
          <template v-if="post.finder_message"><dt>Finder message</dt><dd>{{ post.finder_message }}</dd></template>
          <template v-if="post.contact_info"><dt>Contact</dt><dd>{{ post.contact_info }}</dd></template>
          <template v-if="post.contact_url"><dt>Contact link</dt><dd><a class="detail-link" :href="post.contact_url" target="_blank" rel="noopener">Open contact ↗</a></dd></template>
        </dl>
      </details>

      <details class="full-details">
        <summary>Full parsed details</summary>
        <dl>
          <template v-if="post.source_id"><dt>Source ID</dt><dd>{{ post.source_id }}</dd></template>
          <template v-if="sourcePostedAt"><dt>Posted</dt><dd>{{ exactDate(sourcePostedAt) }}</dd></template>
          <template v-if="eventAt"><dt>Found / sighted</dt><dd>{{ exactDate(eventAt) }}</dd></template>
          <template v-if="addedAt"><dt>Added to Radar</dt><dd>{{ exactDate(addedAt) }}</dd></template>
          <template v-if="post.parsed_traits?.colors?.length"><dt>Colors</dt><dd>{{ post.parsed_traits.colors.join(', ') }}</dd></template>
          <template v-if="post.parsed_traits?.patterns?.length"><dt>Patterns</dt><dd>{{ post.parsed_traits.patterns.join(', ') }}</dd></template>
          <template v-if="post.parsed_traits?.coat"><dt>Coat</dt><dd>{{ post.parsed_traits.coat }}</dd></template>
          <template v-if="post.parsed_traits?.white_chest != null"><dt>White chest</dt><dd>{{ post.parsed_traits.white_chest ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.white_belly != null"><dt>White belly</dt><dd>{{ post.parsed_traits.white_belly ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.white_paws != null"><dt>White paws</dt><dd>{{ post.parsed_traits.white_paws ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.white_face != null"><dt>White face / muzzle</dt><dd>{{ post.parsed_traits.white_face ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.collar && post.parsed_traits.collar !== 'unknown'"><dt>Collar</dt><dd>{{ post.parsed_traits.collar }}</dd></template>
          <template v-if="post.parsed_traits?.microchip && post.parsed_traits.microchip !== 'unknown'"><dt>Microchip</dt><dd>{{ post.parsed_traits.microchip }}</dd></template>
          <template v-if="post.parsed_traits?.age_years != null"><dt>Age</dt><dd>~{{ post.parsed_traits.age_years }} years</dd></template>
        </dl>
      </details>

      <div class="review-actions">
        <button class="possible" @click="review('possible')">Possible Archie</button>
        <button class="hold" @click="review('needs_review')">Hold</button>
        <button class="dismiss" @click="review('dismissed')">Not Archie</button>
      </div>
    </div>
  </article>
</template>
