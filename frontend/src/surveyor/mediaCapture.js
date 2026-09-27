/** Browser media capture helpers. Captured media is only returned to the caller;
 * this module never sends data anywhere. */
export function canCaptureMedia() {
  return typeof window !== 'undefined' && window.isSecureContext === true &&
    Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined'
}

export function mediaCaptureError(error) {
  if (!window.isSecureContext) return 'Media capture requires HTTPS (or localhost). You can still attach an existing file.'
  if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') return 'Permission was denied. You can still attach an existing file.'
  if (error?.name === 'NotFoundError' || error?.name === 'DevicesNotFoundError') return 'No compatible media device was found.'
  return error?.message || 'Media capture is unavailable. You can still attach an existing file.'
}

export function supportedAudioMimeType() {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return ''
  return ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg']
    .find(type => MediaRecorder.isTypeSupported(type)) || ''
}

export function stopMediaTracks(stream) {
  stream?.getTracks().forEach(track => track.stop())
}

export function uploadMedia(api, target, file, {
  caption = '', notes = '', observedAt = new Date().toISOString(), source = 'user capture',
  latitude, longitude, durationSeconds = file?.duration_seconds, width = file?.media_width, height = file?.media_height,
} = {}) {
  const form = new FormData()
  form.append('file', file, file.name || 'field-media')
  form.append('caption', caption)
  form.append('observed_at', observedAt)
  form.append('notes', notes)
  form.append('source', source)
  if (latitude != null && longitude != null) { form.append('latitude', String(latitude)); form.append('longitude', String(longitude)) }
  if (durationSeconds != null) form.append('duration_seconds', String(durationSeconds))
  if (width != null && height != null) { form.append('width', String(width)); form.append('height', String(height)) }
  const path = target.mapObjectId
    ? `/api/surveyor/objects/${target.mapObjectId}/attachments`
    : `/api/surveyor/sessions/${target.searchSessionId}/attachments`
  return fetch(`${api}${path}`, { method: 'POST', body: form }).then(async response => {
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || 'Could not save field media')
    return body
  })
}

export async function downloadMediaBundle(api, attachmentIds, options = {}) {
  if (!attachmentIds.length) throw new Error('No media was selected for export')
  const response = await fetch(`${api}/api/surveyor/media/export`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_ids: attachmentIds, include_originals: true, include_manifest_json: true,
      include_manifest_csv: true, include_context: true, include_exact_coordinates: true, ...options }),
  })
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || 'Media export failed') }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url
  link.download = `archie-radar-export-${new Date().toISOString().slice(0, 10)}.zip`
  link.click(); URL.revokeObjectURL(url)
}
