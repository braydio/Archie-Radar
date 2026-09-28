<script setup>
import TrailCameraEditor from './TrailCameraEditor.vue'
import MediaCaptureSheet from './MediaCaptureSheet.vue'
import MediaGallery from '../media/MediaGallery.vue'
import TaskEditor from './TaskEditor.vue'
import EvidenceEditor from './EvidenceEditor.vue'
import ChecklistEditor from './ChecklistEditor.vue'
import { searchFreshness } from '../../surveyor/zoneState.js'
import { metersToFeet } from '../../surveyor/units.js'
import { downloadMediaBundle } from '../../surveyor/mediaCapture.js'
import { ref } from 'vue'

const props = defineProps({ selected: { type: Object, required: true }, types: { type: Array, required: true }, attachments: { type: Array, default: () => [] }, cameraHistory: { type: Array, default: () => [] }, tasks: { type: Array, default: () => [] }, accessRecord: { type: Object, default: null }, evidenceDraft: { type: Object, default: null }, uploading: Boolean, saving: Boolean, api: { type: String, required: true }, activeTool: { type: String, default: 'select' } })
const emit = defineEmits(['close', 'save', 'saveHistorical', 'move', 'deactivate', 'delete', 'editGeometry', 'saveGeometry', 'cancelGeometry', 'upload', 'deleteAttachment', 'mediaError', 'mediaLocation', 'createTask', 'updateTask', 'saveEvidence', 'saveChecklist', 'editAccess', 'markSearched', 'markNeedsRecheck', 'openSession', 'addOuting', 'addTaskOuting'])
const title = defineModel('title', { type: String })
const subtype = defineModel('subtype', { type: String })
const notes = defineModel('notes', { type: String })
const cameraHeading = defineModel('cameraHeading', { type: Number })
const cameraFov = defineModel('cameraFov', { type: Number })
const cameraRange = defineModel('cameraRange', { type: Number })
const attachmentCaption = defineModel('attachmentCaption', { type: String })
const taskEditorOpen = ref(false)
const mediaOpen = ref(false)
const exportingMedia = ref(false)
async function exportMedia() {
  if (!props.attachments.length) return
  if (!confirm(`Export ${props.attachments.length} media items linked to this ${props.selected.object_type}? Private contact details are excluded.`)) return
  exportingMedia.value = true
  try { await downloadMediaBundle(props.api, props.attachments.map(item => item.id)) }
  catch (cause) { emit('mediaError', cause.message) }
  finally { exportingMedia.value = false }
}
</script>

