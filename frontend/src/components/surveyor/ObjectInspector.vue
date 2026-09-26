<script setup>
import TrailCameraEditor from './TrailCameraEditor.vue'
import AudioRecorder from './AudioRecorder.vue'
import PhotoCapture from './PhotoCapture.vue'
import TaskEditor from './TaskEditor.vue'
import EvidenceEditor from './EvidenceEditor.vue'
import ChecklistEditor from './ChecklistEditor.vue'
import { searchFreshness } from '../../surveyor/zoneState.js'
import { metersToFeet } from '../../surveyor/units.js'
import { ref } from 'vue'

const props = defineProps({ selected: { type: Object, required: true }, types: { type: Array, required: true }, attachments: { type: Array, default: () => [] }, cameraHistory: { type: Array, default: () => [] }, tasks: { type: Array, default: () => [] }, accessRecord: { type: Object, default: null }, evidenceDraft: { type: Object, default: null }, uploading: Boolean, saving: Boolean, api: { type: String, required: true }, activeTool: { type: String, default: 'select' } })
const emit = defineEmits(['close', 'save', 'saveHistorical', 'move', 'deactivate', 'delete', 'editGeometry', 'saveGeometry', 'cancelGeometry', 'upload', 'deleteAttachment', 'mediaError', 'createTask', 'updateTask', 'saveEvidence', 'saveChecklist', 'editAccess', 'markSearched', 'markNeedsRecheck', 'openSession'])
const title = defineModel('title', { type: String })
const subtype = defineModel('subtype', { type: String })
const notes = defineModel('notes', { type: String })
const cameraHeading = defineModel('cameraHeading', { type: Number })
const cameraFov = defineModel('cameraFov', { type: Number })
const cameraRange = defineModel('cameraRange', { type: Number })
const attachmentCaption = defineModel('attachmentCaption', { type: String })
const taskEditorOpen = ref(false)
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
    <section class="inspector-followups"><div class="inspector-section-heading"><h3>Follow-ups</h3><button type="button" class="secondary-button" @click="taskEditorOpen=true">＋ Follow-up</button></div><article v-for="task in tasks" :key="task.id" class="inspector-task"><label><input type="checkbox" :checked="task.status === 'completed'" :disabled="task.status === 'dismissed'" @change="emit('updateTask', task, $event.target.checked ? 'completed' : 'open')" /><span>{{ task.title }}</span></label><small>{{ task.priority }} · {{ task.due_at ? new Date(task.due_at).toLocaleString() : 'No due date' }}</small></article><p v-if="!tasks.length" class="inspector-meta">No follow-ups recorded.</p></section>
    <section class="attachment-list"><h3>Evidence attachments</h3>
      <article v-for="attachment in attachments" :key="attachment.id" class="evidence-attachment">
        <img v-if="attachment.attachment_type === 'image'" :src="`${api}${attachment.media_url}`" :alt="attachment.caption || 'Evidence photo'" />
        <audio v-else-if="attachment.attachment_type === 'audio'" :src="`${api}${attachment.media_url}`" controls preload="none"></audio>
        <a v-else :href="`${api}${attachment.media_url}`" target="_blank" rel="noreferrer">Open file</a>
        <p>{{ attachment.caption || attachment.source }}</p>
        <small>{{ attachment.observed_at ? new Date(attachment.observed_at).toLocaleString() : new Date(attachment.created_at).toLocaleString() }}</small>
        <button type="button" class="danger-button" @click="emit('deleteAttachment', attachment)">Delete</button>
      </article>
      <input v-model="attachmentCaption" class="attachment-caption" placeholder="Caption for next attachment (optional)" />
      <PhotoCapture @select="emit('upload', $event)" />
      <AudioRecorder @select="emit('upload', $event)" @error="emit('mediaError', $event)" />
      <label class="attachment-upload">{{ uploading ? 'Uploading…' : '＋ Add file' }}<input type="file" accept="application/pdf,text/plain,audio/*,image/*" :disabled="uploading" @change="emit('upload', $event)" /></label>
    </section>
    <div v-if="['Polygon','LineString'].includes(selected.geometry.type) && activeTool !== 'edit'" class="inspector-buttons"><button class="secondary-button" @click="emit('editGeometry')">Edit geometry</button></div>
    <div v-if="selected.geometry.type === 'Point' && selected.object_type !== 'trail_camera'" class="inspector-buttons"><button class="secondary-button" @click="emit('move')">Move on map</button></div>
    <div v-if="activeTool === 'edit'" class="inspector-buttons"><button class="primary" @click="emit('saveGeometry')">Save geometry</button><button class="secondary-button" @click="emit('cancelGeometry')">Cancel</button></div>
    <p class="inspector-meta">Added {{ new Date(selected.created_at).toLocaleString() }}</p><div class="inspector-buttons"><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="emit('move')">Move on map</button><button v-if="activeTool !== 'edit'" class="primary" :disabled="saving" @click="emit('save')">{{ saving ? 'Saving…' : 'Save changes' }}</button><button v-if="selected.object_type === 'trail_camera'" class="secondary-button" @click="emit('saveHistorical')">Save current aim as historical placement</button><button v-if="selected.object_type === 'trail_camera'" class="danger-button" @click="emit('deactivate')">Deactivate</button><button v-else class="danger-button" @click="emit('delete')">Delete</button></div>
    <p v-if="['move-camera','move-object'].includes(activeTool)" class="map-hint inline-map-hint">Tap the new object location</p>
    <div v-if="taskEditorOpen" class="nested-sheet-backdrop"><TaskEditor :object="selected" @save="emit('createTask', $event); taskEditorOpen=false" @cancel="taskEditorOpen=false" /></div>
  </aside>
</template>
