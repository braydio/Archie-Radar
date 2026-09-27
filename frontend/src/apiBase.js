const configuredBase = import.meta.env.VITE_API_BASE?.trim()
const configuredPort = Number(import.meta.env.VITE_API_PORT) || 8000

export const API_BASE = configuredBase || `${window.location.protocol}//${window.location.hostname}:${configuredPort}`
