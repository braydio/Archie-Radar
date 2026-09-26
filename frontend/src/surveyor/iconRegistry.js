const icons = {
  'sighting': 'markers/sighting.svg', 'possible-sighting': 'markers/possible-sighting.svg',
  'checked-location': 'markers/checked-location.svg', 'trail-camera': 'markers/trail-camera.svg',
  'food-water-station': 'markers/food-water-station.svg', 'trap': 'markers/trap.svg',
  'scent-item': 'markers/scent-item.svg', 'flyer': 'markers/flyer.svg', 'search-start': 'markers/search-start.svg',
  'dog': 'markers/dog.svg', 'outdoor-cat': 'markers/outdoor-cat.svg', 'shelter-porch': 'markers/shelter-porch.svg',
  'culvert': 'markers/culvert.svg', 'fence-gap': 'markers/fence-gap.svg', 'road-crossing': 'markers/road-crossing.svg',
  'creek-crossing': 'markers/creek-crossing.svg', 'human-activity': 'markers/human-activity.svg',
  'coyote': 'markers/coyote.svg', 'fox': 'markers/fox.svg', 'raccoon': 'markers/raccoon.svg', 'bobcat': 'markers/bobcat.svg',
  'deer': 'markers/deer.svg', 'wildlife-tracks': 'markers/wildlife-tracks.svg', 'wildlife-vocalization': 'markers/wildlife-vocalization.svg',
  'camera-hit': 'markers/camera-hit.svg', 'evidence-photo': 'markers/evidence-photo.svg', 'evidence-audio': 'markers/evidence-audio.svg',
  'note': 'markers/note.svg', 'home': 'map/home.svg', 'probe': 'map/probe.svg', 'snap-point': 'map/snap-point.svg',
  'snap-line': 'map/snap-line.svg', 'camera-history': 'map/camera-history.svg', 'direction-arrow': 'map/direction-arrow.svg'
}
const assetUrls = import.meta.glob('../assets/surveyor/**/*.svg', { eager: true, query: '?url', import: 'default' })

export async function registerSurveyorIcons(map) {
  const registered = [], missing = []
  await Promise.all(Object.entries(icons).map(async ([name, path]) => {
    const asset = Object.entries(assetUrls).find(([file]) => file.endsWith(`/${path}`))?.[1]
    if (!asset) { missing.push(name); return }
    try {
      const image = new Image(); image.src = asset; await image.decode()
      if (!map.hasImage(name)) map.addImage(name, image, { pixelRatio: 2 })
      registered.push(name)
    }
    catch { missing.push(name) }
  }))
  return { registered, missing }
}

export const SURVEYOR_ICON_PATHS = Object.freeze(icons)
