import { useCallback, useEffect, useRef, useState } from 'react'
import { get, post, upload } from './api'
import { Btn, ErrorState, Icon, I, IconBtn } from './ui'
import Dashboard, { FILTERS } from './Dashboard'
import Attention from './Attention'
import History from './History'
import Evaluator from './Evaluator'

const isMobile = () => window.innerWidth < 768
// Nav links map onto the dashboard filter; Audit and Evaluator are their own pages.
const NAV = [['Overview', 'All'], ['Breakdowns', 'All'], ['Approvals', 'Waiting approval'], ['Audit', 'audit'], ['Evaluator', 'eval']]
const BUSY_LABEL = { run: 'Running the pipeline', rerun: 'Running the re-run check', upload: 'Processing the new file' }

export default function App() {
  const [view, setView] = useState(() => isMobile() ? 'Waiting approval' : 'All')   // a FILTERS entry, 'audit', 'eval' or 'map'
  const [nav, setNav] = useState(() => isMobile() ? 'Approvals' : 'Overview')
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [actionRetry, setActionRetry] = useState(null)
  const [history, setHistory] = useState(null)
  const [busy, setBusy] = useState('')
  const [tick, setTick] = useState(0)
  const statsRequest = useRef(0)
  const file = useRef()
  const refresh = useCallback(async () => {
    const request = ++statsRequest.current
    setStatsError(null); setTick(t => t + 1)
    try { const next = await get('stats'); if (request === statsRequest.current) setStats(next) }
    catch (error) { if (request === statsRequest.current) setStatsError(error) }
  }, [])
  useEffect(() => { const f = requestAnimationFrame(() => { void refresh() }); return () => { cancelAnimationFrame(f); statsRequest.current += 1 } }, [refresh])
  const mutate = async (name, action, after) => {
    if (busy) return
    setBusy(name); setActionError(null); setActionRetry(null)
    try { await action(); after?.(); await refresh() }
    catch (error) { setActionError(error); setActionRetry(() => () => mutate(name, action, after)) }
    finally { setBusy('') }
  }
  const run = () => mutate('run', () => post('run'))
  const rerun = () => mutate('rerun', () => post('rerun-check'))
  const onFile = async (e) => {
    const input = e.target, selected = input.files[0]
    if (!selected) return
    try { await mutate('upload', () => upload(selected), () => go('Audit', 'audit')) } finally { input.value = '' }
  }
  const go = (label, v) => { setNav(label); setView(v) }
  const setFilter = (v) => go(NAV.find(([, x]) => x === v && v !== 'All')?.[0] || (FILTERS.includes(v) ? 'Breakdowns' : nav), v)
  const rr = stats?.rerun
  const needs = (stats?.attention || 0) + (stats?.awaiting || 0) > 0
  const page = view === 'audit' ? <Attention tick={tick} onHistory={setHistory} onChange={refresh} />
    : view === 'eval' ? <Evaluator tick={tick} />
    : <Dashboard tick={tick} onHistory={setHistory} onChange={refresh} filter={view === 'map' ? 'All' : view} setFilter={setFilter} mobileView={view === 'map' ? 'map' : 'list'} />

  return (
    <div className="min-h-screen bg-frame">
      <div className="min-h-screen px-3 pb-28 pt-3 text-ink md:px-6 md:pb-6 md:pt-4">
        <input ref={file} type="file" accept=".json,.jsonl,.csv" className="hidden" onChange={onFile} />
        <header className="flex items-center justify-between gap-4 py-2 md:py-3">
          <button onClick={() => go('Overview', 'All')} className="flex items-center gap-2.5"><span className="text-gold"><Icon d={<><path d="M5 6h14" /><path d="M12 6v13" /><path d="M8 19h8" /></>} size={26} sw={3} /></span><span className="whitespace-nowrap text-[22px] font-bold tracking-tight">Meridian Ops.</span></button>
          <nav aria-label="Primary" className="hidden items-center gap-6 whitespace-nowrap lg:flex">
            {NAV.map(([l, v]) => <button key={l} onClick={() => go(l, v)} aria-current={nav === l ? 'page' : undefined} className={`text-[16px] ${nav === l ? 'font-semibold text-ink' : 'text-sub hover:text-ink'}`}>{l}</button>)}
          </nav>
          <div className="flex shrink-0 items-center gap-2.5">
            <button onClick={rerun} disabled={!!busy} title={rr ? `Last checked ${new Date(rr.at).toLocaleTimeString()} on ${rr.files} files` : 'Not run yet'}
              className={`hidden h-11 items-center gap-1.5 whitespace-nowrap rounded-full px-4 text-sm font-medium 2xl:flex ${rr ? (rr.identical ? 'bg-grn-soft text-grn' : 'bg-red-soft text-red') : 'bg-card2 text-sub'}`}>
              <Icon d={I.check} size={16} sw={2} />{busy === 'rerun' ? 'Running twice' : rr ? (rr.identical ? 'Re-run check · identical' : `Re-run check · ${rr.differences.length} differ`) : 'Re-run check'}
            </button>
            <div className="hidden gap-2.5 md:flex"><span className="hidden xl:block"><Btn kind="outline" onClick={() => file.current?.click()} disabled={!!busy} className="whitespace-nowrap"><Icon d={I.upload} />Process new file</Btn></span><IconBtn aria-label="Process new file" title="Process new file" onClick={() => file.current?.click()} disabled={!!busy} className="border border-white/20 bg-transparent xl:hidden"><Icon d={I.upload} /></IconBtn>
            <Btn onClick={run} disabled={!!busy} className="whitespace-nowrap"><Icon d={I.play} size={16} />{busy === 'run' ? 'Running' : 'Run pipeline'}</Btn></div>
            <IconBtn aria-label="Process new file" onClick={() => file.current?.click()} disabled={!!busy} className="md:hidden"><Icon d={I.upload} /></IconBtn>
            <IconBtn aria-label="Run pipeline" onClick={run} disabled={!!busy} className="bg-gold text-frame md:hidden"><Icon d={I.play} /></IconBtn>
            <IconBtn aria-label="Search" onClick={() => { go('Breakdowns', 'All'); setTimeout(() => document.querySelector('input[aria-label="Search breakdowns"]')?.focus(), 50) }} className="hidden sm:flex"><Icon d={I.search} size={20} /></IconBtn>
            <IconBtn aria-label={needs ? 'Items need attention' : 'Nothing needs attention'} onClick={() => go('Audit', 'audit')} className="relative hidden sm:flex"><Icon d={I.bell} size={20} />{needs && <span className="absolute right-3 top-2.5 h-2 w-2 rounded-full bg-gold" />}</IconBtn>
            <div className="hidden h-[60px] items-center gap-3 whitespace-nowrap rounded-full bg-card2 py-2 pl-2 pr-4 xl:flex">
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-gold text-[15px] font-bold text-frame">D</span>
              <span className="flex flex-col leading-tight"><span className="text-[15px] font-semibold">Dispatch desk</span><span className="text-[13px] text-sub">Dispatcher</span></span>
              <Icon d={I.chev} size={18} className="text-sub" />
            </div>
          </div>
        </header>
        <main className="min-w-0 pt-2 md:pt-3">
          {busy && <div role="status" className="mb-4 rounded-2xl bg-card2 px-4 py-3 text-sm font-medium text-gold">{BUSY_LABEL[busy]}</div>}
          {(actionError || statsError) && <div className="mb-4 max-w-[960px]"><ErrorState error={actionError || statsError} onRetry={actionError ? actionRetry : refresh} title={actionError ? 'The action did not complete.' : 'Status counts are unavailable.'} /></div>}
          {page}
        </main>
      </div>
      <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-30 flex bg-card pb-5 pt-1 md:hidden">
        {[['Map', 'map', I.map], ['Breakdowns', 'All', I.list], ['Approvals', 'Waiting approval', I.inbox], ['Audit', 'audit', I.alert], ['Evaluator', 'eval', I.check]].map(([l, v, ic]) => (
          <button key={l} onClick={() => go(l, v)} aria-current={view === v ? 'page' : undefined} className={`flex min-w-0 flex-1 flex-col items-center gap-1 px-0.5 pt-2.5 pb-2 text-[11px] font-medium ${view === v ? 'text-gold' : 'text-sub'}`}><Icon d={ic} />{l}</button>
        ))}
      </nav>
      {history && <History ticketId={history} onClose={() => setHistory(null)} />}
    </div>
  )
}
