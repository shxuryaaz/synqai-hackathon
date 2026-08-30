import { useCallback, useEffect, useRef, useState } from 'react'
import { get, post, when } from './api'
import { Btn, Card, ErrorState, Icon, I, Loading, RuleChip, Section } from './ui'
import { GraphView } from './Graph'

const Result = ({ ok, children }) => <div className={`flex items-center gap-2 text-lg font-semibold ${ok ? 'text-grn' : 'text-red'}`}><Icon d={ok ? I.check : I.alert} sw={2.5} />{children}</div>

export default function Evaluator({ tick }) {
  const [rerun, setRerun] = useState(null); const [scan, setScan] = useState(null); const [plant, setPlant] = useState(null)
  const [replay, setReplay] = useState(null); const [prec, setPrec] = useState(null); const [g, setG] = useState(null); const [busy, setBusy] = useState('')
  const [loading, setLoading] = useState(true); const [loadError, setLoadError] = useState(null)
  const [actionError, setActionError] = useState(null); const [actionRetry, setActionRetry] = useState(null)
  const latest = useRef(0)
  const load = useCallback(async () => {
    const request = ++latest.current
    setLoading(true)
    setLoadError(null)
    try {
      const [nextPrec, nextGraph] = await Promise.all([get('precedence'), get('graph')])
      if (request === latest.current) {
        setPrec(nextPrec)
        setG(nextGraph)
      }
    } catch (reason) {
      if (request === latest.current) setLoadError(reason)
    } finally {
      if (request === latest.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    const frame = requestAnimationFrame(() => { void load() })
    return () => { cancelAnimationFrame(frame); latest.current += 1 }
  }, [load, tick])
  const go = (key, action) => async () => {
    if (busy) return
    setBusy(key)
    setActionError(null)
    setActionRetry(null)
    try {
      await action()
    } catch (reason) {
      setActionError(reason)
      setActionRetry(() => go(key, action))
    } finally {
      setBusy('')
    }
  }
  if (loading) return <Loading label="Loading evaluator data" />
  if (loadError) return <ErrorState error={loadError} onRetry={load} title="Could not load evaluator data." />
  return (
    <div className="grid max-w-[1200px] grid-cols-1 gap-5 md:grid-cols-2">
      {actionError && <div className="md:col-span-2"><ErrorState error={actionError} onRetry={actionRetry} title="The evaluation did not complete." /></div>}
      <Card className="flex flex-col gap-4 p-6">
        <div><h2 className="text-lg font-semibold">Runs twice, same bytes</h2><p className="m-0 text-sub">Runs the whole pipeline twice on tickets.json and compares every output file byte for byte.</p></div>
        <Btn onClick={go('r', () => post('rerun-check').then(setRerun))} disabled={!!busy} className="self-start">{busy === 'r' ? 'Running twice' : 'Run the double-run diff'}</Btn>
        {rerun && <Result ok={rerun.identical}>{rerun.differences.length} differences across {rerun.files_compared} files</Result>}
      </Card>
      <Card className="flex flex-col gap-4 p-6">
        <div><h2 className="text-lg font-semibold">No personal data leaves</h2><p className="m-0 text-sub">Scans outputs/, audit/ and logs/ for phone, aadhaar and licence numbers. Test mode plants a fake number in a scratch copy to prove the scanner bites.</p></div>
        <div className="flex flex-wrap gap-3"><Btn onClick={go('s', () => post('pii-scan', { plant: false }).then(setScan))} disabled={!!busy}>{busy === 's' ? 'Scanning' : 'Run the PII scan'}</Btn>
          <Btn kind="outline" onClick={go('p', () => post('pii-scan', { plant: true }).then(setPlant))} disabled={!!busy}>{busy === 'p' ? 'Testing scan' : 'Test mode: plant a leak'}</Btn></div>
        {scan && <Result ok={scan.leaks === 0}>{scan.leaks} leaks in {scan.scanned.join(', ')}</Result>}
        {plant && <div className="text-sub">Planted copy: <span className="font-semibold text-amb">{plant.leaks} leaks caught</span> ({plant.hits.map(h => h.kind).join(', ')}). The live outputs were not touched.</div>}
      </Card>
      <Card className="flex flex-col gap-4 p-6">
        <div><h2 className="text-lg font-semibold">Every decision has a story</h2><p className="m-0 text-sub">Replays the full audit trail for a random processed ticket.</p></div>
        <Btn onClick={go('a', () => get('random-ticket').then(setReplay))} disabled={!!busy} className="self-start">{busy === 'a' ? 'Loading replay' : 'Replay a random ticket'}</Btn>
        {replay && <div className="flex flex-col gap-3"><Section>{replay.ticket_id}</Section>
          {replay.steps.map((s, i) => <div key={i} className="flex flex-col gap-1 border-l-2 border-line pl-3"><div className="flex items-baseline gap-2"><span className="font-semibold">{s.step}</span><span className="text-[13px] text-mute">{when(s.at)} · {s.by}</span></div><div className="text-[15px]">{s.decision}</div>
            {s.rules.length > 0 && <div className="flex flex-wrap gap-1.5">{s.rules.map(r => <RuleChip key={r.id} r={r} />)}</div>}</div>)}</div>}
      </Card>
      <Card className="flex flex-col gap-4 p-6">
        <div><h2 className="text-lg font-semibold">Sources disagree, precedence decides</h2><p className="m-0 text-sub">Order: {prec?.order.join(' > ')}. Every conflict found in the data, with the loser kept on record.</p></div>
        {prec && <div className="overflow-x-auto"><table className="w-full text-[15px]"><thead><tr className="text-left text-[13px] uppercase tracking-wider text-mute"><th className="py-1 pr-3">Entity</th><th className="pr-3">Fact</th><th className="pr-3">Loser said</th><th className="pr-3">Winner</th></tr></thead>
          <tbody>{prec.conflicts.map((c, i) => <tr key={i} className="border-t border-line"><td className="py-2 pr-3 font-mono text-sm">{c.entity}</td><td className="pr-3">{c.key.replace('_', ' ')}</td><td className="pr-3 text-sub">{c.source}: {c.value}</td><td className="pr-3 font-semibold">{c.vs_source}: {c.vs_value}</td></tr>)}</tbody></table>
          <div className="mt-3 text-sm text-mute">Plus {prec.same_source_duplicates.length} duplicate rows inside fleet_master itself, first row wins.</div></div>}
      </Card>
      <Card className="flex flex-col gap-4 p-6 md:col-span-2">
        <div><h2 className="text-lg font-semibold">What the store knows, as a graph</h2><p className="m-0 text-sub">Clients, hubs and the rules that shaped dispatches, from live store queries.</p></div>
        <div className="mx-auto w-full max-w-[720px]"><GraphView data={g} center={g?.nodes?.find(n => n.kind === 'hub')?.id} w={720} h={520} /></div>
      </Card>
    </div>
  )
}
