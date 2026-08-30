// Small shared pieces. Dark charcoal theme, gold for active states only; red/amber/green stay semantic.
import { useEffect, useId, useRef } from 'react'
export const Icon = ({ d, size = 18, sw = 1.5, ...p }) => (
  <svg aria-hidden="true" focusable="false" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" {...p}>{d}</svg>
)
export const I = {
  play: <path d="M6 4l14 8-14 8z" />, check: <path d="M5 12l5 5 9-10" />, send: <><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4z" /></>,
  edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></>, clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  x: <path d="M6 6l12 12M18 6L6 18" />, alert: <><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17.5v.5" /></>,
  map: <><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></>, list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  inbox: <><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5 5h14l3 7v7H2v-7z" /></>, back: <path d="M15 5l-7 7 7 7" />, upload: <><path d="M12 16V4M6 10l6-6 6 6" /><path d="M4 20h16" /></>,
  graph: <><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="M7 7l4 9M17 7l-4 9M7 6h10" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></>, bell: <><path d="M6 16V11a6 6 0 0112 0v5l2 2H4z" /><path d="M10 21h4" /></>,
  chev: <path d="M6 9l6 6 6-6" />, expand: <><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" /></>, arrow: <><path d="M7 17L17 7" /><path d="M8 7h9v9" /></>,
  cal: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></>, filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  truck: <><path d="M2 7h11v9H2zM13 10h4l3 3v3h-7z" /><circle cx="6" cy="17.5" r="1.5" /><circle cx="17" cy="17.5" r="1.5" /></>,
  engine: <><path d="M4 10h3l2-2h5l2 2h4v7H4z" /><path d="M9 6h4M11 4v2M4 13H2M20 13h2" /></>, brake: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 4v2M12 18v2M4 12h2M18 12h2" /></>,
  tyre: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><path d="M12 3v5M12 16v5M3 12h5M16 12h5" /></>, fuel: <><path d="M4 21V5a2 2 0 012-2h6a2 2 0 012 2v16" /><path d="M4 10h10M14 8h3l3 3v6a2 2 0 01-4 0v-4h-2" /></>,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" /></>,
  wrench: <path d="M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.4 2.4-2.4-.6-.6-2.4z" />,
  bolt: <path d="M13 2L4 14h7l-1 8 9-12h-7z" />, box: <><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M4 7.5l8 4.5 8-4.5M12 12v9" /></>,
}
export const ISSUE_KINDS = [['Engine', I.engine, /engine|overheat|coolant|radiator|turbo/], ['Brakes', I.brake, /brake/], ['Tyres', I.tyre, /tyre|tire|puncture/], ['Fuel', I.fuel, /fuel|diesel/], ['Gearbox', I.gear, /gear|clutch/], ['Electrical', I.bolt, /electric|alternator|battery/]]
export const issueKind = (issue = '') => ISSUE_KINDS.find(([, , re]) => re.test(issue.toLowerCase()))?.[0] || 'Other'
export const kindIcon = (kind) => ISSUE_KINDS.find(([k]) => k === kind)?.[1] || I.wrench

