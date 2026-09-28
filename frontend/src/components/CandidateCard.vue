<script>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { dateOnly, exactDate, relativeTime, sourceLabel, statusLabel } from '../lib/format.js'
import CandidateMedia from './candidates/CandidateMedia.vue'

const SOURCE_ACCENTS = {
  pawboost: '#cc8a3d',
  regional_24petconnect: '#557a78',
  aps_durham_found: '#5c6f9b',
  wake_county_lostfound: '#6d7a54',
  orange_county_found: '#b06d4f',
  pet911: '#7b5a92',
  petkey: '#6f6f8e',
  facebook_bridge: '#526aa5',
  facebook_group: '#526aa5'
}

export default {
  name: 'CandidateCard',
  components: { CandidateMedia, RouterLink },
  props: {
    post: { type: Object, required: true },
    rank: { type: Number, default: 1 },
    config: { type: Object, default: null }
  },
  emits: ['review', 'locate', 'map'],
  setup(props, { emit }) {
    const imageUnavailable = ref(false)
    const selectedImage = ref(null)
    const candidateImage = computed(() => props.post.primary_image || props.post.case_images?.[0] || (props.post.image_url ? {
      url: props.post.image_url, width: props.post.image_width, height: props.post.image_height,
      aspect_ratio: props.post.image_aspect_ratio, photo_similarity: props.post.photo_similarity,
      source_post_id: props.post.primary_post_id, source_platform: props.post.source_platform,
      holding_entity: props.post.holding_entity
    } : null))
    const caseImages = computed(() => props.post.case_images?.length
      ? props.post.case_images.filter(image => image.url !== candidateImage.value?.url)
      : [])
    watch(() => [props.post.case_id, candidateImage.value?.url], () => { imageUnavailable.value = false; selectedImage.value = null })
    const displayedImage = computed(() => selectedImage.value || candidateImage.value)

    const priorityClass = computed(() => {
      const score = Number(props.post.match_score || 0)
      if (score >= 70) return 'high'
      if (score >= 48) return 'medium'
      return 'low'
    })
    const photoPct = computed(() => props.post.photo_similarity == null ? null : Math.round(props.post.photo_similarity * 100))
    const hasPhoto = computed(() => Boolean(candidateImage.value?.url) && !imageUnavailable.value)
    const sourceAccent = computed(() => SOURCE_ACCENTS[props.post.source] || '#7b897f')

    const sourcePostedAt = computed(() => props.post.posted_at || null)
    const eventAt = computed(() => props.post.reported_at || null)
    const addedAt = computed(() => props.post.first_seen_at || null)
    const title = computed(() => props.post.name || `${statusLabel(props.post.status) || 'Found'} cat`)
    const usefulTitle = computed(() => !/^(found\s+cat|shelter\s+intake\s+cat|cat|unknown)$/i.test(String(title.value || '').trim()))
    const detailsAvailable = computed(() => Boolean(props.post.nearest_landmark || props.post.finder_message || props.post.contact_info || props.post.contact_url))
    const candidateHeading = computed(() => props.post.current_custody?.holding_entity || props.post.holding_entity || props.post.current_custody?.custody_label || props.post.custody_label || statusLabel(props.post.status) || 'Found report')
    const candidateSubheading = computed(() => [props.post.current_custody?.custody_label || props.post.custody_label,
      (props.post.current_custody || props.post.source_platform) ? `via ${props.post.source_platform || sourceLabel(props.post.source)}` : sourceLabel(props.post.source)].filter(Boolean).join(' · '))
    const currentLocation = computed(() => props.post.current_location || null)
    const locationText = computed(() => (currentLocation.value?.location_text || '').replace(/\s+And\s+/gi, ' & '))
    const locationDistance = computed(() => currentLocation.value?.distance_from_home_miles)
    const identityIds = computed(() => props.post.external_ids || [])
    const facebookAppearances = computed(() => {
      const byGroup = new Map()
      for (const record of props.post.source_records || []) {
        for (const appearance of record.facebook_group_appearances || []) {
          if (appearance.group_subscription_id != null) byGroup.set(appearance.group_subscription_id, appearance)
        }
      }
      return [...byGroup.values()].sort((a, b) => String(a.group_name).localeCompare(String(b.group_name)))
    })
    const mapHref = computed(() => {
      const lat = currentLocation.value?.map_latitude
      const lon = currentLocation.value?.map_longitude
      return lat == null || lon == null ? null : `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=14/${lat}/${lon}`
    })
    const bearing = computed(() => {
      const { map_latitude: rawLat, map_longitude: rawLon } = currentLocation.value || {}
      const { home_latitude: rawHomeLat, home_longitude: rawHomeLon } = props.config || {}
      if (rawLat == null || rawLon == null || rawHomeLat == null || rawHomeLon == null) return null
      const lat = Number(rawLat), lon = Number(rawLon)
      const homeLat = Number(rawHomeLat), homeLon = Number(rawHomeLon)
      if (![lat, lon, homeLat, homeLon].every(Number.isFinite)) return null
      const rad = value => value * Math.PI / 180
      const y = Math.sin(rad(lon - homeLon)) * Math.cos(rad(lat))
      const x = Math.cos(rad(homeLat)) * Math.sin(rad(lat)) - Math.sin(rad(homeLat)) * Math.cos(rad(lat)) * Math.cos(rad(lon - homeLon))
      const degrees = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360
      return ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(degrees / 22.5) % 16]
    })
    const distanceText = computed(() => {
      if (locationDistance.value == null) return ''
      const approximate = Boolean(currentLocation.value?.distance_is_approximate)
      const prefix = approximate ? '~' : ''
      const direction = bearing.value ? ` ${bearing.value}` : ''
      const suffix = approximate ? ' · Approximate' : ''
      return `${prefix}${Number(locationDistance.value).toFixed(1)} mi${direction} of home${suffix}`
    })
    const sourceIs24Pet = computed(() => String(props.post.source || '').includes('24petconnect'))
    const sourceLink = computed(() => sourceIs24Pet.value
      ? (props.post.source_link_kind === 'exact_detail' ? (props.post.detail_url || props.post.source_url) : (props.post.listing_url || props.post.source_url))
      : props.post.source_url)
    const sourceLinkLabel = computed(() => sourceIs24Pet.value
      ? (props.post.source_link_kind === 'exact_detail' ? 'View on 24PetConnect ↗' : 'Open 24PetConnect ↗')
      : 'Open source ↗')

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
      if (traits.white_belly === true) add('white belly', 'neutral')
      if (traits.white_belly === false) add('no white belly', 'neutral')
      if (traits.white_paws === true) add('white paws', 'neutral')
      if (traits.white_face === true) add('white face', 'neutral')
      if (traits.collar === 'none') add('no collar', 'match')
      if (traits.collar === 'wearing') add('collar', 'conflict')
      if (traits.microchip === 'none') add('not microchipped', 'match')
      if (traits.microchip === 'yes') add('microchipped', 'conflict')
      if (traits.age_years != null) add(`~${traits.age_years} yr`, Math.abs(Number(traits.age_years) - 8) <= 2.5 ? 'match' : 'neutral')
      return tokens
    })

    const primaryTraitTokens = computed(() => {
      const priority = [/orange/i, /striped|tabby/i, /male|female/i, /white chest/i, /short hair/i, /neutered|spayed|intact/i, /collar/i, /microchip/i, /age|yr/i, /white paws/i, /white face/i]
      return [...traitTokens.value].sort((a, b) => {
        if (a.state === 'conflict' && b.state !== 'conflict') return -1
        if (b.state === 'conflict' && a.state !== 'conflict') return 1
        const ai = priority.findIndex(pattern => pattern.test(a.label))
        const bi = priority.findIndex(pattern => pattern.test(b.label))
        return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi)
      }).slice(0, 5)
    })

    const reasonSummary = computed(() => {
      try {
        const skip = /^(Male|Neutered|Very close|Nearby|Regional|Farther away|Very recent|Recent|Orange coloring|Striped\/tabby|Short hair|White chest|No white belly|No collar|Not microchipped)/i
        return JSON.parse(props.post.match_reasons || '[]').filter(x => x && !skip.test(x)).slice(0, 4)
      } catch { return [] }
    })

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
    function locate() { emit('locate', props.post) }
    function focusMap() { emit('map', props.post) }
    async function copyAnimalId() {
      const identifier = identityIds.value.find(item => item.kind === 'animal_id') || identityIds.value[0]
      if (!identifier) return
      try { await navigator.clipboard.writeText(identifier.value) } catch { /* Clipboard may be unavailable in insecure contexts. */ }
    }

    return {
      imageUnavailable, candidateImage, displayedImage, selectedImage, caseImages, priorityClass, photoPct, hasPhoto, sourceAccent, candidateHeading, candidateSubheading, identityIds,
      sourcePostedAt, eventAt, addedAt, title, usefulTitle, detailsAvailable, mapHref, distanceText, sourceLink, sourceLinkLabel, sourceIs24Pet,
      traitTokens, primaryTraitTokens, reasonSummary, colorClass, facebookAppearances,
      sourceLabel, statusLabel, dateOnly, exactDate, relativeTime, review, locate, focusMap, locationText, currentLocation, copyAnimalId
    }
  }
}
</script>

