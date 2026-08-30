import { useEffect, useState } from 'react'
import { get, post, when } from './api'
import { Btn, Card, Chip, Empty, Icon, I, RuleChip, Section } from './ui'

const APPROVER = 'Dispatcher on duty'   // ponytail: single-user console, no login. Swap for a real identity when there is one.

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
  const [busy, setBusy] = useState(false)
  useEffect(() => { setBody(it.body); setEditing(false) }, [it])
  const approve = async () => { setBusy(true); await post('approve', { ticket_id: it.ticket_id, by: APPROVER, body: editing && body !== it.body ? body : null }); setBusy(false); onDone() }
  return (
    <Card className="flex flex-col gap-6 p-5 md:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {onBack && <button onClick={onBack} className="flex h-11 w-11 items-center justify-center rounded-[10px] bg-bg"><Icon d={I.back} size={20} /></button>}
          <div className="flex flex-col gap-1"><h2 className="text-[22px] font-semibold">{it.client}</h2>
            <div className="text-sm text-sub">To: {it.recipient} · Drafted by {it.drafted_by} · Truck {it.vehicle} · {when(it.at)}</div></div>
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
          <div className="mt-auto flex flex-col gap-3 border-t border-line pt-4 md:flex-row">
            <Btn kind="green" onClick={approve} disabled={busy} className="h-14 grow text-lg"><Icon d={I.send} size={20} />{busy ? 'Sending' : 'Approve & send'}</Btn>
            <Btn kind="outline" onClick={() => setEditing(e => !e)} className="h-14 text-lg font-medium"><Icon d={I.edit} size={20} />{editing ? 'Done editing' : 'Edit draft'}</Btn>
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
  const load = () => get('approvals').then(x => { setD(x); setSel(s => s ?? x.pending[0]?.ticket_id ?? null) })
  useEffect(() => { load() }, [tick])
  const all = [...d.pending, ...d.sent]
  const cur = all.find(i => i.ticket_id === sel)
  const done = () => { load(); onChange(); setMobileOpen(false) }
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
      <div className="hidden gap-6 md:flex"><div className="w-[380px] shrink-0 self-start">{list}</div><div className="grow">{cur && <Detail it={cur} onDone={done} onHistory={onHistory} />}</div></div>
      <div className="md:hidden">{mobileOpen && cur ? <Detail it={cur} onDone={done} onHistory={onHistory} onBack={() => setMobileOpen(false)} /> : list}</div>
    </>
  )
}
