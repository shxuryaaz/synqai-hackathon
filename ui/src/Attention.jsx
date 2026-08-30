import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { get, post } from './api'
import { Btn, Empty, ErrorState, Icon, I, Loading } from './ui'

const LABEL = { vehicle: 'Vehicle number', origin_hub: 'Origin hub', created_at: 'Reported at (date and time)', ticket_id: 'Ticket id', km_from_origin_hub: 'Km from origin hub' }
const safeSource = (source = '') => source.split(/[\\/]/).pop() || 'Unknown source'

export function Quarantined({ q, onHistory, onChange, bare }) {
  const [vals, setVals] = useState({})
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    setMsg('')
    try {
      const r = await post('resubmit', { ticket_id: q.ticket_id, fields: vals })
      setMsg(r.result === 'processed' ? 'Processed. Work order created.' : `Still set aside: ${r.quarantine.map(x => x.detail).join('; ')}`)
      await onChange()
    } catch (reason) {
      setError(reason)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className={`flex min-w-0 flex-col gap-3.5 ${bare ? '' : 'rounded-3xl bg-card px-5 py-5'}`}>
      <div className="flex items-start justify-between gap-3">
        {bare ? <div className="text-sm text-sub">Nothing was dispatched. Fill the gap and resubmit.</div> : <div className="flex gap-3"><span className="mt-0.5 text-red"><Icon d={I.alert} size={20} /></span><div className="text-[17px] font-semibold">Ticket {q.ticket_id} set aside, {q.detail}</div></div>}
        <button onClick={() => onHistory(q.ticket_id)} className="min-h-11 shrink-0 text-sm font-medium text-gold">History</button>
      </div>
      <div className="break-words rounded-2xl bg-card2 px-4 py-3 font-mono text-[13px] text-sub">reason: {q.reason} · {q.detail} · from {safeSource(q.source_file)} · record: {Object.entries(q.record).filter(([k, v]) => v && !k.startsWith('_')).map(([k, v]) => `${k}=${v}`).slice(0, 5).join(' · ')}</div>
      <div className="flex flex-wrap items-end gap-3">
        {q.missing.map(f => <label key={f} className="flex w-full min-w-0 grow flex-col gap-1.5 sm:w-auto sm:min-w-[260px]"><span className="text-sm font-medium text-sub">{LABEL[f] || f}</span>
          <input value={vals[f] || ''} onChange={e => setVals({ ...vals, [f]: e.target.value })} disabled={busy} placeholder="Type it here" className="h-12 min-w-0 rounded-full bg-card2 px-4 text-base text-ink outline-none focus:ring-1 focus:ring-gold" /></label>)}
        <Btn onClick={submit} disabled={busy || !q.missing.every(f => vals[f])} className="h-12">{busy ? 'Resubmitting' : 'Resubmit'}</Btn>
      </div>
      {error && <ErrorState error={error} onRetry={submit} title="This record was not resubmitted." />}
      {msg && <div role="status" className="text-sm font-medium text-sub">{msg}</div>}
    </div>
  )
}

function ReviewAlert({ alert, related, onHistory }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div className="flex min-w-0 flex-col gap-3.5 rounded-3xl bg-card px-5 py-5">
      <div className="flex min-w-0 flex-col gap-3.5 md:flex-row md:items-center">
        <span aria-hidden="true" className="text-amb"><Icon d={I.alert} size={20} /></span>
        <div className="flex min-w-0 grow flex-col gap-1"><div className="break-words text-[17px] font-semibold">{alert.message}</div><div className="break-words text-[15px] text-sub">File: {safeSource(alert.source_file)} · {alert.records} records</div></div>
        <Btn kind="amber" onClick={() => setOpen(value => !value)} aria-expanded={open} aria-controls={id} className="h-12 shrink-0">{open ? 'Close review' : 'Review file'}</Btn>
      </div>
      {open && <div id={id} role="region" aria-label={`Review of ${safeSource(alert.source_file)}`} className="rounded-2xl bg-card2 px-4 py-4">
        <div className="font-semibold">Held safely from {safeSource(alert.source_file)}</div>
        <div className="mt-1 text-sm text-sub">{alert.records} records were not dispatched. Review the record context below, then complete any ticket-level corrections in Set aside.</div>
        {related.length > 0 ? <ul className="mb-0 mt-3 flex list-none flex-col gap-2 p-0">
          {related.map(q => <li key={q.ticket_id + q.reason} className="flex flex-col gap-2 rounded-xl bg-card3 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 break-words text-sm"><span className="font-semibold">{q.ticket_id}</span>: {Object.entries(q.record).filter(([key, value]) => value && !key.startsWith('_')).slice(0, 3).map(([key, value]) => `${key}=${value}`).join(' · ') || q.detail}</div>
            <button onClick={() => onHistory(q.ticket_id)} className="min-h-11 shrink-0 self-start px-2 text-sm text-gold sm:self-auto">View history</button>
          </li>)}
        </ul> : <div className="mt-3 text-sm text-sub">No ticket-level record was created for this file.</div>}
      </div>}
    </div>
  )
}

