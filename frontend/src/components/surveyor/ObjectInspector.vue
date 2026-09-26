<script setup>
import TrailCameraEditor from './TrailCameraEditor.vue'
import { searchFreshness } from '../../surveyor/zoneState.js'

const props = defineProps({ selected: { type: Object, required: true }, types: { type: Array, required: true }, attachments: { type: Array, default: () => [] }, cameraHistory: { type: Array, default: () => [] }, uploading: Boolean, saving: Boolean, api: { type: String, required: true }, activeTool: { type: String, default: 'select' } })
const emit = defineEmits(['close', 'save', 'saveHistorical', 'move', 'deactivate', 'delete', 'editGeometry', 'saveGeometry', 'cancelGeometry', 'upload'])
const title = defineModel('title', { type: String })
const subtype = defineModel('subtype', { type: String })
const notes = defineModel('notes', { type: String })
const cameraHeading = defineModel('cameraHeading', { type: Number })
const cameraFov = defineModel('cameraFov', { type: Number })
const cameraRange = defineModel('cameraRange', { type: Number })
const attachmentCaption = defineModel('attachmentCaption', { type: String })
</script>

<template>
  <aside class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">{{ selected.object_type }} · #{{ selected.id }}</p><h2>{{ selected.name || 'Field object' }}</h2></div><button aria-label="Close inspector" @click="emit('close')">×</button></div>
    <label>Name<input v-model="title" maxlength="180" /></label>
    <label v-if="selected.object_type !== 'trail_camera' && !['zone','corridor'].includes(selected.object_type)">Type<select v-model="subtype"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
    <TrailCameraEditor v-if="selected.object_type === 'trail_camera'" v-model:heading="cameraHeading" v-model:fov="cameraFov" v-model:range="cameraRange" :history="cameraHistory" />
    <p v-if="selected.subtype === 'searched'" class="coverage-status">Coverage: {{ searchFreshness(selected) }} · {{ selected.properties?.searched_at ? new Date(selected.properties.searched_at).toLocaleDateString() : 'No search date recorded' }}</p>
    <label>Notes<textarea v-model="notes" rows="5"></textarea></label>
    <section class="attachment-list"><h3>Evidence attachments</h3><article v-for="attachment in attachments" :key="attachment.id"><img v-if="attachment.attachment_type === 'image'" :src="`${api}${attachment.media_url}`" :alt="attachment.caption || 'Evidence photo'" /><a v-else :href="`${api}${attachment.media_url}`" target="_blank" rel="noreferrer">{{ attachment.attachment_type === 'audio' ? 'Play audio evidence' : 'Open file' }}</a><p>{{ attachment.caption || attachment.source }}</p></article><label class="attachment-upload">{{ uploading ? 'Uploading…' : '＋ Add photo, audio, or file' }}<input type="file" accept="image/jpeg,image/png,image/webp,audio/mpeg,audio/wav,application/pdf,text/plain" :disabled="uploading" @change="emit('upload', $event)" /></label><input v-model="attachmentCaption" class="attachment-caption" placeholder="Attachment caption (optional)" /></section>
    <div v-if="['Polygon','LineString'].includes(selected.geometry.type) && activeTool !== 'edit'" class="inspector-buttons"><button class="secondary-button" @click="emit('editGeometry')">Edit geometry</button></div>
    <div v-if="selected.geometry.type === 'Point' && selected.object_type !== 'trail_camera'" class="inspector-buttons"><button class="secondary-button" @click="emit('move')">Move on map</button></div>
    <div v-if="activeTool === 'edit'" class="inspector-buttons"><button class="primary" @click="emit('saveGeometry')">Save geometry</button><button class="secondary-button" @click="emit('cancelGeometry')">Cancel</button></div>
    <p class="inspector-meta">Added {{ new Date(selected.created_at).toLocaleString() }}</p><div class="inspector-buttons"><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="emit('move')">Move on map</button><button v-if="activeTool !== 'edit'" class="primary" :disabled="saving" @click="emit('save')">{{ saving ? 'Saving…' : 'Save changes' }}</button><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="emit('saveHistorical')">Save current aim as historical placement</button><button v-if="selected.object_type === 'trail_camera'" class="danger-button" @click="emit('deactivate')">Deactivate</button><button v-else class="danger-button" @click="emit('delete')">Delete</button></div>
    <p v-if="['move-camera','move-object'].includes(activeTool)" class="map-hint inline-map-hint">Tap the new object location</p>
  </aside>
</template>
