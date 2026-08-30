let token = ''
export const setToken = (t) => { token = t || '' }
const headers = (extra = {}) => token ? { ...extra, Authorization: `Bearer ${token}` } : extra
const j = async (r) => {
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!r.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    const message = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `${r.status} ${r.statusText || 'Request failed'}`
    throw new Error(message)
  }
  return data
}
export const get = (p) => fetch('/api/' + p, { headers: headers() }).then(j)
export const post = (p, body) => fetch('/api/' + p, { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify(body ?? {}) }).then(j)
export const upload = (file) => { const f = new FormData(); f.append('file', file); return fetch('/api/upload', { method: 'POST', headers: headers(), body: f }).then(j) }
export const when = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) }
