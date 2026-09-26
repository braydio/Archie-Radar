const labels = {
  search_started: event => `${event.after?.method || 'Field'} search started`,
  search_completed: event => `${event.after?.method || 'Field'} search completed`,
  search_coverage_created: () => 'Searched route coverage recorded',
  camera_moved: event => `${event.after?.name || 'Trail camera'} moved`,
  camera_aimed: event => `${event.after?.name || 'Trail camera'} aim updated`,
  camera_deactivated: event => `${event.before?.name || 'Trail camera'} deactivated`,
  evidence_added: event => `${event.after?.attachment_type || 'Evidence'} attachment added`,
  evidence_resolved: event => `Evidence ${event.after?.resolution?.replaceAll('_', ' ') || 'resolved'}`,
  evidence_reopened: () => 'Evidence reopened',
  access_created: () => 'Property access recorded',
  access_updated: event => event.after?.access_status ? `Access updated · ${event.after.access_status.replaceAll('_', ' ')}` : 'Access updated',
  task_created: event => `Follow-up added · ${event.after?.title || ''}`,
  task_completed: event => `Follow-up completed · ${event.after?.title || ''}`,
  task_reopened: event => `Follow-up reopened · ${event.after?.title || ''}`,
  task_dismissed: event => `Follow-up dismissed · ${event.after?.title || ''}`,
  object_link_created: () => 'Map objects linked',
  object_link_updated: () => 'Map link updated',
  object_link_deleted: () => 'Map link removed',
  attachment_deleted: () => 'Evidence attachment deleted',
}

export function eventLabel(event) {
  const label = labels[event.event_type]
  if (label) return label(event).trim()
  if (event.event_type === 'object_created') {
    const object = event.after || {}
    return `${object.subtype?.replaceAll('_', ' ') || object.object_type || 'Field object'} added`
  }
  if (event.event_type === 'object_updated') return `${event.after?.object_type || 'Field object'} updated`
  if (event.event_type === 'object_deleted') return `${event.before?.object_type || 'Field object'} archived`
  return event.action || event.event_type.replaceAll('_', ' ')
}
