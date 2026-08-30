import { useEffect, useState } from 'react'
import { get, post } from './api'
import { Btn, Empty, Icon, I } from './ui'

const LABEL = { vehicle: 'Vehicle number', origin_hub: 'Origin hub', created_at: 'Reported at (date and time)', ticket_id: 'Ticket id', km_from_origin_hub: 'Km from origin hub' }

function Quarantined({ q, onHistory, onChange }) {
  const [vals, setVals] = useState({})
  const [msg, setMsg] = useState('')
  const submit = async () => {
    const r = await post('resubmit', { ticket_id: q.ticket_id, fields: vals })
    setMsg(r.result === 'processed' ? 'Processed. Work order created.' : `Still set aside: ${r.quarantine.map(x => x.detail).join('; ')}`)
    onChange()
  }
  return (
    <div className="flex flex-col gap-3.5 rounded-xl border border-red-200 bg-red-soft px-5 py-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex gap-3"><span className="mt-0.5 text-red"><Icon d={I.alert} size={20} /></span><div className="text-[17px] font-semibold">Ticket {q.ticket_id} set aside, {q.detail}</div></div>
        <button onClick={() => onHistory(q.ticket_id)} className="min-h-11 shrink-0 text-sm text-ind">History</button>
      </div>
      <div className="rounded-lg border border-red-200 bg-white px-3.5 py-2.5 font-mono text-sm text-sub">reason: {q.reason} · {q.detail} · from {q.source_file} · record: {Object.entries(q.record).filter(([k, v]) => v && !k.startsWith('_')).map(([k, v]) => `${k}=${v}`).slice(0, 5).join(' · ')}</div>
      <div className="flex flex-wrap items-end gap-3">
        {q.missing.map(f => <label key={f} className="flex min-w-[260px] grow flex-col gap-1.5"><span className="text-sm font-medium text-sub">{LABEL[f] || f}</span>
          <input value={vals[f] || ''} onChange={e => setVals({ ...vals, [f]: e.target.value })} placeholder="Type it here" className="h-12 rounded-[10px] border-[1.5px] border-[#cdd1d9] bg-white px-3.5 text-base outline-none focus:border-ind" /></label>)}
        <Btn onClick={submit} disabled={!q.missing.every(f => vals[f])} className="h-12">Resubmit</Btn>
      </div>
      {msg && <div className="text-sm font-medium text-sub">{msg}</div>}
    </div>
  )
}

export default function Attention({ tick, onHistory, onChange }) {
  const [d, setD] = useState({ quarantined: [], alerts: [] })
  useEffect(() => { get('attention').then(setD) }, [tick])
  if (d.quarantined.length + d.alerts.length === 0) return <Empty title="Nothing needs attention." sub="Every ticket was understood and every file was recognised." />
  return (
    <div className="flex max-w-[960px] flex-col gap-7">
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between"><h2 className="text-lg font-semibold">Set aside · {d.quarantined.length}</h2><span className="text-sm text-mute">Nothing was dispatched for these. Fill the gap and resubmit.</span></div>
        {d.quarantined.map(q => <Quarantined key={q.ticket_id + q.reason} q={q} onHistory={onHistory} onChange={onChange} />)}
      </div>
      {d.alerts.length > 0 && <div className="flex flex-col gap-3"><h2 className="text-lg font-semibold">System warnings · {d.alerts.length}</h2>
        {d.alerts.map(a => (
          <div key={a.key} className="flex flex-col gap-3.5 rounded-xl border border-amber-200 bg-amb-soft px-5 py-5 md:flex-row md:items-center">
            <span className="text-amb"><Icon d={I.alert} size={20} /></span>
            <div className="flex grow flex-col gap-1"><div className="text-[17px] font-semibold">{a.message}</div><div className="text-[15px] text-sub">File: {a.source_file} · {a.records} records</div></div>
            <Btn kind="amber" onClick={() => onHistory(null, a.source_file)} className="h-12 shrink-0">Review file</Btn>
          </div>))}
      </div>}
    </div>
  )
}
