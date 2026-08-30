import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import { get, when } from './api'
import { Card, Chip, Empty, ErrorState, Icon, I, Loading, sevColor, statusTone } from './ui'

const pinIcon = (sel) => L.divIcon({ className: '', iconSize: [24, 30], iconAnchor: [12, 30], html:
  `<svg width="24" height="30" viewBox="0 0 24 30" class="${sel ? 'pin-sel' : ''}"><path d="M12 30 L3 16 a11 11 0 1 1 18 0 z" fill="#dc2626"/><circle cx="12" cy="13" r="4" fill="#fff"/></svg>` })
const hubIcon = L.divIcon({ className: '', iconSize: [18, 18], iconAnchor: [9, 9], html: '<div style="width:18px;height:18px;border-radius:50%;background:#fff;border:3px solid #4f46e5"></div>' })

function Focus({ item }) {
  const map = useMap()
  useEffect(() => { if (item) map.flyTo([item.point.lat, item.point.lon], 9, { duration: 0.6 }) }, [item, map])
  return null
}

export function FleetMap({ items, hubs, selected, onSelect, className = '' }) {
  return (
    <MapContainer center={[28.4, 77.8]} zoom={6} className={`z-0 rounded-xl border border-line ${className}`} scrollWheelZoom={false}>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
      {Object.entries(hubs || {}).map(([n, h]) => <Marker key={n} position={[h.lat, h.lon]} icon={hubIcon} alt={`${n} hub`} title={`${n} hub`}><Tooltip direction="right" offset={[10, 0]} permanent className="!border-0 !bg-transparent !shadow-none !font-semibold">{n}</Tooltip></Marker>)}
      {items.filter(b => b.status !== 'Resolved').map(b => (
        <span key={b.ticket_id}>
          {b.hub && <Polyline positions={[[b.hub.lat, b.hub.lon], [b.point.lat, b.point.lon]]} pathOptions={{ color: '#4f46e5', weight: 2, dashArray: '6 6' }} />}
          <Marker position={[b.point.lat, b.point.lon]} icon={pinIcon(selected === b.ticket_id)} alt={`${b.severity} severity breakdown: ${b.summary}`} title={b.summary} eventHandlers={{ click: () => onSelect?.(b.ticket_id) }}><Tooltip>{b.summary}</Tooltip></Marker>
        </span>
      ))}
      <Focus item={items.find(b => b.ticket_id === selected)} />
    </MapContainer>
  )
}

export function BreakdownCard({ b, selected, onSelect, onHistory }) {
  const select = () => onSelect?.(b.ticket_id)
  return (
    <Card role="button" tabIndex="0" aria-pressed={selected} aria-label={`${b.severity} severity breakdown. ${b.summary}`} onClick={select} onKeyDown={e => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select() } }} className={`flex min-w-0 cursor-pointer gap-3 ${selected ? 'border-ind ring-[3px] ring-ind-soft' : ''}`}>
      <span aria-hidden="true" className={`mt-2 h-2.5 w-2.5 shrink-0 rounded-full ${sevColor(b.severity)}`} />
      <div className="flex min-w-0 grow flex-col gap-1.5">
        <div className="font-medium leading-snug">{b.summary}</div>
        <div className="text-sm text-sub"><span className="font-medium">{b.severity} severity</span> · {b.replacement_line}</div>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <Chip t={statusTone(b.status)}>{b.status}</Chip>
          <div className="flex items-center gap-3 text-sm text-mute"><span className="flex items-center gap-1"><Icon d={I.clock} size={14} />{when(b.at)}</span>
            <button onClick={e => { e.stopPropagation(); onHistory(b.ticket_id) }} className="-my-3 min-h-11 px-2 text-ind hover:text-ind-dark">History</button></div>
        </div>
      </div>
    </Card>
  )
}

export default function Operations({ tick, onHistory, mobileView }) {
  const [data, setData] = useState({ items: [], hubs: {} })
  const [sel, setSel] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    setError(null)
    try {
      const next = await get('breakdowns')
      if (request === latest.current) setData(next)
    } catch (reason) {
      if (request === latest.current) setError(reason)
    } finally {
      if (request === latest.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    const frame = requestAnimationFrame(() => { void load() })
    return () => { cancelAnimationFrame(frame); latest.current += 1 }
  }, [load, tick])
  const open = useMemo(() => data.items.filter(b => b.status !== 'Resolved').length, [data])
  if (loading) return <Loading label="Loading breakdowns" />
  if (error) return <ErrorState error={error} onRetry={load} title="Could not load breakdowns." />
  const feed = (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between"><h2 className="text-lg font-semibold">Breakdowns</h2><span className="text-sm text-mute">Newest first</span></div>
      {data.items.length === 0 ? <Empty title="No breakdowns right now." sub="All trucks moving. Run the pipeline to process a queue." /> :
        data.items.map(b => <BreakdownCard key={b.ticket_id} b={b} selected={sel === b.ticket_id} onSelect={setSel} onHistory={onHistory} />)}
    </div>
  )
  const map = (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between"><h2 className="text-lg font-semibold">Fleet map</h2><span className="text-sm text-mute">{open} open breakdown{open === 1 ? '' : 's'}</span></div>
      <FleetMap items={data.items} hubs={data.hubs} selected={sel} onSelect={setSel} className="h-[60vh] md:h-[calc(100vh-220px)]" />
      {sel && <div className="md:hidden">{data.items.filter(b => b.ticket_id === sel).map(b => <BreakdownCard key={b.ticket_id} b={b} selected onSelect={setSel} onHistory={onHistory} />)}</div>}
    </div>
  )
  return (
    <>
      <div className="hidden gap-6 md:flex"><div className="w-[60%] shrink-0">{map}</div><div className="min-w-0 grow">{feed}</div></div>
      <div className="md:hidden">{mobileView === 'map' ? map : feed}</div>
    </>
  )
}
