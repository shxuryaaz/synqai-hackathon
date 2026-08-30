import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { get, when } from './api'
import { ErrorState, Icon, I, Loading, RuleChip } from './ui'
import Graph from './Graph'

export default function History({ ticketId, onClose }) {
  const [h, setH] = useState(null)
  const [graph, setGraph] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const dialog = useRef(null)
  const close = useRef(null)
  const latest = useRef(0)
  const title = useId()
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
  useEffect(() => {
    const previous = document.activeElement
    const onKeyDown = event => {
      if (event.key === 'Escape') return onClose()
      if (event.key !== 'Tab') return
      const focusable = [...(dialog.current?.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])]
      if (focusable.length === 0) return
      const first = focusable[0], last = focusable.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKeyDown)
    close.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus?.()
    }
  }, [onClose])
  const rr = h?.rerun
  return (
    <>
      <div aria-hidden="true" className="fixed inset-0 z-40 bg-ink/25" onClick={onClose} />
      <aside ref={dialog} role="dialog" aria-modal="true" aria-labelledby={title} className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[520px] flex-col gap-6 overflow-y-auto border-l border-line bg-white px-5 py-7 shadow-[-12px_0_32px_rgba(16,24,40,.12)] sm:px-6 md:px-8">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex flex-col gap-1"><h2 id={title} className="text-xl font-semibold">{graph ? 'What the system knew' : 'History'}</h2><div className="break-words text-sm text-sub">{ticketId} · every step the system took</div></div>
          <button ref={close} onClick={onClose} aria-label="Close history" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] bg-bg text-sub"><Icon d={I.x} size={20} /></button>
        </div>
        <button onClick={() => setGraph(g => !g)} className="flex h-11 items-center justify-center gap-2 rounded-[10px] bg-ind-soft text-base font-semibold text-ind"><Icon d={I.graph} />{graph ? 'View as timeline' : 'View as graph'}</button>
        {graph ? <Graph ticketId={ticketId} /> : loading ? <Loading label="Loading history" /> : error ? <ErrorState error={error} onRetry={load} title="Could not load history." /> : !h || h.steps.length === 0 ? <div className="text-sub">No audit trail for this ticket yet.</div> : (
          <div className="flex flex-col">
            {h.steps.map((s, i) => {
              const last = i === h.steps.length - 1
              const human = s.by === 'human', warn = /fallback|Quarantined|repeated/.test(s.step)
              return (
                <div key={i} className="flex gap-4">
                  <div className="flex w-6 shrink-0 flex-col items-center">
                    <div className={`flex h-6 w-6 items-center justify-center rounded-full ${warn ? 'bg-amb-soft text-amb' : human ? 'bg-ind-soft text-ind' : 'bg-grn-soft text-grn'}`}><Icon d={I.check} size={14} sw={2.5} /></div>
                    {!last && <div className="my-1 w-0.5 grow bg-line" />}
                  </div>
                  <div className={`flex flex-col gap-1 ${last ? '' : 'pb-6'}`}>
                    <div className="flex flex-wrap items-baseline gap-2.5"><span className="font-semibold">{s.step}</span><span className="text-[13px] text-mute">{when(s.at)} · by {s.by}</span></div>
                    <div className="text-[15px] leading-relaxed">{s.decision}</div>
                    {s.step === 'Truck selected' && s.data.skipped?.length > 0 && <ul className="m-0 list-disc pl-5 text-sm text-sub">{s.data.skipped.map((k, j) => <li key={j}>Skipped {k.vehicle} at {k.hub}: {k.rule}, {k.why}</li>)}</ul>}
                    {s.rules.length > 0 && <div className="flex flex-wrap gap-1.5 pt-1">{s.rules.map(r => <RuleChip key={r.id} r={r} />)}</div>}
                    {s.sources.length > 0 && <div className="text-[13px] text-mute">Source: {s.sources.join(' · ')}</div>}
                  </div>
                </div>)
            })}
          </div>)}
        {rr && <div className="mt-auto rounded-[10px] bg-bg px-4 py-3.5 text-sm text-sub">Re-run check at {when(rr.at)}: {rr.identical ? 'the pipeline produced the identical result.' : `${rr.differences.length} files differed.`}</div>}
      </aside>
    </>
  )
}
