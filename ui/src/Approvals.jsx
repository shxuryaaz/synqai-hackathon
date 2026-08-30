import { useCallback, useEffect, useRef, useState } from 'react'
import { get, post, when } from './api'
import { Btn, Card, Chip, Empty, ErrorState, Icon, I, Loading, RuleChip, Section } from './ui'

const reviewerKey = 'meridian-reviewer'
const savedReviewer = () => {
  try { return localStorage.getItem(reviewerKey) || '' } catch { return '' }
}

function Row({ it, sel, onClick }) {
  return (
    <button onClick={onClick} className={`flex w-full flex-col gap-1 rounded-[10px] border px-4 py-4 text-left ${sel ? 'border-indigo-200 bg-ind-soft' : 'border-transparent hover:bg-bg'}`}>
      <div className="flex items-center justify-between gap-2"><span className="font-semibold">{it.client}</span>
        {it.status === 'sent' ? <span className="flex items-center gap-1 text-[13px] font-medium text-grn"><Icon d={I.check} size={14} sw={2.5} />Sent</span> : <Chip t="amb">Waiting</Chip>}</div>
      <div className="text-sm leading-snug text-sub">{it.status === 'sent' ? `Approved by ${it.approved_by} · ${when(it.sent_at)}` : it.summary}</div>
    </button>
  )
}

export function Detail({ it, onDone, onHistory, onBack }) {
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(it.body)
  const [reviewer, setReviewer] = useState(savedReviewer)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const approve = async () => {
    const by = reviewer.trim()
    if (!by || busy) return
    setBusy(true)
    setError(null)
    try {
      await post('approve', { ticket_id: it.ticket_id, by, body: editing && body !== it.body ? body : null })
      try { localStorage.setItem(reviewerKey, by) } catch { /* local storage may be unavailable */ }
      await onDone()
    } catch (reason) {
      setError(reason)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="flex min-w-0 flex-col gap-6 p-5 md:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {onBack && <button onClick={onBack} aria-label="Back to approvals" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] bg-bg"><Icon d={I.back} size={20} /></button>}
          <div className="flex min-w-0 flex-col gap-1"><h2 className="break-words text-[22px] font-semibold">{it.client}</h2>
            <div className="break-words text-sm text-sub">To: {it.recipient} · Drafted by {it.drafted_by} · Truck {it.vehicle} · {when(it.at)}</div></div>
        </div>
        <button onClick={() => onHistory(it.ticket_id)} className="min-h-11 text-sm text-ind">History</button>
      </div>
      <div className="flex flex-col gap-2"><Section>Message to client</Section>
        {editing ? <textarea value={body} onChange={e => setBody(e.target.value)} rows={9} className="rounded-[10px] border-[1.5px] border-ind bg-white p-5 text-base leading-relaxed outline-none" />
          : <div className="whitespace-pre-line rounded-[10px] border-[1.5px] border-line bg-[#fafafb] px-5 py-5 leading-relaxed">{body}</div>}
      </div>
      <div className="flex flex-col gap-3 rounded-[10px] bg-bg px-5 py-5">
        <div className="font-semibold">Why this decision</div>
        <p className="m-0 leading-relaxed">{it.why}</p>
        {it.flags.length > 0 && <ul className="m-0 list-disc pl-5 text-sub">{it.flags.map(f => <li key={f}>{f}</li>)}</ul>}
        <div className="flex flex-wrap gap-2">{it.rules.map(r => <RuleChip key={r.id} r={r} />)}</div>
        <div className="text-sm text-sub">Based on: {it.based_on.join(' · ')}</div>
      </div>
      {it.status === 'pending' ? (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-sub">Reviewer identity</span>
            <input value={reviewer} onChange={e => setReviewer(e.target.value)} onBlur={() => { try { localStorage.setItem(reviewerKey, reviewer.trim()) } catch { /* local storage may be unavailable */ } }} required autoComplete="name" placeholder="Enter your name or shift identity" className="h-12 rounded-[10px] border-[1.5px] border-[#cdd1d9] bg-white px-3.5 text-base outline-none focus:border-ind" />
            <span className="text-sm text-mute">Required for the approval record.</span>
          </label>
          {error && <ErrorState error={error} onRetry={approve} title="Approval was not sent." />}
          <div className="mt-auto flex flex-col gap-3 border-t border-line pt-4 md:flex-row">
            <Btn kind="green" onClick={approve} disabled={busy || !reviewer.trim()} className="h-14 grow text-lg"><Icon d={I.send} size={20} />{busy ? 'Sending' : 'Approve & send'}</Btn>
            <Btn kind="outline" onClick={() => setEditing(e => !e)} disabled={busy} className="h-14 text-lg font-medium"><Icon d={I.edit} size={20} />{editing ? 'Done editing' : 'Edit draft'}</Btn>
          </div>
          <div className="text-center text-sm text-mute">Sending is final. The client receives this message immediately.</div>
        </>
      ) : <div className="flex items-center gap-2 border-t border-line pt-4 text-grn"><Icon d={I.check} sw={2.5} /><span className="font-medium">Sent by {it.approved_by} at {when(it.sent_at)}</span></div>}
    </Card>
  )
}

export default function Approvals({ tick, onHistory, onChange }) {
  const [d, setD] = useState({ pending: [], sent: [] })
  const [sel, setSel] = useState(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    setError(null)
    try {
      const next = await get('approvals')
      if (request === latest.current) {
        setD(next)
        setSel(s => s ?? next.pending[0]?.ticket_id ?? null)
      }
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
  const all = [...d.pending, ...d.sent]
  const cur = all.find(i => i.ticket_id === sel)
  const done = async () => { await load(); await onChange(); setMobileOpen(false) }
  if (loading) return <Loading label="Loading approvals" />
  if (error) return <ErrorState error={error} onRetry={load} title="Could not load approvals." />
  if (all.length === 0) return <Empty title="Nothing waiting for approval." sub="Every drafted message has been sent." />
  const list = (
    <Card className="flex flex-col gap-1 p-2">
      <div className="px-4 pt-2.5 pb-1.5"><Section>Pending · {d.pending.length}</Section></div>
      {d.pending.map(it => <Row key={it.ticket_id} it={it} sel={sel === it.ticket_id} onClick={() => { setSel(it.ticket_id); setMobileOpen(true) }} />)}
      {d.sent.length > 0 && <><div className="mx-2.5 my-2 h-px bg-line" /><div className="px-4 py-1.5"><Section>Sent · {d.sent.length}</Section></div>
        {d.sent.map(it => <Row key={it.ticket_id} it={it} sel={sel === it.ticket_id} onClick={() => { setSel(it.ticket_id); setMobileOpen(true) }} />)}</>}
    </Card>
  )
  return (
    <>
      <div className="hidden gap-6 lg:flex"><div className="w-[380px] shrink-0 self-start">{list}</div><div className="min-w-0 grow">{cur && <Detail key={cur.ticket_id} it={cur} onDone={done} onHistory={onHistory} />}</div></div>
      <div className="lg:hidden">{mobileOpen && cur ? <Detail key={cur.ticket_id} it={cur} onDone={done} onHistory={onHistory} onBack={() => setMobileOpen(false)} /> : list}</div>
    </>
  )
}
