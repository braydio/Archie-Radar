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

export function uploadMedia(api, target, file, { caption = '', observedAt = new Date().toISOString() } = {}) {
  const form = new FormData()
  form.append('file', file, file.name || 'field-media')
  form.append('caption', caption)
  form.append('observed_at', observedAt)
  const path = target.mapObjectId
    ? `/api/surveyor/objects/${target.mapObjectId}/attachments`
    : `/api/surveyor/sessions/${target.searchSessionId}/attachments`
  return fetch(`${api}${path}`, { method: 'POST', body: form }).then(async response => {
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || 'Could not save field media')
    return body
  })
}
