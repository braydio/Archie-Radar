export const SURVEYOR_DRAFT_KEY = 'archie-radar-surveyor-draft'

export function storeSurveyorDraft(kind, payload) {
  try { sessionStorage.setItem(SURVEYOR_DRAFT_KEY, JSON.stringify({ kind, payload, saved_at: new Date().toISOString() })) } catch {}
}

export function readSurveyorDraft() {
  try { return JSON.parse(sessionStorage.getItem(SURVEYOR_DRAFT_KEY) || 'null') } catch { return null }
}

export function clearSurveyorDraft(kind) {
  try {
    const current = readSurveyorDraft()
    if (!kind || current?.kind === kind) sessionStorage.removeItem(SURVEYOR_DRAFT_KEY)
  } catch {}
}
