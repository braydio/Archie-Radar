<script setup>
import { computed, ref, watch } from 'vue'
import { downloadMediaBundle } from '../../surveyor/mediaCapture.js'
import MediaLinkEditor from './MediaLinkEditor.vue'
const props = defineProps({ item: { type: Object, required: true }, api: { type: String, required: true } })
const emit = defineEmits(['close', 'delete', 'useLocation'])
const error = ref('')
const previewFailed = ref(false)
const url = computed(() => `${props.api}${props.item.preview_url || props.item.download_url}`)
watch(() => props.item.id, () => { previewFailed.value = false; error.value = '' })
function dateLabel(value) { return value ? new Date(value).toLocaleString() : 'Unknown' }
async function exportItem() {
  error.value = ''
  try {
    const response = await fetch(`${props.api}/api/surveyor/attachments/${props.item.id}/download`)
    if (!response.ok) throw new Error('Original media could not be downloaded')
    const blob = await response.blob()
    const file = new File([blob], props.item.original_filename, { type: props.item.mime_type })
    if (navigator.canShare?.({ files: [file] }) && navigator.share) await navigator.share({ files: [file], title: props.item.caption || file.name })
    else { const href = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = href; link.download = file.name; link.click(); setTimeout(() => URL.revokeObjectURL(href), 1000) }
  } catch (cause) { error.value = cause.message || 'Share is unavailable' }
}
async function exportBundle() {
  error.value = ''
  try { await downloadMediaBundle(props.api, [props.item.id]) }
  catch (cause) { error.value = cause.message || 'Evidence export failed' }
}
</script>
<template>
  <div class="media-viewer-backdrop" role="dialog" aria-modal="true" :aria-label="item.caption || item.original_filename" @click.self="emit('close')">
    <section class="media-viewer">
      <header><strong>{{ item.caption || item.original_filename }}</strong><button type="button" aria-label="Close media viewer" @click="emit('close')">×</button></header>
      <div class="media-viewer-stage">
        <img v-if="item.attachment_type === 'image' && !previewFailed" :src="url" :alt="item.caption || item.original_filename" @error="previewFailed=true" />
        <video v-else-if="item.attachment_type === 'video' && !previewFailed" :src="`${api}${item.download_url}`" :poster="item.thumbnail_url ? `${api}${item.thumbnail_url}` : undefined" controls playsinline preload="metadata" @error="previewFailed=true" />
        <div v-else-if="['image','video'].includes(item.attachment_type)" class="media-preview-unavailable">Preview unavailable <a :href="`${api}${item.download_url}`">Download original</a></div>
        <audio v-else-if="item.attachment_type === 'audio'" :src="`${api}${item.download_url}`" controls preload="metadata" />
        <div v-else class="media-preview-unavailable">Preview unavailable <a :href="`${api}${item.download_url}`">Download original</a></div>
      </div>
      <div class="media-viewer-metadata"><p>{{ dateLabel(item.observed_at || item.created_at) }} · {{ item.source }}</p><p>{{ item.map_object_name || item.session_label || 'Unlinked media' }} · {{ (item.file_size_bytes / 1048576).toFixed(1) }} MB</p><button type="button" class="secondary-button" @click="exportItem">Share / Download original</button><button type="button" class="secondary-button" @click="exportBundle">Export evidence bundle</button><button type="button" class="danger-button" @click="emit('delete', item)">Delete</button><p v-if="error" class="surveyor-error">{{ error }}</p>
        <details><summary>Details</summary><dl><dt>Filename</dt><dd>{{ item.original_filename }}</dd><dt>Type</dt><dd>{{ item.mime_type }}</dd><dt>Dimensions</dt><dd>{{ item.width && item.height ? `${item.width} × ${item.height}` : 'Not available' }}</dd><dt>Duration</dt><dd>{{ item.duration_seconds ? `${Math.round(item.duration_seconds)} sec` : 'Not available' }}</dd><dt>Caption</dt><dd>{{ item.caption || 'None' }}</dd><dt>Capture coordinates</dt><dd>{{ item.latitude != null ? `${item.latitude}, ${item.longitude}` : 'Not recorded' }}</dd></dl><p v-if="item.metadata?.exif_gps">Photo contains GPS metadata. It has not changed the map object location.</p><button v-if="item.metadata?.exif_gps" type="button" class="secondary-button" @click="emit('useLocation', { attachmentId: item.id, ...item.metadata.exif_gps })">Use photo location on map</button><MediaLinkEditor :api="api" :attachment-id="item.id" /></details>
      </div>
    </section>
  </div>
</template>