const tone = { red: 'bg-red-soft text-red', amb: 'bg-amb-soft text-amb', grn: 'bg-grn-soft text-grn', gray: 'bg-card2 text-sub', gold: 'bg-gold text-frame' }
export const Chip = ({ children, t = 'gray', className = '' }) => <span className={`inline-flex h-7 items-center rounded-full px-3 text-[13px] font-medium ${tone[t]} ${className}`}>{children}</span>
export const statusTone = (s) => ({ Resolved: 'grn', 'Awaiting approval': 'amb', Approved: 'grn', 'Set aside': 'red', Quarantined: 'red' }[s] || 'gray')
export const statusText = (s) => ({ Resolved: 'text-grn', 'Awaiting approval': 'text-amb', Approved: 'text-grn', 'Set aside': 'text-red' }[s] || 'text-sub')
export const RuleChip = ({ r }) => <span className="inline-flex h-[26px] items-center rounded-full bg-card3 px-2.5 font-mono text-[12px] font-medium text-gold">{r.label}</span>
export const Btn = ({ kind = 'primary', className = '', children, ...p }) => {
  const k = { primary: 'bg-gold text-frame hover:bg-gold-dark', green: 'bg-grn text-frame hover:brightness-110', outline: 'border border-white/20 bg-transparent text-ink hover:bg-white/5', soft: 'bg-card2 text-ink hover:bg-card3', amber: 'border border-amb/50 bg-transparent text-amb' }[kind]
  return <button className={`inline-flex h-11 items-center justify-center gap-2 rounded-full px-5 text-[15px] font-semibold disabled:opacity-50 ${k} ${className}`} {...p}>{children}</button>
}
export const IconBtn = ({ className = '', children, ...p }) => <button className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-card2 text-ink hover:bg-card3 disabled:opacity-50 ${className}`} {...p}>{children}</button>
export const Card = ({ className = '', children, ...p }) => <div className={`rounded-3xl bg-card p-6 ${className}`} {...p}>{children}</div>
export const CardTitle = ({ children, action, onAction }) => (
  <div className="flex items-start justify-between gap-3"><h2 className="text-[21px] font-semibold leading-tight tracking-tight">{children}</h2>
    {onAction && <button onClick={onAction} aria-label={action} className="-mr-1 -mt-1 flex h-9 w-9 items-center justify-center rounded-full text-sub hover:bg-card2"><Icon d={I.arrow} size={20} /></button>}</div>
)
export const Empty = ({ title, sub }) => (
  <div className="flex flex-col items-center gap-3 rounded-3xl bg-card px-8 py-12 text-center">
    <div className="flex h-14 w-14 items-center justify-center rounded-full bg-grn-soft text-grn"><Icon d={I.check} size={28} sw={2} /></div>
    <div className="text-xl font-semibold">{title}</div><div className="text-sub">{sub}</div>
  </div>
)
export const Loading = ({ label = 'Loading' }) => <div role="status" className="rounded-3xl bg-card px-5 py-8 text-center text-sub">{label}</div>
export const ErrorState = ({ error, onRetry, title = 'Could not load this view.' }) => (
  <div role="alert" className="flex flex-col items-start gap-3 rounded-2xl bg-red-soft px-5 py-5 text-red">
    <div><div className="font-semibold">{title}</div><div className="mt-1 break-words text-sm">{error?.message || 'The request failed.'}</div></div>
    {onRetry && <Btn kind="outline" onClick={onRetry} className="h-10 border-red/40 text-red">Try again</Btn>}
  </div>
)
export const Section = ({ children }) => <div className="text-[12px] font-semibold uppercase tracking-[0.08em] text-mute">{children}</div>

// Right slide-over with focus trap; History and the ticket detail both use it.
export function Drawer({ title, sub, onClose, children, wide }) {
  const dialog = useRef(null), close = useRef(null), id = useId()
  useEffect(() => {
    const previous = document.activeElement
    const onKeyDown = event => {
      if (event.key === 'Escape') return onClose()
      if (event.key !== 'Tab') return
      const focusable = [...(dialog.current?.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])]
      if (focusable.length === 0) return
      const first = focusable[0], last = focusable.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKeyDown)
    close.current?.focus()
    return () => { document.removeEventListener('keydown', onKeyDown); previous?.focus?.() }
  }, [onClose])
  return (
    <>
      <div aria-hidden="true" className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <aside ref={dialog} role="dialog" aria-modal="true" aria-labelledby={id} className={`fixed inset-y-0 right-0 z-50 flex w-full flex-col gap-6 overflow-y-auto bg-card px-5 py-6 text-ink shadow-[-12px_0_40px_rgba(0,0,0,.45)] sm:px-7 md:inset-y-3 md:right-3 md:rounded-3xl ${wide ? 'max-w-[640px]' : 'max-w-[540px]'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1"><h2 id={id} className="break-words text-[22px] font-semibold tracking-tight">{title}</h2>{sub && <div className="break-words text-sm text-sub">{sub}</div>}</div>
          <IconBtn ref={close} onClick={onClose} aria-label="Close"><Icon d={I.x} size={20} /></IconBtn>
        </div>
        {children}
      </aside>
    </>
  )
}
