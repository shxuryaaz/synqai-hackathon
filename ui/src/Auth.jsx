import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { get, setToken } from './api'
import { Btn, Icon, Loading } from './ui'

// Gate: /api/config says whether Supabase is configured. Locally it is not, so the app renders straight away.
export default function Auth({ children }) {
  const [state, setState] = useState({ loading: true, client: null, session: null, error: null })
  useEffect(() => {
    let sub
    get('config').then(cfg => {
      if (!cfg.supabase_url) return setState({ loading: false, client: null, session: null })
      const client = createClient(cfg.supabase_url, cfg.supabase_anon_key)
      const apply = (session) => { setToken(session?.access_token); setState({ loading: false, client, session }) }
      client.auth.getSession().then(({ data }) => apply(data.session))
      sub = client.auth.onAuthStateChange((_e, session) => apply(session)).data.subscription
    }).catch(error => setState({ loading: false, client: null, session: null, error }))
    return () => sub?.unsubscribe()
  }, [])
  if (state.loading) return <div className="flex min-h-screen items-center justify-center bg-frame p-6"><Loading label="Checking sign-in" /></div>
  if (state.client && !state.session) return (
    <div className="flex min-h-screen items-center justify-center bg-frame p-6 text-ink">
      <div className="flex w-full max-w-[380px] flex-col items-center gap-6 rounded-3xl bg-card px-8 py-10 text-center">
        <span className="text-gold"><Icon d={<><path d="M5 6h14" /><path d="M12 6v13" /><path d="M8 19h8" /></>} size={40} sw={3} /></span>
        <div><div className="text-[22px] font-bold tracking-tight">Meridian Ops.</div><div className="mt-1 text-sub">Dispatch desk sign-in</div></div>
        {state.error && <div className="text-sm text-red">{state.error.message}</div>}
        <Btn onClick={() => state.client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin } })} className="w-full">Continue with Google</Btn>
      </div>
    </div>
  )
  return children({ user: state.session?.user, signOut: state.client ? () => state.client.auth.signOut() : null })
}
