import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import { get, when, whenText } from './api'
import { Btn, Card, CardTitle, Drawer, ErrorState, Icon, I, IconBtn, Loading, issueKind, kindIcon, statusText } from './ui'
import { Detail } from './Approvals'
import { Quarantined } from './Attention'

export const FILTERS = ['All', 'Waiting approval', 'Approved', 'Resolved', 'Set aside']
const RULE_IDS = Array.from({ length: 11 }, (_, i) => `R${i + 1}`)
const TRUCK = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f3efe6" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 7h11v9H2zM13 10h4l3 3v3h-7z"/><circle cx="6" cy="17.5" r="1.5"/><circle cx="17" cy="17.5" r="1.5"/></svg>'
const pinIcon = (sel) => L.divIcon({ className: sel ? 'pin-sel' : '', iconSize: [36, 36], iconAnchor: [18, 18], html: `<div style="width:36px;height:36px;border-radius:50%;background:#161617;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.35)">${TRUCK}</div>` })
const hubIcon = L.divIcon({ className: '', iconSize: [14, 14], iconAnchor: [7, 7], html: '<div style="width:14px;height:14px;border-radius:50%;background:#fff;border:3px solid #161617"></div>' })

// Rows are built from strings the API already returns; no new backend fields. ponytail: regex on fixed server templates.
const parseSummary = (s = '') => { const m = s.match(/^Truck (\S+) broke down (\d+) km from ([^,]+), (.*)$/); return m ? { truck: m[1], km: +m[2], origin: m[3], issue: m[4] } : { truck: '', km: 0, origin: '', issue: s } }
const parseReplacement = (s = '') => s.match(/^Replacement (\S+) dispatched from (.+) hub$/)?.slice(1) || [null, null]
const parseBody = (a) => ({ dest: a?.summary.match(/, \S+ to (.+)$/)?.[1] || '', eta: whenText(a?.body.match(/revised delivery time[^\d]*?(\d{1,2} \w{3,9}(?: at)? \d{1,2}:\d{2})/i)?.[1] || '') })
const skippedBy = (why = '') => [...why.matchAll(/(\d+) skipped by (R\d+)/g)].map(m => [m[2], +m[1]])

export function buildRows({ items }, { pending, sent }, { quarantined }) {
  const appr = Object.fromEntries([...pending, ...sent].map(a => [a.ticket_id, a]))
  const rows = items.map(b => {
    const p = parseSummary(b.summary), [rep, repHub] = parseReplacement(b.replacement_line), a = appr[b.ticket_id], body = parseBody(a)
    const status = b.status === 'Awaiting approval' ? 'Waiting approval' : a?.status === 'sent' ? 'Approved' : 'Resolved'
    return { ...b, ...p, kind: issueKind(p.issue), replacement: rep, replacement_hub: repHub || b.replacement_hub, dest: body.dest, eta: body.eta, status, approval: a, why: a?.why || '' }
  })
  const files = {}; quarantined.filter(q => q.reason === 'unrecognized_format').forEach(q => { files[q.source_file] = (files[q.source_file] || 0) + 1 })
  const heldFiles = Object.entries(files).map(([f, n]) => ({ ticket_id: f.split(/[\\/]/).pop(), client: `${n} records held`, truck: '', origin: '', dest: '', issue: 'New format, mapping awaits approval', kind: 'Other', at: '', status: 'Set aside', held: true, replacement: null, eta: '', summary: '', severity: 'HIGH', point: null, rules: [] }))
  const setAside = quarantined.filter(q => q.reason !== 'unrecognized_format').map(q => ({ ticket_id: q.ticket_id, client: q.record.client || '—', truck: q.record.vehicle || '', origin: q.record.origin_hub || '', dest: q.record.destination || '', issue: q.record.issue || q.detail, kind: issueKind(q.record.issue), at: q.record.created_at, status: 'Set aside', quarantine: q, replacement: null, eta: '', summary: q.detail, severity: 'HIGH', point: null, rules: [] }))
  return [...rows, ...setAside, ...heldFiles]
}

function Focus({ item }) {
  const map = useMap()
  useEffect(() => { if (item?.point) map.flyTo([item.point.lat, item.point.lon], 9, { duration: 0.6 }) }, [item, map])
  return null
}
function Resize({ dep }) { const map = useMap(); useEffect(() => { setTimeout(() => map.invalidateSize(), 250) }, [dep, map]); return null }