<template>
  <aside class="surveyor-inspector"><div class="inspector-heading"><div><p class="eyebrow">{{ selected.object_type }} · #{{ selected.id }}</p><h2>{{ selected.name || 'Field object' }}</h2></div><button aria-label="Close inspector" @click="emit('close')">×</button></div>
    <label>Name<input v-model="title" maxlength="180" /></label>
    <label v-if="selected.object_type !== 'trail_camera' && !['zone','corridor'].includes(selected.object_type)">Type<select v-model="subtype"><option v-for="item in types" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
    <TrailCameraEditor v-if="selected.object_type === 'trail_camera'" v-model:heading="cameraHeading" v-model:fov="cameraFov" v-model:range="cameraRange" :history="cameraHistory" />
    <section v-if="selected.subtype === 'searched'" class="coverage-status"><p>Coverage: {{ searchFreshness(selected) }} · {{ selected.properties?.searched_at ? new Date(selected.properties.searched_at).toLocaleDateString() : 'No search date recorded' }}</p><p v-if="selected.properties?.search_method">Method: {{ selected.properties.search_method.replaceAll('_', ' ') }}<span v-if="selected.properties?.buffer_meters"> · {{ Math.round(metersToFeet(selected.properties.buffer_meters)) }} ft buffer</span></p><button type="button" class="secondary-button" @click="emit('markSearched')">Mark searched again</button><button v-if="selected.properties?.search_session_id" type="button" class="secondary-button" @click="emit('openSession', selected.properties.search_session_id)">Open search session</button><button type="button" class="secondary-button" @click="emit('markNeedsRecheck')">Needs re-check</button></section>
    <section v-if="selected.object_type === 'access'" class="access-summary"><div class="inspector-section-heading"><h3>Property access</h3><button type="button" class="secondary-button" @click="emit('editAccess')">Edit</button></div><p :class="{ 'do-not-contact': accessRecord?.access_status === 'do_not_contact' }">{{ (accessRecord?.access_status || selected.subtype || 'unknown').replaceAll('_', ' ') }}</p><p v-if="accessRecord">{{ accessRecord.dog_count ?? 'Unknown' }} dogs · {{ accessRecord.outdoor_cat_count ?? 'Unknown' }} outdoor cats</p><p v-if="accessRecord">Search {{ accessRecord.search_permission }} · Camera {{ accessRecord.camera_permission }} · Trap {{ accessRecord.trap_permission }}</p><p v-if="accessRecord?.contact_notes">{{ accessRecord.contact_notes }}</p></section>
    <label>Notes<textarea v-model="notes" rows="5"></textarea></label>
    <EvidenceEditor v-if="selected.object_type === 'evidence'" :object="selected" :saving="saving" :initial-form="evidenceDraft" @save="emit('saveEvidence', $event)" />
    <ChecklistEditor v-if="selected.object_type === 'note'" :object="selected" @save="emit('saveChecklist', $event)" @followup="emit('createTask', { title: $event.text, task_type: 'other', priority: 'normal', map_object_id: selected.id })" />
    <section class="inspector-followups"><div class="inspector-section-heading"><h3>Follow-ups</h3><button type="button" class="secondary-button" @click="taskEditorOpen=true">＋ Follow-up</button></div><article v-for="task in tasks" :key="task.id" class="inspector-task"><label><input type="checkbox" :checked="task.status === 'completed'" :disabled="task.status === 'dismissed'" @change="emit('updateTask', task, $event.target.checked ? 'completed' : 'open')" /><span>{{ task.title }}</span></label><small>{{ task.priority }} · {{ task.due_at ? new Date(task.due_at).toLocaleString() : 'No due date' }} <button type="button" class="outing-inline-link" @click="emit('addTaskOuting', task)">Add to outing</button></small></article><p v-if="!tasks.length" class="inspector-meta">No follow-ups recorded.</p></section>
    <section class="attachment-list"><div class="inspector-section-heading"><h3>Media · {{ attachments.length }}</h3><button v-if="attachments.length" type="button" class="secondary-button" :disabled="exportingMedia" @click="exportMedia">{{ exportingMedia ? 'Preparing…' : `Export ${selected.object_type === 'trail_camera' ? 'camera' : selected.object_type === 'evidence' ? 'evidence' : 'media'} bundle` }}</button></div><MediaGallery :items="attachments" :api="api" title="" @delete="emit('deleteAttachment', $event)" @use-location="emit('mediaLocation', $event)" />
      <input v-model="attachmentCaption" class="attachment-caption" placeholder="Caption for next media (optional)" />
      <button type="button" class="secondary-button" :disabled="uploading" @click="mediaOpen=!mediaOpen">{{ uploading ? 'Uploading…' : '＋ Media' }}</button>
      <MediaCaptureSheet v-if="mediaOpen" :api="api" @select="emit('upload', $event); mediaOpen=false" @cancel="mediaOpen=false" @error="emit('mediaError', $event)" />
    </section>
    <div v-if="['Polygon','LineString'].includes(selected.geometry.type) && activeTool !== 'edit'" class="inspector-buttons"><button class="secondary-button" @click="emit('editGeometry')">Edit geometry</button></div>
    <div v-if="selected.geometry.type === 'Point' && selected.object_type !== 'trail_camera'" class="inspector-buttons"><button class="secondary-button" @click="emit('move')">Move on map</button></div>
    <div v-if="activeTool === 'edit'" class="inspector-buttons"><button class="primary" @click="emit('saveGeometry')">Save geometry</button><button class="secondary-button" @click="emit('cancelGeometry')">Cancel</button></div>
    <p class="inspector-meta">Added {{ new Date(selected.created_at).toLocaleString() }}</p><div class="inspector-buttons"><button v-if="activeTool !== 'edit'" class="secondary-button" @click="emit('addOuting')">＋ Add to outing</button><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="emit('move')">Move on map</button><button v-if="activeTool !== 'edit'" class="primary" :disabled="saving" @click="emit('save')">{{ saving ? 'Saving…' : 'Save changes' }}</button><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="emit('saveHistorical')">Save current aim as historical placement</button><button v-if="selected.object_type === 'trail_camera'" class="danger-button" @click="emit('deactivate')">Deactivate</button><button v-else class="danger-button" @click="emit('delete')">Delete</button></div>
    <p v-if="['move-camera','move-object'].includes(activeTool)" class="map-hint inline-map-hint">Tap the new object location</p>
    <div v-if="taskEditorOpen" class="nested-sheet-backdrop"><TaskEditor :object="selected" @save="emit('createTask', $event); taskEditorOpen=false" @cancel="taskEditorOpen=false" /></div>
  </aside>
</template>
