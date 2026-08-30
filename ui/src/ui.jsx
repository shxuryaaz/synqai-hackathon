// Small shared pieces. Colors are status-only: red/amber/green never decorate.
export const Icon = ({ d, size = 18, sw = 2, ...p }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" {...p}>{d}</svg>
)
export const I = {
  play: <path d="M6 4l14 8-14 8z" />, check: <path d="M5 12l5 5 9-10" />, send: <><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4z" /></>,
  edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></>, clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  x: <path d="M6 6l12 12M18 6L6 18" />, alert: <><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17.5v.5" /></>,
  map: <><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></>, list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  inbox: <><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5 5h14l3 7v7H2v-7z" /></>, back: <path d="M15 5l-7 7 7 7" />, upload: <><path d="M12 16V4M6 10l6-6 6 6" /><path d="M4 20h16" /></>,
  graph: <><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="M7 7l4 9M17 7l-4 9M7 6h10" /></>,
}
const tone = { red: 'bg-red-soft text-red border-red/15', amb: 'bg-amb-soft text-amb border-amb/15', grn: 'bg-grn-soft text-grn border-grn/15', gray: 'bg-[#f1f2f5] text-sub border-line' }
export const Pill = ({ n, label, t }) => (
  <div className={`flex items-center gap-2.5 rounded-full border px-4 py-2 ${tone[t]}`}><span className="text-xl font-semibold leading-none">{n}</span><span className="text-sm font-medium text-sub">{label}</span></div>
)
export const Chip = ({ children, t = 'gray' }) => <span className={`inline-flex h-7 items-center rounded-full px-3 text-sm font-medium ${tone[t]}`}>{children}</span>
export const statusTone = (s) => ({ Resolved: 'grn', 'Awaiting approval': 'amb', Quarantined: 'red' }[s] || 'gray')
export const sevColor = (s) => ({ HIGH: 'bg-red', MEDIUM: 'bg-amb', LOW: 'bg-grn' }[s] || 'bg-mute')
export const RuleChip = ({ r }) => <span className="inline-flex h-[26px] items-center rounded-md bg-ind-soft px-2.5 font-mono text-[13px] font-medium text-ind">{r.label}</span>
export const Btn = ({ kind = 'primary', className = '', children, ...p }) => {
  const k = { primary: 'bg-ind text-white hover:bg-ind-dark', green: 'bg-grn text-white hover:bg-green-700', outline: 'border-[1.5px] border-[#cdd1d9] bg-white text-ink hover:bg-bg', soft: 'bg-ind-soft text-ind hover:bg-indigo-100', amber: 'border-[1.5px] border-amber-500 bg-white text-amber-900' }[kind]
  return <button className={`inline-flex h-11 items-center justify-center gap-2 rounded-[10px] px-5 text-base font-semibold disabled:opacity-50 ${k} ${className}`} {...p}>{children}</button>
}
export const Card = ({ className = '', children, ...p }) => <div className={`rounded-xl border border-line bg-white p-4 shadow-card ${className}`} {...p}>{children}</div>
export const Empty = ({ title, sub }) => (
  <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#cdd1d9] bg-white px-8 py-12 text-center">
    <div className="flex h-14 w-14 items-center justify-center rounded-full bg-grn-soft text-grn"><Icon d={I.check} size={28} sw={2.5} /></div>
    <div className="text-xl font-semibold">{title}</div><div className="text-sub">{sub}</div>
  </div>
)
export const Section = ({ children }) => <div className="text-[13px] font-semibold uppercase tracking-[0.06em] text-mute">{children}</div>