export function FleetMap({ items, hubs, selected, onSelect, expanded }) {
  return (
    <MapContainer center={[28.4, 77.8]} zoom={6} zoomControl={false} className="z-0 h-full w-full" scrollWheelZoom={false}>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
      <ZoomBottomRight />
      <Resize dep={expanded} />
      {Object.entries(hubs || {}).map(([n, h]) => <Marker key={n} position={[h.lat, h.lon]} icon={hubIcon} alt={`${n} hub`} title={`${n} hub`}><Tooltip direction="right" offset={[8, 0]} permanent className="hub-tip">{n}</Tooltip></Marker>)}
      {items.filter(b => b.point && b.status !== 'Resolved' && b.status !== 'Approved').map(b => (
        <span key={b.ticket_id}>
          {b.hub && <Polyline positions={[[b.hub.lat, b.hub.lon], [b.point.lat, b.point.lon]]} pathOptions={{ color: '#161617', weight: 1.5, dashArray: '5 6', opacity: .7 }} />}
          <Marker position={[b.point.lat, b.point.lon]} icon={pinIcon(selected === b.ticket_id)} alt={`${b.severity} severity breakdown: ${b.summary}`} title={b.ticket_id} eventHandlers={{ click: () => onSelect?.(b.ticket_id) }}>
            {selected === b.ticket_id && <Tooltip direction="right" offset={[22, 0]} permanent interactive className="pin-tip"><div className="text-[15px] font-bold">#{b.ticket_id}</div><div className="mt-0.5 text-[13px] text-[#6b6963]">{b.issue.split(',')[0]} · {b.truck}</div></Tooltip>}
          </Marker>
        </span>
      ))}
      <Focus item={items.find(b => b.ticket_id === selected)} />
    </MapContainer>
  )
}
function ZoomBottomRight() { const map = useMap(); useEffect(() => { const c = L.control.zoom({ position: 'bottomright' }).addTo(map); return () => c.remove() }, [map]); return null }

// Semicircle gauge, red → gold → green like the reference. ponytail: pure SVG, no chart lib.
function Gauge({ pct, caption }) {
  const r = 140, cx = 150, cy = 150, a = Math.PI * (1 - pct / 100), x = cx + r * Math.cos(a), y = cy - r * Math.sin(a)
  return (
    <div className="relative mt-2">
      <svg viewBox="0 0 300 170" className="w-full">
        <defs><linearGradient id="gg" x1="0" x2="1"><stop offset="0" stopColor="#e0604f" /><stop offset=".5" stopColor="#d8cba3" /><stop offset="1" stopColor="#5fc78a" /></linearGradient></defs>
        <path d={`M10 150 A140 140 0 0 1 290 150`} fill="none" stroke="#353538" strokeWidth="3" />
        {pct > 0 && <path d={`M10 150 A140 140 0 ${pct > 50 ? 1 : 0} 1 ${x} ${y}`} fill="none" stroke="url(#gg)" strokeWidth="3" strokeLinecap="round" />}
        <circle cx={x} cy={y} r="6" fill="#f3efe6" />
        <g transform={`translate(${x} ${y - 30})`}><rect x="-26" y="-13" width="52" height="26" rx="13" fill="#f3efe6" /><text textAnchor="middle" y="5" fontSize="14" fontWeight="700" fill="#161617">{pct}%</text></g>
        <text x="10" y="168" fontSize="12" fill="#78756e">0%</text><text x="290" y="168" fontSize="12" fill="#78756e" textAnchor="end">100%</text>
      </svg>
      <div className="mt-1 text-center text-sm text-sub">{caption}</div>
    </div>
  )
}

function Route({ origin, dest }) {
  return (
    <div className="flex flex-col gap-0.5 text-[14px] leading-tight">
      <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full border border-mute" />{origin || '—'}</div>
      <div className="ml-[3px] h-2 w-px bg-mute/50" />
      <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-sub" />{dest || 'Unknown'}</div>
    </div>
  )
}

export default function Dashboard({ tick, onHistory, onChange, filter, setFilter, mobileView }) {
  const [d, setD] = useState(null)
  const [sel, setSel] = useState(null)
  const [openRow, setOpenRow] = useState(null)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('Status')
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true); setError(null)
    try {
      const [b, a, t] = await Promise.all([get('breakdowns'), get('approvals'), get('attention')])
      if (request === latest.current) setD({ b, a, t })
    } catch (reason) { if (request === latest.current) setError(reason) }
    finally { if (request === latest.current) setLoading(false) }
  }, [])
  useEffect(() => { const f = requestAnimationFrame(() => { void load() }); return () => { cancelAnimationFrame(f); latest.current += 1 } }, [load, tick])
  const rows = useMemo(() => d ? buildRows(d.b, d.a, d.t) : [], [d])
  const stats = useMemo(() => {
    const kinds = {}; rows.forEach(r => { kinds[r.kind] = (kinds[r.kind] || 0) + 1 })
    const top = Object.entries(kinds).sort((x, y) => y[1] - x[1]).slice(0, 4)
    const real = rows.filter(r => !r.held)
    const resolved = real.filter(r => r.status === 'Resolved' || r.status === 'Approved').length
    const fired = {}; rows.forEach(r => r.rules?.forEach(x => { fired[x.id] = (fired[x.id] || 0) + 1 }))
    const skipped = {}; rows.forEach(r => skippedBy(r.why).forEach(([id, n]) => { skipped[id] = (skipped[id] || 0) + n }))
    const topSkip = Object.entries(skipped).sort((x, y) => y[1] - x[1])
    const topFire = Object.entries(fired).sort((x, y) => y[1] - x[1])[0]
    return { top, resolved, total: real.length, fired, skipped: topSkip[0], topFire, interventions: Object.values(fired).reduce((s, n) => s + n, 0) }
  }, [rows])
  const attention = d ? [['Quarantined', d.t.quarantined.filter(q => q.reason !== 'unrecognized_format').length, 'Set aside', 'red', I.alert], ['Format warnings', d.t.alerts.length + (d.t.format_maps?.length || 0), 'audit', 'gold', I.box], ['Pending approvals', d.a.pending.length, 'Waiting approval', 'gold', I.inbox]] : []
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const list = rows.filter(r => (filter === 'All' || r.status === filter) && (!needle || [r.ticket_id, r.truck, r.client, r.issue, r.origin, r.dest].join(' ').toLowerCase().includes(needle)))
    const order = { 'Waiting approval': 0, 'Set aside': 1, Approved: 2, Resolved: 3 }
    return sort === 'Status' ? [...list].sort((a, b) => order[a.status] - order[b.status] || (b.at || '').localeCompare(a.at || '')) : [...list].sort((a, b) => (b.at || '').localeCompare(a.at || ''))
  }, [rows, q, filter, sort])
  const current = rows.find(r => r.ticket_id === openRow)
  const done = async () => { await load(); await onChange(); setOpenRow(null) }
  if (loading && !d) return <Loading label="Loading breakdowns" />
  if (error) return <ErrorState error={error} onRetry={load} title="Could not load breakdowns." />

  const left = (
    <div className="flex flex-col gap-4">
      <Card>
        <CardTitle action="Show all breakdowns" onAction={() => setFilter('All')}>Today's breakdowns</CardTitle>
        <div className="mt-5 flex flex-wrap gap-2.5">
          {stats.top.map(([k, n]) => <button key={k} onClick={() => setQ(k === 'Other' ? '' : k.toLowerCase().slice(0, 4))} className="flex h-11 items-center gap-2 rounded-full bg-card2 px-4 text-[15px] hover:bg-card3"><Icon d={kindIcon(k)} size={18} /><span className="font-medium">{k}</span><span className="text-sub">{n}</span></button>)}
        </div>
        <Gauge pct={stats.total ? Math.round(100 * stats.resolved / stats.total) : 0} caption={`${stats.resolved} of ${stats.total} resolved (${stats.total ? Math.round(100 * stats.resolved / stats.total) : 0}%)`} />
      </Card>
      <Card>
        <CardTitle action="Open audit" onAction={() => setFilter('audit')}>Needs attention</CardTitle>
        <div className="mt-4 flex flex-col gap-1">
          {attention.map(([label, n, target, color, ic]) => { const max = Math.max(1, ...attention.map(a => a[1])); return (
            <button key={label} onClick={() => setFilter(target)} className="-mx-2 flex h-11 items-center gap-3 rounded-xl px-2 text-left hover:bg-card2">
              <span className="text-sub"><Icon d={ic} size={20} /></span><span className="w-[150px] text-[15px]">{label}</span><span className="w-8 font-semibold">{n}</span>
              <span className="h-2 grow overflow-hidden rounded-full bg-card3"><span className={`block h-full rounded-full ${color === 'red' ? 'bg-red' : 'bg-gold'}`} style={{ width: `${100 * n / max}%` }} /></span>
            </button>) })}
        </div>
      </Card>
      <Card>
        <CardTitle action="Open evaluator" onAction={() => setFilter('eval')}>Rule activity</CardTitle>
        <div className="mt-4 grid grid-cols-3 items-end">
          <div><div className="text-[15px] font-semibold">{stats.skipped ? `${stats.skipped[1]} grounded` : '0 grounded'}</div><div className="text-sm text-sub">{stats.skipped ? stats.skipped[0] : '—'}</div></div>
          <div className="text-center"><div className="whitespace-nowrap text-[13px] text-sub">Rule interventions</div><div className="text-[40px] font-semibold leading-none tracking-tight">{stats.interventions}</div></div>
          <div className="text-right"><div className="text-[15px] font-semibold">{stats.topFire ? `${stats.topFire[1]} fired` : '0 fired'}</div><div className="text-sm text-sub">{stats.topFire ? stats.topFire[0] : '—'}</div></div>
        </div>
        <div className="mt-5 flex h-20 items-end gap-1.5">{RULE_IDS.map(id => { const n = stats.fired[id] || 0, max = Math.max(1, ...Object.values(stats.fired)); return <div key={id} title={`${id}: ${n}`} className="flex grow flex-col items-center gap-1"><div className="w-full rounded-sm bg-gold" style={{ height: `${Math.max(3, 64 * n / max)}px`, opacity: n ? 1 : .25 }} /><span className="text-[10px] text-mute">{id}</span></div> })}</div>
      </Card>
    </div>
  )
  const map = (
    <div className={expanded ? 'fixed inset-3 z-40' : 'relative h-[420px] md:h-[520px]'}>
      <div className="h-full w-full overflow-hidden rounded-3xl">
        <FleetMap items={rows} hubs={d.b.hubs} selected={sel} onSelect={id => { setSel(id); setOpenRow(id) }} expanded={expanded} />
      </div>
      <div className="absolute left-4 top-4 z-[500] flex flex-wrap gap-2.5 pr-16">
        <label className="flex h-11 w-[260px] max-w-[calc(100vw-140px)] items-center gap-2 rounded-full bg-white px-4 text-[#161617] shadow-md"><Icon d={I.search} size={18} /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Search ticket, truck, client…" aria-label="Search breakdowns" className="w-full bg-transparent text-[15px] outline-none placeholder:text-[#8a877f]" /></label>
        <button onClick={() => setSort(s => s === 'Status' ? 'Newest' : 'Status')} className="flex h-11 items-center gap-1.5 rounded-full bg-white px-4 text-[15px] text-[#161617] shadow-md"><span className="text-[#8a877f]">Sort by</span><span className="font-semibold">{sort}</span><Icon d={I.chev} size={16} /></button>
      </div>
      <button onClick={() => setExpanded(e => !e)} aria-label={expanded ? 'Shrink map' : 'Expand map'} className="absolute right-4 top-4 z-[500] flex h-11 w-11 items-center justify-center rounded-full bg-white text-[#161617] shadow-md"><Icon d={expanded ? I.x : I.expand} size={18} /></button>
    </div>
  )
  const table = (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-col gap-4 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
        <h2 className="text-[21px] font-semibold tracking-tight">Breakdowns</h2>
        <div className="flex min-w-0 items-center gap-2">
          <div role="tablist" className="flex min-w-0 max-w-full gap-1 overflow-x-auto rounded-full bg-card2 p-1">{FILTERS.map(f => <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)} className={`h-10 shrink-0 rounded-full px-4 text-[14px] font-medium ${filter === f ? 'bg-gold text-frame' : 'text-ink hover:bg-card3'}`}>{f}</button>)}</div>
          <IconBtn aria-label="Newest first" onClick={() => setSort('Newest')} className={`hidden lg:flex ${sort === 'Newest' ? 'text-gold' : ''}`}><Icon d={I.cal} size={18} /></IconBtn>
          <IconBtn aria-label="Sort by status" onClick={() => setSort('Status')} className={`hidden lg:flex ${sort === 'Status' ? 'text-gold' : ''}`}><Icon d={I.filter} size={18} /></IconBtn>
        </div>
      </div>
      {shown.length === 0 ? <div className="px-6 pb-8 text-sub">No breakdowns match.</div> : <>
        <div className="hidden overflow-x-auto md:block"><table className="w-full table-fixed text-[15px]"><colgroup>{[17, 23, 16, 18, 13, 13].map((w, i) => <col key={i} style={{ width: `${w}%` }} />)}</colgroup>
          <thead><tr className="text-left text-[13px] text-mute">{['Ticket', 'Client', 'Route', 'Replacement', 'ETA', 'Status'].map((h, i) => <th key={h} className={`border-t border-white/5 px-4 py-3 font-medium ${i === 5 ? 'text-right' : ''}`}>{h}</th>)}</tr></thead>
          <tbody>{shown.map(r => (
            <tr key={r.ticket_id} onClick={() => { setOpenRow(r.ticket_id); setSel(r.ticket_id) }} tabIndex="0" onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpenRow(r.ticket_id) } }} className={`cursor-pointer border-t border-white/5 hover:bg-card2 ${sel === r.ticket_id ? 'bg-card2' : ''}`}>
              <td className="px-4 py-4"><div className="flex items-center gap-2.5"><Icon d={I.truck} size={22} className="shrink-0" /><span className="truncate font-semibold">#{r.ticket_id}</span></div></td>
              <td className="px-4 py-4"><div className="truncate">{r.client}</div><div className="truncate text-[13px] text-sub">{r.kind}{r.truck ? ` · ${r.truck}` : ''}</div></td>
              <td className="px-4 py-4"><Route origin={r.origin} dest={r.dest} /></td>
              <td className="px-4 py-4"><div className="truncate">{r.replacement || <span className="text-sub">{r.status === 'Set aside' ? 'Held' : 'Manual'}</span>}</div>{r.replacement && <div className="text-[13px] text-sub">{r.replacement_hub} hub</div>}</td>
              <td className="px-4 py-4 text-[14px]">{r.eta || (r.at ? when(r.at) : '—')}</td>
              <td className={`px-4 py-4 text-right text-[14px] font-medium leading-tight ${statusText(r.status)}`}>{r.status}</td>
            </tr>))}</tbody>
        </table></div>
        <div className="flex flex-col gap-2 px-3 pb-3 md:hidden">{shown.map(r => (
          <button key={r.ticket_id} onClick={() => setOpenRow(r.ticket_id)} className="flex flex-col gap-2 rounded-2xl bg-card2 px-4 py-4 text-left">
            <div className="flex items-center justify-between"><span className="flex items-center gap-2 font-semibold"><Icon d={I.truck} size={22} />#{r.ticket_id}</span><span className={`text-sm font-medium ${statusText(r.status)}`}>{r.status}</span></div>
            <div className="text-[15px]">{r.client} · {r.issue.split(',')[0]}</div>
            <div className="flex items-center justify-between text-sm text-sub"><span>{r.origin || '—'} → {r.dest || 'Unknown'}</span><span>{r.replacement || 'No replacement'}</span></div>
          </button>))}</div>
      </>}
    </Card>
  )
  return (
    <>
      <div className="hidden gap-4 md:grid md:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">{left}<div className="flex min-w-0 flex-col gap-4">{map}{table}</div></div>
      <div className="flex flex-col gap-4 md:hidden">{mobileView === 'map' ? map : <>{filter === 'All' && left}{table}</>}</div>
      {current && (current.held ? <Drawer title={current.ticket_id} sub={current.client} onClose={() => setOpenRow(null)}><div className="text-sub">A new file format was detected. Review and approve the field mapping in Audit.</div><Btn onClick={() => { setOpenRow(null); setFilter('audit') }} className="self-start">Open audit</Btn></Drawer> : current.status === 'Set aside'
        ? <Drawer title={`Ticket ${current.ticket_id} set aside`} sub={current.quarantine.detail} onClose={() => setOpenRow(null)}><Quarantined q={current.quarantine} onHistory={onHistory} onChange={done} bare /></Drawer>
        : current.approval
          ? <Drawer wide title={current.client} sub={`${current.issue} · ${current.truck}`} onClose={() => setOpenRow(null)}><Detail it={current.approval} onDone={done} onHistory={onHistory} bare /></Drawer>
          : <Drawer title={current.client} sub={current.summary} onClose={() => setOpenRow(null)}><div className="text-sub">{current.replacement_line}</div><button onClick={() => onHistory(current.ticket_id)} className="self-start text-gold">History</button></Drawer>)}
    </>
  )
}
