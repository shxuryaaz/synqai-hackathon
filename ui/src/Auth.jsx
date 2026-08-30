import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { get, setToken } from './api'
import { Icon, I, Loading } from './ui'

const G = <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.5 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.3l7.8 6C12.3 13.6 17.7 9.5 24 9.5z" /><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4 7.1-10 7.1-17.5z" /><path fill="#FBBC05" d="M10.4 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.7l7.8-6z" /><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.9 2.3-8.4 2.3-6.3 0-11.7-4.1-13.6-9.8l-7.8 6C6.5 42.6 14.6 48 24 48z" /></svg>

const FEATURES = [
  [I.truck, 'Replacement picked by rule', 'Nearest eligible truck, every skipped one explained.'],
  [I.send, 'You approve, it sends', 'Client message drafted for you. Nothing leaves without a dispatcher.'],
  [I.list, 'Every step on record', 'Sources, rules and timestamps for each decision.'],
]

function Landing({ onGoogle, error, busy }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-frame text-ink">
      <svg aria-hidden="true" className="pointer-events-none absolute inset-0 h-full w-full opacity-[.18]" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
        <defs><pattern id="grid" width="80" height="80" patternUnits="userSpaceOnUse"><path d="M80 0H0V80" fill="none" stroke="#3a3a3e" strokeWidth="1" /></pattern></defs>
        <rect width="1440" height="900" fill="url(#grid)" />
        <path d="M120 720 C 380 520, 520 640, 760 420 S 1180 260, 1340 140" fill="none" stroke="#d8cba3" strokeWidth="2" strokeDasharray="8 10" />
        {[[120, 720], [760, 420], [1340, 140]].map(([x, y]) => <g key={x}><circle cx={x} cy={y} r="14" fill="#161617" stroke="#d8cba3" strokeWidth="2" /><circle cx={x} cy={y} r="4" fill="#d8cba3" /></g>)}
      </svg>
      <div className="relative mx-auto flex min-h-screen max-w-[1180px] flex-col justify-center gap-10 px-6 py-10 lg:flex-row lg:items-center lg:gap-20 lg:px-10">
        <div className="flex max-w-[560px] flex-col gap-8">
          <div className="flex items-center gap-2.5"><span className="text-gold"><Icon d={<><path d="M5 6h14" /><path d="M12 6v13" /><path d="M8 19h8" /></>} size={28} sw={3} /></span><span className="text-[22px] font-bold tracking-tight">Meridian Ops.</span></div>
          <div className="flex flex-col gap-4">
            <span className="inline-flex h-8 w-fit items-center rounded-full bg-card2 px-3 text-[13px] font-medium text-gold">Breakdown response console</span>
            <h1 className="text-[40px] font-bold leading-[1.05] tracking-tight sm:text-[52px]">A truck is down.<br />The plan is already on your desk.</h1>
            <p className="max-w-[460px] text-[17px] leading-relaxed text-sub">Meridian reads the ticket, checks the fleet rules, picks the replacement and drafts the client note. You read it, approve it, and move on.</p>
          </div>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {FEATURES.map(([ic, t, d]) => <li key={t} className="flex items-start gap-4"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-card2 text-gold"><Icon d={ic} size={20} /></span><div><div className="font-semibold">{t}</div><div className="text-[15px] text-sub">{d}</div></div></li>)}
          </ul>
        </div>
        <div className="w-full max-w-[420px] shrink-0 self-center rounded-3xl bg-card p-8 sm:p-10">
          <div className="text-[24px] font-semibold tracking-tight">Dispatch desk sign-in</div>
          <div className="mt-1.5 text-sub">Use the Google account the desk was issued.</div>
          <button onClick={onGoogle} disabled={busy} className="mt-8 flex h-14 w-full items-center justify-center gap-3 rounded-full bg-ink text-[16px] font-semibold text-frame hover:bg-white disabled:opacity-60">{G}{busy ? 'Opening Google' : 'Continue with Google'}</button>
          {error && <div role="alert" className="mt-4 rounded-2xl bg-red-soft px-4 py-3 text-sm text-red">{error}</div>}
          <div className="mt-8 flex flex-col gap-3 border-t border-white/5 pt-6 text-[13px] text-mute">
            <div className="flex items-center gap-2"><Icon d={I.check} size={16} className="text-grn" />Every approval is recorded under your name.</div>
            <div className="flex items-center gap-2"><Icon d={I.check} size={16} className="text-grn" />Driver phone numbers are masked before anything is shown.</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// Gate: /api/config says whether Supabase is configured. Locally it is not, so the app renders straight away.
export default function Auth({ children }) {
  const [state, setState] = useState({ loading: true, client: null, session: null, error: null })
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let sub
    get('config').then(cfg => {
      if (!cfg.supabase_url) return setState({ loading: false, client: null, session: null })
      const client = createClient(cfg.supabase_url, cfg.supabase_anon_key)
      const apply = (session) => { setToken(session?.access_token); setState(s => ({ ...s, loading: false, client, session })) }
      client.auth.getSession().then(({ data }) => apply(data.session))
      sub = client.auth.onAuthStateChange((_e, session) => apply(session)).data.subscription
    }).catch(error => setState({ loading: false, client: null, session: null, error: error.message }))
    return () => sub?.unsubscribe()
  }, [])
  const google = async () => {
    setBusy(true)
    const { error } = await state.client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin } })
    if (error) { setState(s => ({ ...s, error: error.message })); setBusy(false) }
  }
  if (state.loading) return <div className="flex min-h-screen items-center justify-center bg-frame p-6"><Loading label="Checking sign-in" /></div>
  if (state.client && !state.session) return <Landing onGoogle={google} error={state.error} busy={busy} />
  return children({ user: state.session?.user, signOut: state.client ? () => state.client.auth.signOut() : null })
}