function FormatCard({ m, onChange }) {
  const [by, setBy] = useState(() => { try { return localStorage.getItem('meridian-reviewer') || '' } catch { return '' } })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const decide = async (approve) => {
    if (busy || !by.trim()) return
    setBusy(true); setError(null)
    try { await post('format-map', { key: m.key, by: by.trim(), approve }); await onChange() } catch (reason) { setError(reason) } finally { setBusy(false) }
  }
  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-3xl bg-card px-5 py-5">
      <div className="flex gap-3"><span className="mt-0.5 text-gold"><Icon d={I.box} size={20} /></span><div><div className="text-[17px] font-semibold">New format detected in {safeSource(m.source_file)}</div><div className="text-[15px] text-sub">{m.records} records held. Proposed mapping to the ticket schema. Approve to process them.</div></div></div>
      <div className="overflow-x-auto"><table className="w-full text-[15px]"><thead><tr className="text-left text-[12px] uppercase tracking-wider text-mute"><th className="py-1 pr-3">File column</th><th className="pr-3">Maps to</th><th>Confidence</th></tr></thead>
        <tbody>{m.columns.map(c => { const x = m.mapping[c] || {}; const ok = x.target && x.confidence >= 0.7; return <tr key={c} className="border-t border-white/10"><td className="py-1.5 pr-3 font-mono text-[13px]">{c}</td><td className={`pr-3 ${ok ? '' : 'text-sub'}`}>{ok ? x.target : x.target ? `${x.target} (too low, dropped)` : 'not mapped'}</td><td className={ok ? 'text-grn' : 'text-amb'}>{Math.round((x.confidence || 0) * 100)}%</td></tr> })}</tbody></table></div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-[240px] grow flex-col gap-1.5"><span className="text-sm font-medium text-sub">Reviewer identity</span><input value={by} onChange={e => setBy(e.target.value)} placeholder="Your name or shift identity" className="h-12 rounded-full bg-card2 px-4 text-base text-ink outline-none focus:ring-1 focus:ring-gold" /></label>
        <Btn kind="green" onClick={() => decide(true)} disabled={busy || !by.trim()} className="h-12">{busy ? 'Working' : 'Approve mapping & process'}</Btn>
        <Btn kind="outline" onClick={() => decide(false)} disabled={busy || !by.trim()} className="h-12">Reject</Btn>
      </div>
      {error && <ErrorState error={error} onRetry={() => decide(true)} title="The mapping decision did not go through." />}
    </div>
  )
}

export default function Attention({ tick, onHistory, onChange }) {
  const [d, setD] = useState({ quarantined: [], alerts: [], format_maps: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    setError(null)
    try {
      const next = await get('attention')
      if (request === latest.current) setD(next)
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
  if (loading) return <Loading label="Loading attention items" />
  if (error) return <ErrorState error={error} onRetry={load} title="Could not load attention items." />
  const held = d.quarantined.filter(q => q.reason !== 'unrecognized_format')
  if (held.length + d.alerts.length + (d.format_maps?.length || 0) === 0) return <Empty title="Nothing needs attention." sub="Every ticket was understood and every file was recognised." />
  return (
    <div className="flex max-w-[960px] flex-col gap-7">
      {d.format_maps?.length > 0 && <div className="flex flex-col gap-3"><h2 className="text-[21px] font-semibold tracking-tight">New formats · {d.format_maps.length}</h2>{d.format_maps.map(m => <FormatCard key={m.key} m={m} onChange={onChange} />)}</div>}
      {held.length > 0 && <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between"><h2 className="text-[21px] font-semibold tracking-tight">Set aside · {held.length}</h2><span className="text-sm text-mute">Nothing was dispatched for these. Fill the gap and resubmit.</span></div>
        {held.map(q => <Quarantined key={q.ticket_id + q.reason} q={q} onHistory={onHistory} onChange={onChange} />)}
      </div>}
      {d.alerts.length > 0 && <div className="flex flex-col gap-3"><h2 className="text-[21px] font-semibold tracking-tight">System warnings · {d.alerts.length}</h2>
        {d.alerts.map(a => <ReviewAlert key={a.key} alert={a} related={d.quarantined.filter(q => q.source_file === a.source_file)} onHistory={onHistory} />)}
      </div>}
    </div>
  )
}
