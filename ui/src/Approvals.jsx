import { useState } from 'react'
import { post, when } from './api'
import { Btn, ErrorState, Icon, I, RuleChip, Section } from './ui'

const reviewerKey = 'meridian-reviewer'
const savedReviewer = () => { try { return localStorage.getItem(reviewerKey) || '' } catch { return '' } }

// Approval detail, rendered inside the ticket slide-over. Approve is exactly-once server side (409 on conflict).
export function Detail({ it, onDone, onHistory }) {
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(it.body)
  const [reviewer, setReviewer] = useState(savedReviewer)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const approve = async () => {
    const by = reviewer.trim()
    if (!by || busy) return
    setBusy(true); setError(null)
    try {
      await post('approve', { ticket_id: it.ticket_id, by, body: editing && body !== it.body ? body : null })
      try { localStorage.setItem(reviewerKey, by) } catch { /* local storage may be unavailable */ }
      await onDone()
    } catch (reason) { setError(reason) } finally { setBusy(false) }
  }
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-sub">
        <span className="break-words">To: {it.recipient} · Drafted by {it.drafted_by} · {when(it.at)}</span>
        <button onClick={() => onHistory(it.ticket_id)} className="min-h-11 font-medium text-gold">History</button>
      </div>
      <div className="flex flex-col gap-2"><Section>Message to client</Section>
        {editing ? <textarea value={body} onChange={e => setBody(e.target.value)} rows={9} className="rounded-2xl bg-card2 p-5 text-base leading-relaxed text-ink outline-none ring-1 ring-gold" />
          : <div className="whitespace-pre-line rounded-2xl bg-card2 px-5 py-5 leading-relaxed">{body}</div>}
      </div>
      <div className="flex flex-col gap-3 rounded-2xl bg-card2 px-5 py-5">
        <div className="font-semibold">Why this decision</div>
        <p className="m-0 leading-relaxed text-ink/90">{it.why}</p>
        {it.flags.length > 0 && <ul className="m-0 list-disc pl-5 text-sub">{it.flags.map(f => <li key={f}>{f}</li>)}</ul>}
        <div className="flex flex-wrap gap-2">{it.rules.map(r => <RuleChip key={r.id} r={r} />)}</div>
        <div className="text-sm text-sub">Based on: {it.based_on.join(' · ')}</div>
      </div>
      {it.status === 'pending' ? (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-sub">Reviewer identity</span>
            <input value={reviewer} onChange={e => setReviewer(e.target.value)} onBlur={() => { try { localStorage.setItem(reviewerKey, reviewer.trim()) } catch { /* local storage may be unavailable */ } }} required autoComplete="name" placeholder="Enter your name or shift identity" className="h-12 rounded-full bg-card2 px-4 text-base text-ink outline-none focus:ring-1 focus:ring-gold" />
            <span className="text-sm text-mute">Required for the approval record.</span>
          </label>
          {error && <ErrorState error={error} onRetry={approve} title="Approval was not sent." />}
          <div className="mt-auto flex flex-col gap-3 md:flex-row">
            <Btn kind="green" onClick={approve} disabled={busy || !reviewer.trim()} className="h-14 grow text-lg"><Icon d={I.send} size={20} />{busy ? 'Sending' : 'Approve & send'}</Btn>
            <Btn kind="outline" onClick={() => setEditing(e => !e)} disabled={busy} className="h-14 text-lg font-medium"><Icon d={I.edit} size={20} />{editing ? 'Done editing' : 'Edit draft'}</Btn>
          </div>
          <div className="text-center text-sm text-mute">Sending is final. The client receives this message immediately.</div>
        </>
      ) : <div className="flex items-center gap-2 text-grn"><Icon d={I.check} sw={2} /><span className="font-medium">Sent by {it.approved_by} at {when(it.sent_at)}</span></div>}
    </div>
  )
}
