export const OBJECT_TYPES = {
  search: [
    ['sighting', 'Sighting'], ['possible_sighting', 'Possible sighting'], ['checked_location', 'Checked location'],
    ['food_station', 'Food station'], ['water_station', 'Water station'], ['trap', 'Trap'],
    ['scent_item', 'Scent item'], ['flyer', 'Flyer'], ['search_start', 'Search starting point']
  ],
  environment: [
    ['dog_lives_here', 'Dog lives here'], ['outdoor_cat', 'Outdoor cat'], ['cat_feeding_station', 'Cat feeding station'],
    ['porch', 'Porch'], ['crawlspace', 'Crawlspace'], ['shed', 'Shed'], ['culvert', 'Culvert'],
    ['fence_opening', 'Fence opening'], ['road_crossing', 'Road crossing'], ['creek_crossing', 'Creek crossing'],
    ['dense_cover', 'Dense cover'], ['construction', 'Construction'], ['human_activity', 'Human activity']
  ],
  wildlife: [
    ['coyote', 'Coyote'], ['fox', 'Fox'], ['raccoon', 'Raccoon'], ['bobcat', 'Bobcat'], ['deer', 'Deer'],
    ['tracks', 'Tracks'], ['scat', 'Scat'], ['vocalization', 'Vocalization'], ['other_wildlife', 'Other wildlife']
  ],
  evidence: [
    ['camera_hit', 'Camera hit'], ['photo', 'Photo'], ['audio', 'Audio'], ['footprint', 'Footprint'],
    ['fur', 'Fur'], ['reported_observation', 'Reported observation']
  ]
}

export const PIN_TYPES = Object.values(OBJECT_TYPES).flat().map(([value, label]) => ({ value, label }))
