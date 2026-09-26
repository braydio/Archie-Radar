const define = (label, group, icon, color = '#bf704d', defaultConfidence = 'possible', defaultEpistemicState = 'observed') => ({ label, group, icon, color, defaultConfidence, defaultEpistemicState })

export const OBJECT_TYPES = {
  sighting: define('Sighting', 'search', 'sighting'), possible_sighting: define('Possible sighting', 'search', 'possible-sighting'),
  checked_location: define('Checked location', 'search', 'checked-location', '#657c69', 'confirmed'),
  food_station: define('Food station', 'search', 'food-water-station', '#b28a43'), water_station: define('Water station', 'search', 'food-water-station', '#538b9a'),
  trap: define('Trap', 'search', 'trap', '#927149'), scent_item: define('Scent item', 'search', 'scent-item', '#9c7b52'),
  flyer: define('Flyer', 'search', 'flyer', '#778195'), search_start: define('Search starting point', 'search', 'search-start', '#477b7a', 'confirmed'),
  dog_lives_here: define('Dog lives here', 'environment', 'dog', '#b85d45'), outdoor_cat: define('Outdoor cat', 'environment', 'outdoor-cat', '#8372a1'),
  cat_feeding_station: define('Cat feeding station', 'environment', 'food-water-station', '#b28a43'), porch: define('Porch', 'environment', 'shelter-porch', '#8d8069'),
  crawlspace: define('Crawlspace', 'environment', 'shelter-porch', '#756b59'), shed: define('Shed', 'environment', 'shelter-porch', '#827866'),
  culvert: define('Culvert', 'environment', 'culvert', '#587e84'), fence_opening: define('Fence opening', 'environment', 'fence-gap', '#67825c'),
  road_crossing: define('Road crossing', 'environment', 'road-crossing', '#b15e49'), creek_crossing: define('Creek crossing', 'environment', 'creek-crossing', '#528797'),
  dense_cover: define('Dense cover', 'environment', 'shelter-porch', '#52745a'), construction: define('Construction', 'environment', 'human-activity', '#b07b41'),
  human_activity: define('Human activity', 'environment', 'human-activity', '#857760'), coyote: define('Coyote', 'wildlife', 'coyote', '#906c4f'),
  fox: define('Fox', 'wildlife', 'fox', '#c17847'), raccoon: define('Raccoon', 'wildlife', 'raccoon', '#706d66'), bobcat: define('Bobcat', 'wildlife', 'bobcat', '#a47850'),
  deer: define('Deer', 'wildlife', 'deer', '#8e8053'), tracks: define('Tracks', 'wildlife', 'wildlife-tracks', '#806f5a'), scat: define('Scat', 'wildlife', 'wildlife-tracks', '#78654f'),
  vocalization: define('Vocalization', 'wildlife', 'wildlife-vocalization', '#7881a3'), other_wildlife: define('Other wildlife', 'wildlife', 'coyote', '#7c766c'),
  camera_hit: define('Camera hit', 'evidence', 'camera-hit', '#527b7a'), photo: define('Photo', 'evidence', 'evidence-photo', '#b17851'),
  audio: define('Audio', 'evidence', 'evidence-audio', '#777fa2'), footprint: define('Footprint', 'evidence', 'wildlife-tracks', '#806f5a'),
  fur: define('Fur', 'evidence', 'evidence-photo', '#9c835e'), reported_observation: define('Reported observation', 'evidence', 'sighting')
}

export const PIN_GROUPS = ['search', 'environment', 'wildlife', 'evidence'].map(key => ({
  key, label: ({ search: 'Search', environment: 'Environment', wildlife: 'Wildlife', evidence: 'Evidence' })[key],
  types: Object.keys(OBJECT_TYPES).filter(type => OBJECT_TYPES[type].group === key)
}))
export const PIN_TYPES = Object.entries(OBJECT_TYPES).map(([value, definition]) => ({ value, label: definition.label, ...definition }))
