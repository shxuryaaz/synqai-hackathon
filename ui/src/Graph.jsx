import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from './api'
import { ErrorState, Loading } from './ui'

// ponytail: radial SVG layout, no physics lib. A ticket graph is ~12 nodes; upgrade to react-force-graph if it grows past ~60.
const COLOR = { ticket: '#d8cba3', vehicle: '#f3efe6', driver: '#a9a59c', client: '#5fc78a', hub: '#e2a93f', maintenance: '#e0604f', rule: '#d8cba3', skipped: '#78756e' }

export function GraphView({ data, center, w = 460, h = 460 }) {
  if (!data?.nodes?.length) return <div className="text-sub">Nothing to draw yet.</div>
  const c = center ?? data.nodes[0].id
  const ring = data.nodes.filter(n => n.id !== c)
  const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 56
  const pos = { [c]: [cx, cy] }
  ring.forEach((n, i) => { const a = -Math.PI / 2 + (2 * Math.PI * i) / ring.length; pos[n.id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)] })
  return (
    <svg role="img" aria-label="Decision relationship graph" viewBox={`0 0 ${w} ${h}`} className="w-full rounded-2xl bg-card2" style={{ fontFamily: 'inherit' }}>
      {data.edges.filter(e => pos[e.from] && pos[e.to]).map((e, i) => {
        const [x1, y1] = pos[e.from], [x2, y2] = pos[e.to]; const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
        return <g key={i}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#454549" strokeWidth="1.5" />
          <text x={mx} y={my - 4} fontSize="9" fill="#a9a59c" textAnchor="middle" paintOrder="stroke" stroke="#2b2b2e" strokeWidth="3">{e.label}</text></g>
      })}
      {data.nodes.filter(n => pos[n.id]).map(n => {
        const [x, y] = pos[n.id]; const lines = n.label.split('\n'); const isC = n.id === c
        return <g key={n.id} role="img" aria-label={`${n.kind}: ${lines.join(' ')}`}>
          <circle cx={x} cy={y} r={isC ? 22 : 14} fill={n.kind === 'rule' ? '#353538' : n.kind === 'skipped' ? '#2b2b2e' : '#161617'} stroke={COLOR[n.kind] || '#8a909c'} strokeWidth={isC ? 3 : 2} strokeDasharray={n.kind === 'skipped' ? '3 3' : ''} />
          {lines.map((l, j) => <text key={j} x={x} y={y + (isC ? 34 : 26) + j * 11} fontSize="10" fontWeight={j === 0 ? 600 : 400} fill={j === 0 ? '#f3efe6' : '#a9a59c'} textAnchor="middle" paintOrder="stroke" stroke="#2b2b2e" strokeWidth="3">{l}</text>)}
        </g>
      })}
    </svg>
  )
}

export default function Graph({ ticketId }) {
  const [d, setD] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    setError(null)
    try {
      const next = await get('graph/' + encodeURIComponent(ticketId))
      if (request === latest.current) setD(next)
    } catch (reason) {
      if (request === latest.current) setError(reason)
    } finally {
      if (request === latest.current) setLoading(false)
    }
  }, [ticketId])
  useEffect(() => {
    const frame = requestAnimationFrame(() => { void load() })
    return () => { cancelAnimationFrame(frame); latest.current += 1 }
  }, [load])
  if (loading) return <Loading label="Loading graph" />
  if (error) return <ErrorState error={error} onRetry={load} title="Could not load the graph." />
  return (
    <div className="flex flex-col gap-3">
      <GraphView data={d} center={ticketId} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-sub">{Object.entries(COLOR).filter(([k]) => k !== 'ticket').map(([k, v]) => <span key={k} className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-3 w-3 rounded-full border-2" style={{ borderColor: v }} />{k}</span>)}</div>
    </div>
  )
}
