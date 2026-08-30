import { useCallback, useEffect, useRef, useState } from 'react'
import { get, when } from './api'
import { Drawer, ErrorState, Icon, I, Loading, RuleChip } from './ui'
import Graph from './Graph'

export default function History({ ticketId, onClose }) {
  const [h, setH] = useState(null)
  const [graph, setGraph] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    setError(null)
    try {
      const next = await get('history/' + encodeURIComponent(ticketId))
      if (request === latest.current) setH(next)
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
  const rr = h?.rerun
  return (
    <Drawer title={graph ? 'What the system knew' : 'History'} sub={`${ticketId} · every step the system took`} onClose={onClose}>
        <button onClick={() => setGraph(g => !g)} className="flex h-11 items-center justify-center gap-2 rounded-full bg-card2 text-[15px] font-semibold text-gold hover:bg-card3"><Icon d={I.graph} />{graph ? 'View as timeline' : 'View as graph'}</button>
        {graph ? <Graph ticketId={ticketId} /> : loading ? <Loading label="Loading history" /> : error ? <ErrorState error={error} onRetry={load} title="Could not load history." /> : !h || h.steps.length === 0 ? <div className="text-sub">No audit trail for this ticket yet.</div> : (
          <div className="flex flex-col">
            {h.steps.map((s, i) => {
              const last = i === h.steps.length - 1
              const human = s.by === 'human', warn = /fallback|Quarantined|repeated/.test(s.step)
              return (
                <div key={i} className="flex gap-4">
                  <div className="flex w-6 shrink-0 flex-col items-center">
                    <div className={`flex h-6 w-6 items-center justify-center rounded-full ${warn ? 'bg-amb-soft text-amb' : human ? 'bg-gold text-frame' : 'bg-grn-soft text-grn'}`}><Icon d={I.check} size={14} sw={2} /></div>
                    {!last && <div className="my-1 w-px grow bg-white/10" />}
                  </div>
                  <div className={`flex flex-col gap-1 ${last ? '' : 'pb-6'}`}>
                    <div className="flex flex-wrap items-baseline gap-2.5"><span className="font-semibold">{s.step}</span><span className="text-[13px] text-mute">{when(s.at)} · by {s.by}</span></div>
                    <div className="text-[15px] leading-relaxed text-ink/90">{s.decision}</div>
                    {s.step === 'Truck selected' && s.data.skipped?.length > 0 && <ul className="m-0 list-disc pl-5 text-sm text-sub">{s.data.skipped.map((k, j) => <li key={j}>Skipped {k.vehicle} at {k.hub}: {k.rule}, {k.why}</li>)}</ul>}
                    {s.rules.length > 0 && <div className="flex flex-wrap gap-1.5 pt-1">{s.rules.map(r => <RuleChip key={r.id} r={r} />)}</div>}
                    {s.sources.length > 0 && <div className="text-[13px] text-mute">Source: {s.sources.join(' · ')}</div>}
                  </div>
                </div>)
            })}
          </div>)}
        {rr && <div className="mt-auto rounded-2xl bg-card2 px-4 py-3.5 text-sm text-sub">Re-run check at {when(rr.at)}: {rr.identical ? 'the pipeline produced the identical result.' : `${rr.differences.length} files differed.`}</div>}
    </Drawer>
  )
}
