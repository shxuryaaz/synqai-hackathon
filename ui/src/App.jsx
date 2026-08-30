import { useCallback, useEffect, useRef, useState } from 'react'
import { get, post, upload } from './api'
import { Btn, ErrorState, Icon, I, Pill } from './ui'
import Operations from './Operations'
import Approvals from './Approvals'
import Attention from './Attention'
import History from './History'
import Evaluator from './Evaluator'

const isMobile = () => window.innerWidth < 768
const TABS = [['ops', 'Operations'], ['appr', 'Approvals'], ['att', 'Attention'], ['eval', 'Evaluator']]
const BUSY_LABEL = { run: 'Running the pipeline', rerun: 'Running the re-run check', upload: 'Processing the new file' }

export default function App() {
  const [tab, setTab] = useState(() => isMobile() ? 'appr' : 'ops')
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [actionRetry, setActionRetry] = useState(null)
  const [history, setHistory] = useState(null)   // ticket id open in the drawer
  const [busy, setBusy] = useState('')
  const [tick, setTick] = useState(0)            // bump to make screens refetch
  const statsRequest = useRef(0)
  const file = useRef()
  const refresh = useCallback(async () => {
    const request = ++statsRequest.current
    setStatsError(null)
    setTick(t => t + 1)
    try {
      const next = await get('stats')
      if (request === statsRequest.current) setStats(next)
    } catch (error) {
      if (request === statsRequest.current) setStatsError(error)
    }
  }, [])
  useEffect(() => {
    const frame = requestAnimationFrame(() => { void refresh() })
    return () => { cancelAnimationFrame(frame); statsRequest.current += 1 }
  }, [refresh])

  const mutate = async (name, action, after) => {
    if (busy) return
    setBusy(name)
    setActionError(null)
    setActionRetry(null)
    try {
      await action()
      after?.()
      await refresh()
    } catch (error) {
      setActionError(error)
      setActionRetry(() => () => mutate(name, action, after))
    } finally {
      setBusy('')
    }
  }
  const run = () => mutate('run', () => post('run'))
  const rerun = () => mutate('rerun', () => post('rerun-check'))
  const onFile = async (e) => {
    const input = e.target
    const selected = input.files[0]
    if (!selected) return
    try { await mutate('upload', () => upload(selected), () => setTab('att')) } finally { input.value = '' }
  }
  const rr = stats?.rerun

  return (
    <div className="min-h-screen pb-36 md:pb-0">
      <header className="border-b border-line bg-white px-4 md:px-8">
        <input ref={file} type="file" accept=".json,.jsonl,.csv" className="hidden" onChange={onFile} />
        <div className="flex h-auto flex-col gap-3 py-3 lg:h-[72px] lg:flex-row lg:items-center lg:justify-between lg:py-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5"><div className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-ind"><Icon d={<path d="M4 12h16M12 4v16" />} sw={2.5} stroke="#fff" /></div><span className="text-lg font-semibold tracking-tight">Meridian Ops</span></div>
            <div className="flex gap-2 lg:hidden">
              <Btn kind="outline" onClick={() => file.current?.click()} disabled={!!busy} aria-label="Process new file" title="Process new file" className="w-11 px-0"><Icon d={I.upload} /></Btn>
              <Btn onClick={run} disabled={!!busy} className="px-4"><Icon d={I.play} />{busy === 'run' ? 'Running' : 'Run'}</Btn>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-1.5 sm:flex sm:gap-3">
            <Pill n={stats?.active ?? '–'} label={isMobile() ? 'Active' : 'Active breakdowns'} t={stats?.active ? 'red' : 'gray'} />
            <Pill n={stats?.awaiting ?? '–'} label={isMobile() ? 'Waiting' : 'Awaiting approval'} t={stats?.awaiting ? 'amb' : 'gray'} />
            <Pill n={stats?.attention ?? '–'} label={isMobile() ? 'Attention' : 'Needs attention'} t="gray" />
          </div>
          <div className="hidden items-center gap-3 lg:flex">
            <button onClick={rerun} disabled={!!busy} title={rr ? `Last checked ${new Date(rr.at).toLocaleTimeString()} on ${rr.files} files` : 'Not run yet'}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${rr ? (rr.identical ? 'bg-grn-soft text-grn' : 'bg-red-soft text-red') : 'bg-[#f1f2f5] text-sub'}`}>
              <Icon d={I.check} size={16} sw={2.5} />{busy === 'rerun' ? 'Running twice' : rr ? (rr.identical ? 'Re-run check · identical' : `Re-run check · ${rr.differences.length} differ`) : 'Re-run check'}
            </button>
            <Btn kind="outline" onClick={() => file.current.click()} disabled={!!busy}><Icon d={I.upload} />Process new file</Btn>
            <Btn onClick={run} disabled={!!busy}><Icon d={I.play} />{busy === 'run' ? 'Running' : 'Run pipeline'}</Btn>
          </div>
        </div>
        <nav aria-label="Primary" className="hidden h-11 gap-7 md:flex">
          {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} aria-current={tab === k ? 'page' : undefined} className={`h-11 border-b-2 px-1 text-base font-medium ${tab === k ? 'border-ind text-ind' : 'border-transparent text-sub'}`}>{l}</button>)}
        </nav>
      </header>
      <main className="min-w-0 px-4 py-4 md:px-8 md:py-6">
        {busy && <div role="status" className="mb-4 max-w-[960px] rounded-[10px] bg-ind-soft px-4 py-3 text-sm font-medium text-ind">{BUSY_LABEL[busy]}</div>}
        {(actionError || statsError) && <div className="mb-4 max-w-[960px]"><ErrorState error={actionError || statsError} onRetry={actionError ? actionRetry : refresh} title={actionError ? 'The action did not complete.' : 'Status counts are unavailable.'} /></div>}
        {tab === 'ops' && <Operations tick={tick} onHistory={setHistory} mobileView="feed" />}
        {tab === 'map' && <Operations tick={tick} onHistory={setHistory} mobileView="map" />}
        {tab === 'appr' && <Approvals tick={tick} onHistory={setHistory} onChange={refresh} />}
        {tab === 'att' && <Attention tick={tick} onHistory={setHistory} onChange={refresh} />}
        {tab === 'eval' && <Evaluator tick={tick} />}
      </main>
      <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-white pb-5 md:hidden">
        {[['map', 'Map', I.map], ['ops', 'Breakdowns', I.list], ['appr', 'Approvals', I.inbox], ['att', 'Attention', I.alert], ['eval', 'Evaluator', I.check]].map(([k, l, ic]) => (
          <button key={k} onClick={() => setTab(k)} aria-current={tab === k ? 'page' : undefined} className={`flex min-w-0 flex-1 flex-col items-center gap-1 px-0.5 pt-2.5 pb-2 text-[11px] font-medium sm:text-[13px] ${tab === k ? 'text-ind' : 'text-sub'}`}><Icon d={ic} />{l}</button>
        ))}
      </nav>
      {history && <History ticketId={history} onClose={() => setHistory(null)} />}
    </div>
  )
}
