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
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const two = (n) => String(n).padStart(2, '0')
// One date format everywhere: "03 Jan 21:50", the same shape the server writes into drafts.
export const when = (iso) => { if (!iso) return ''; const d = new Date(iso); return isNaN(d) ? String(iso) : `${two(d.getDate())} ${MON[d.getMonth()]} ${two(d.getHours())}:${two(d.getMinutes())}` }
export const whenText = (t = '') => { const m = t.match(/(\d{1,2}) ([A-Za-z]+)(?: at)? (\d{1,2}:\d{2})/); return m ? `${two(m[1])} ${m[2].slice(0, 3)} ${m[3]}` : t }
