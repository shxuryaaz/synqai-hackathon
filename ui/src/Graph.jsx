import { useEffect, useState } from 'react'
import { get } from './api'

// ponytail: radial SVG layout, no physics lib. A ticket graph is ~12 nodes; upgrade to react-force-graph if it grows past ~60.
const COLOR = { ticket: '#4f46e5', vehicle: '#1a1d26', driver: '#5c6270', client: '#0f766e', hub: '#7c3aed', maintenance: '#b45309', rule: '#4f46e5', skipped: '#8a909c' }

export function GraphView({ data, center, w = 460, h = 460 }) {
  if (!data?.nodes?.length) return <div className="text-sub">Nothing to draw yet.</div>
  const c = center ?? data.nodes[0].id
  const ring = data.nodes.filter(n => n.id !== c)
  const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 56
  const pos = { [c]: [cx, cy] }
  ring.forEach((n, i) => { const a = -Math.PI / 2 + (2 * Math.PI * i) / ring.length; pos[n.id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)] })
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full rounded-xl border border-line bg-white" style={{ fontFamily: 'inherit' }}>
      {data.edges.filter(e => pos[e.from] && pos[e.to]).map((e, i) => {
        const [x1, y1] = pos[e.from], [x2, y2] = pos[e.to]; const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
        return <g key={i}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#cdd1d9" strokeWidth="1.5" />
          <text x={mx} y={my - 4} fontSize="9" fill="#8a909c" textAnchor="middle" paintOrder="stroke" stroke="#fff" strokeWidth="3">{e.label}</text></g>
      })}
      {data.nodes.filter(n => pos[n.id]).map(n => {
        const [x, y] = pos[n.id]; const lines = n.label.split('\n'); const isC = n.id === c
        return <g key={n.id}>
          <circle cx={x} cy={y} r={isC ? 22 : 14} fill={n.kind === 'rule' ? '#eef2ff' : n.kind === 'skipped' ? '#f1f2f5' : '#fff'} stroke={COLOR[n.kind] || '#8a909c'} strokeWidth={isC ? 3 : 2} strokeDasharray={n.kind === 'skipped' ? '3 3' : ''} />
          {lines.map((l, j) => <text key={j} x={x} y={y + (isC ? 34 : 26) + j * 11} fontSize="10" fontWeight={j === 0 ? 600 : 400} fill={j === 0 ? '#1a1d26' : '#5c6270'} textAnchor="middle" paintOrder="stroke" stroke="#fff" strokeWidth="3">{l}</text>)}
        </g>
      })}
    </svg>
  )
}

export default function Graph({ ticketId }) {
  const [d, setD] = useState(null)
  useEffect(() => { get('graph/' + ticketId).then(setD) }, [ticketId])
  return (
    <div className="flex flex-col gap-3">
      <GraphView data={d} center={ticketId} />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-sub">{Object.entries(COLOR).filter(([k]) => k !== 'ticket').map(([k, v]) => <span key={k} className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full border-2" style={{ borderColor: v }} />{k}</span>)}</div>
    </div>
  )
}