<template>
  <article :id="`post-${post.id}`" :class="['candidate-card', `priority-${priorityClass}`, colorClass, { 'has-photo': hasPhoto }]" :style="{ '--source-accent': sourceAccent }">
    <CandidateMedia v-if="hasPhoto" :image="candidateImage" :other-images="caseImages" :image-width="post.image_width" :image-height="post.image_height" :photo-similarity="photoPct == null ? null : photoPct / 100" :alt="`Candidate cat photo${identityIds[0] ? ` for ${identityIds[0].label} ${identityIds[0].value}` : ''}`" :case-id="post.case_id || post.id" @select-image="selectedImage=$event" @unavailable="imageUnavailable = true" />

    <div class="candidate-body">
      <div class="candidate-topline">
        <div class="source-line candidate-case-heading">
          <span class="source-name candidate-holder">{{ candidateHeading }}</span>
          <span class="status-tag candidate-subheading">{{ candidateSubheading }}</span>
          <span v-if="!hasPhoto" class="no-photo-tag">No photo</span>
        </div>
        <div class="rank-badge" :title="'Top of the queue is #1. Score is shown separately.'">
          <strong>#{{ rank }}</strong><span>rank</span>
        </div>
      </div>

      <div class="title-row">
        <h2 v-if="usefulTitle">{{ title }}</h2>
        <a v-if="sourceLink" class="original-link prominent" :href="sourceLink" target="_blank" rel="noopener">{{ sourceLinkLabel }}</a>
        <button v-if="sourceIs24Pet && post.source_link_kind !== 'exact_detail'" type="button" class="copy-id-button" @click="copyAnimalId">Copy Animal ID</button>
      </div>

      <div v-if="identityIds.length || post.record_count > 1" class="case-identity-row">
        <strong v-for="identifier in identityIds" :key="identifier.namespace + identifier.value">{{ identifier.label }} {{ identifier.value }}</strong>
        <span>Radar case #{{ post.case_id || post.id }}<template v-if="post.record_count > 1"> · {{ post.record_count }} source records</template></span>
      </div>
      <p v-if="facebookAppearances.length" class="facebook-appearance-summary">Seen in {{ facebookAppearances.length }} Facebook {{ facebookAppearances.length === 1 ? 'group' : 'groups' }}</p>
      <RouterLink class="candidate-case-open" :to="`/candidates/${post.case_id || post.id}`">Open case workspace →</RouterLink>

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
      <div v-if="locationText || distanceText" class="address-row">
        <div>
          <strong v-if="locationText">{{ locationText }}</strong>
          <span v-if="distanceText" :class="{ approximate: currentLocation?.distance_is_approximate }">{{ distanceText }}</span>
        </div>
        <button v-if="currentLocation?.map_latitude != null && currentLocation?.map_longitude != null" type="button" @click="focusMap">Map</button>
      </div>
      <button v-if="locationText && !currentLocation?.map_latitude" type="button" class="candidate-locate-link" @click="locate">Locate relative to home</button>

      <div v-if="primaryTraitTokens.length" class="trait-row" aria-label="Most relevant traits parsed from listing text">
        <span v-for="token in primaryTraitTokens" :key="`${token.label}-${token.state}`" :class="['trait-chip', token.state]">{{ token.label }}</span>
        <span v-if="traitTokens.length > primaryTraitTokens.length" class="trait-overflow">+{{ traitTokens.length - primaryTraitTokens.length }} more</span>
      </div>

      <div class="meta-bar mobile-detail-summary">
        <span v-if="Number(post.match_score || 0) > 0" class="score-pill">match signals {{ Math.round(post.match_score || 0) }}/100</span>
        <span v-else class="score-pill weak">limited match signals</span>
        <span v-if="sourcePostedAt && (!eventAt || dateOnly(sourcePostedAt) !== dateOnly(eventAt))" class="date-primary">Posted {{ dateOnly(sourcePostedAt) }}</span>
      </div>

      <div class="review-actions">
        <button class="possible" @click="review('possible')">Possible Archie</button>
        <button class="hold" @click="review('needs_review')">Hold</button>
        <button class="dismiss" @click="review('dismissed')">Not Archie</button>
      </div>

      <details class="candidate-more-details">
        <summary>More details</summary>
        <section v-if="post.description" class="more-detail-section">
          <h3>Description</h3><p class="description">{{ post.description }}</p>
        </section>
        <section v-if="reasonSummary.length || post.duplicate_of_post_id || post.match_score" class="more-detail-section">
          <h3>Match information</h3>
          <p v-if="post.match_score" class="score-pill">Match signals {{ Math.round(post.match_score) }}/100</p>
          <p v-if="post.duplicate_of_post_id" class="duplicate-note">Image matches candidate #{{ post.duplicate_of_post_id }}</p>
          <ul v-if="reasonSummary.length"><li v-for="reason in reasonSummary" :key="reason">{{ reason }}</li></ul>
        </section>
        <section class="more-detail-section">
          <h3>Listing</h3>
          <dl>
            <template v-if="post.source_id"><dt>Source ID</dt><dd>{{ post.source_id }}</dd></template>
            <template v-if="sourcePostedAt"><dt>Posted</dt><dd>{{ exactDate(sourcePostedAt) }}</dd></template>
            <template v-if="eventAt"><dt>Found / sighted</dt><dd>{{ exactDate(eventAt) }}</dd></template>
            <template v-if="addedAt"><dt>Added to Radar</dt><dd>{{ exactDate(addedAt) }}</dd></template>
          </dl>
          <div v-if="currentLocation" class="location-provenance"><h3>Location provenance</h3><p>Current location from source record #{{ currentLocation.record_id }}</p><p>Precision: {{ currentLocation.precision || 'unknown' }}</p><p>{{ currentLocation.location_text }}</p></div>
          <a v-if="mapHref" class="detail-link" :href="mapHref" target="_blank" rel="noopener">Open external map ↗</a>
          <p v-if="sourceIs24Pet" class="inspector-meta">Source link: {{ post.source_link_kind === 'exact_detail' ? 'exact animal detail' : post.source_link_kind === 'search_results' ? 'saved search results' : post.source_link_kind || 'unavailable' }}</p>
        </section>
        <section v-if="post.source_records?.length > 1" class="more-detail-section source-history">
          <h3>Source history</h3>
          <article v-for="record in post.source_records" :key="record.post_id" class="source-history-row">
            <time>{{ exactDate(record.last_seen_at || record.first_seen_at) }}</time>
            <strong>{{ record.holding_entity || record.custody_label || record.source_label }}</strong>
            <span v-if="record.source_id">{{ record.identifier_label }} {{ record.source_id }}</span>
            <small>{{ record.custody_label || statusLabel(record.status) }}<template v-if="record.source_platform"> · via {{ record.source_platform }}</template></small>
            <em v-if="displayedImage?.source_post_id === record.post_id">Current photo</em>
            <a v-if="record.source_url" :href="record.source_link_kind === 'exact_detail' ? (record.detail_url || record.source_url) : (record.listing_url || record.source_url)" target="_blank" rel="noopener">{{ record.source_link_kind === 'exact_detail' ? 'View animal ↗' : record.source_platform === '24PetConnect' ? 'Open 24PetConnect ↗' : 'Open record ↗' }}</a>
          </article>
        </section>
        <section v-if="facebookAppearances.length" class="more-detail-section source-history">
          <h3>Facebook reports · {{ facebookAppearances.length }} {{ facebookAppearances.length === 1 ? 'group' : 'groups' }}</h3>
          <article v-for="appearance in facebookAppearances" :key="appearance.group_subscription_id" class="source-history-row">
            <time>{{ exactDate(appearance.posted_at || appearance.seen_at) }}</time>
            <strong>{{ appearance.group_name }}</strong>
            <a v-if="appearance.group_url" :href="appearance.group_url" target="_blank" rel="noopener">Open group ↗</a>
          </article>
        </section>
        <section v-if="Object.keys(post.parsed_traits || {}).length" class="more-detail-section">
          <h3>Parsed traits</h3>
        <dl>
          <template v-if="post.parsed_traits?.colors?.length"><dt>Colors</dt><dd>{{ post.parsed_traits.colors.join(', ') }}</dd></template>
          <template v-if="post.parsed_traits?.patterns?.length"><dt>Patterns</dt><dd>{{ post.parsed_traits.patterns.join(', ') }}</dd></template>
          <template v-if="post.parsed_traits?.coat"><dt>Coat</dt><dd>{{ post.parsed_traits.coat }}</dd></template>
          <template v-if="post.sex"><dt>Sex</dt><dd>{{ post.sex }}</dd></template>
          <template v-if="post.parsed_traits?.altered_status"><dt>Altered</dt><dd>{{ post.parsed_traits.altered_status }}</dd></template>
          <template v-if="post.parsed_traits?.white_chest != null"><dt>White chest</dt><dd>{{ post.parsed_traits.white_chest ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.white_belly != null"><dt>White belly</dt><dd>{{ post.parsed_traits.white_belly ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.white_paws != null"><dt>White paws</dt><dd>{{ post.parsed_traits.white_paws ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.white_face != null"><dt>White face / muzzle</dt><dd>{{ post.parsed_traits.white_face ? 'yes' : 'no' }}</dd></template>
          <template v-if="post.parsed_traits?.collar && post.parsed_traits.collar !== 'unknown'"><dt>Collar</dt><dd>{{ post.parsed_traits.collar }}</dd></template>
          <template v-if="post.parsed_traits?.microchip && post.parsed_traits.microchip !== 'unknown'"><dt>Microchip</dt><dd>{{ post.parsed_traits.microchip }}</dd></template>
          <template v-if="post.parsed_traits?.age_years != null"><dt>Age</dt><dd>~{{ post.parsed_traits.age_years }} years</dd></template>
        </dl>
        </section>
        <section v-if="detailsAvailable" class="more-detail-section">
          <h3>Contact & listing details</h3>
          <dl>
            <template v-if="post.nearest_landmark"><dt>Nearest landmark</dt><dd>{{ post.nearest_landmark }}</dd></template>
            <template v-if="post.finder_message"><dt>Finder message</dt><dd>{{ post.finder_message }}</dd></template>
            <template v-if="post.contact_info"><dt>Contact</dt><dd>{{ post.contact_info }}</dd></template>
            <template v-if="post.contact_url"><dt>Contact link</dt><dd><a class="detail-link" :href="post.contact_url" target="_blank" rel="noopener">Open contact ↗</a></dd></template>
          </dl>
        </section>
        <section v-if="displayedImage" class="more-detail-section image-details">
          <h3>Selected source image</h3>
          <p v-if="displayedImage.width && displayedImage.height">{{ displayedImage.width }} × {{ displayedImage.height }}<span v-if="Math.min(displayedImage.width, displayedImage.height) < 320"> · Low-resolution source</span></p>
          <p v-if="displayedImage.source_platform || displayedImage.holding_entity">{{ displayedImage.holding_entity || displayedImage.source_platform }}<template v-if="displayedImage.holding_entity && displayedImage.source_platform"> · via {{ displayedImage.source_platform }}</template></p>
        </section>
      </details>

    </div>
  </article>
</template>
