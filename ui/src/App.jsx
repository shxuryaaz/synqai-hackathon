import { useEffect, useRef, useState } from 'react'
import { get, post, upload } from './api'
import { Btn, Icon, I, Pill } from './ui'
import Operations from './Operations'
import Approvals from './Approvals'
import Attention from './Attention'
import History from './History'
import Evaluator from './Evaluator'

const isMobile = () => window.innerWidth < 768
const TABS = [['ops', 'Operations'], ['appr', 'Approvals'], ['att', 'Attention'], ['eval', 'Evaluator']]

export default function App() {
  const [tab, setTab] = useState(() => isMobile() ? 'appr' : 'ops')
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState(null)   // ticket id open in the drawer
  const [busy, setBusy] = useState('')
  const [tick, setTick] = useState(0)            // bump to make screens refetch
  const file = useRef()
  const refresh = () => { get('stats').then(setStats); setTick(t => t + 1) }
  useEffect(refresh, [])

  const run = async () => { setBusy('run'); await post('run'); setBusy(''); refresh() }
  const rerun = async () => { setBusy('rerun'); await post('rerun-check'); setBusy(''); refresh() }
  const onFile = async (e) => { const f = e.target.files[0]; if (!f) return; setBusy('run'); await upload(f); setBusy(''); e.target.value = ''; refresh(); setTab('att') }
  const rr = stats?.rerun

  return (
    <div className="min-h-screen pb-24 md:pb-0">
      <header className="border-b border-line bg-white px-4 md:px-8">
        <div className="flex h-auto flex-col gap-3 py-3 md:h-[72px] md:flex-row md:items-center md:justify-between md:py-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5"><div className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-ind"><Icon d={<path d="M4 12h16M12 4v16" />} sw={2.5} stroke="#fff" /></div><span className="text-lg font-semibold tracking-tight">Meridian Ops</span></div>
            <div className="flex gap-2 md:hidden"><Btn onClick={run} disabled={!!busy} className="px-4"><Icon d={I.play} />{busy === 'run' ? 'Running' : 'Run'}</Btn></div>
          </div>
          <div className="flex gap-2 md:gap-3">
            <Pill n={stats?.active ?? '–'} label={isMobile() ? 'Active' : 'Active breakdowns'} t={stats?.active ? 'red' : 'gray'} />
            <Pill n={stats?.awaiting ?? '–'} label={isMobile() ? 'Waiting' : 'Awaiting approval'} t={stats?.awaiting ? 'amb' : 'gray'} />
            <Pill n={stats?.attention ?? '–'} label={isMobile() ? 'Attention' : 'Needs attention'} t="gray" />
          </div>
          <div className="hidden items-center gap-3 md:flex">
            <button onClick={rerun} disabled={!!busy} title={rr ? `Last checked ${new Date(rr.at).toLocaleTimeString()} on ${rr.files} files` : 'Not run yet'}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${rr ? (rr.identical ? 'bg-grn-soft text-grn' : 'bg-red-soft text-red') : 'bg-[#f1f2f5] text-sub'}`}>
              <Icon d={I.check} size={16} sw={2.5} />{busy === 'rerun' ? 'Running twice' : rr ? (rr.identical ? 'Re-run check · identical' : `Re-run check · ${rr.differences.length} differ`) : 'Re-run check'}
            </button>
            <input ref={file} type="file" accept=".json,.jsonl,.csv" className="hidden" onChange={onFile} />
            <Btn kind="outline" onClick={() => file.current.click()} disabled={!!busy}><Icon d={I.upload} />Process new file</Btn>
            <Btn onClick={run} disabled={!!busy}><Icon d={I.play} />{busy === 'run' ? 'Running' : 'Run pipeline'}</Btn>
          </div>
        </div>
        <nav className="hidden h-11 gap-7 md:flex">
          {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`h-11 border-b-2 px-1 text-base font-medium ${tab === k ? 'border-ind text-ind' : 'border-transparent text-sub'}`}>{l}</button>)}
        </nav>
      </header>
      <main className="px-4 py-4 md:px-8 md:py-6">
        {tab === 'ops' && <Operations tick={tick} onHistory={setHistory} mobileView="feed" />}
        {tab === 'map' && <Operations tick={tick} onHistory={setHistory} mobileView="map" />}
        {tab === 'appr' && <Approvals tick={tick} onHistory={setHistory} onChange={refresh} />}
        {tab === 'att' && <Attention tick={tick} onHistory={setHistory} onChange={refresh} />}
        {tab === 'eval' && <Evaluator tick={tick} />}
      </main>
      <nav className="fixed inset-x-0 bottom-0 flex border-t border-line bg-white pb-5 md:hidden">
        {[['map', 'Map', I.map], ['ops', 'Breakdowns', I.list], ['appr', 'Approvals', I.inbox], ['att', 'Attention', I.alert]].map(([k, l, ic]) => (
          <button key={k} onClick={() => setTab(k)} className={`flex flex-1 flex-col items-center gap-1 pt-2.5 pb-2 text-[13px] font-medium ${tab === k ? 'text-ind' : 'text-sub'}`}><Icon d={ic} />{l}</button>
        ))}
      </nav>
      {history && <History ticketId={history} onClose={() => setHistory(null)} />}
    </div>
  )
}
