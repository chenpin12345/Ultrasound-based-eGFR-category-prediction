import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-[24px] font-bold leading-tight">{title}</h1>
        {description && <p className="mt-1.5 text-ink-soft">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Panel({
  title,
  aside,
  children,
  className = '',
  flush = false,
}: {
  title?: string
  aside?: ReactNode
  children: ReactNode
  className?: string
  flush?: boolean
}) {
  return (
    <section className={`rounded-lg border border-line bg-white ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 className="text-[16px] font-semibold">{title}</h2>
          {aside}
        </div>
      )}
      <div className={flush ? '' : 'p-5'}>{children}</div>
    </section>
  )
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost'

export function Button({
  children,
  variant = 'secondary',
  icon: Icon,
  disabled,
  title,
  onClick,
  type = 'button',
}: {
  children: ReactNode
  variant?: ButtonVariant
  icon?: LucideIcon
  disabled?: boolean
  title?: string
  onClick?: () => void
  type?: 'button' | 'submit'
}) {
  const styles: Record<ButtonVariant, string> = {
    primary: 'bg-steel text-white hover:bg-steel-dark border-steel',
    secondary: 'bg-white text-ink border-line hover:bg-paper',
    ghost: 'bg-transparent text-steel border-transparent hover:bg-steel-wash',
  }
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex min-h-[38px] items-center gap-2 rounded-md border px-3.5 text-[14px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]}`}
    >
      {Icon && <Icon className="h-4 w-4" aria-hidden />}
      {children}
    </button>
  )
}

export type Tone = 'neutral' | 'steel' | 'amber' | 'ok' | 'alert'

const toneStyles: Record<Tone, string> = {
  neutral: 'bg-paper-deep text-ink-soft',
  steel: 'bg-steel-wash text-steel-dark',
  amber: 'bg-amber-wash text-amber',
  ok: 'bg-ok-wash text-ok',
  alert: 'bg-alert-wash text-alert',
}

export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center whitespace-nowrap rounded px-2 py-0.5 text-[13px] font-medium ${toneStyles[tone]}`}>{children}</span>
}

export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: LucideIcon
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-start gap-3 self-start rounded-lg border border-dashed border-line bg-white px-6 py-8">
      <Icon className="h-6 w-6 text-ink-faint" aria-hidden />
      <div>
        <p className="font-semibold">{title}</p>
        <p className="mt-1 max-w-xl text-ink-soft">{body}</p>
      </div>
      {action}
    </div>
  )
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  className = 'mb-5 border-b',
}: {
  tabs: { id: T; label: string }[]
  value: T
  onChange: (id: T) => void
  label: string
  className?: string
}) {
  return (
    <div className={`flex gap-1 overflow-x-auto overflow-y-hidden border-line ${className}`} role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={value === tab.id}
          onClick={() => onChange(tab.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[14px] ${
            value === tab.id ? 'border-steel font-semibold text-steel-dark' : 'border-transparent text-ink-soft hover:text-ink'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

export function Table({ head, rows, minWidth = 640 }: { head: ReactNode[]; rows: ReactNode[][]; minWidth?: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[14px]" style={{ minWidth }}>
        <thead>
          <tr className="border-b border-line text-[13px] text-ink-faint">
            {head.map((h, i) => (
              <th key={i} className="px-5 py-2.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-line last:border-0 hover:bg-paper/60">
              {row.map((cell, c) => (
                <td key={c} className="px-5 py-3 align-middle">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[14px] font-medium">{label}</span>
      {hint && <span className="mt-0.5 block text-[13px] text-ink-faint">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  )
}

export const inputClass =
  'w-full rounded-md border border-line bg-white px-3 py-2 text-[14px] focus:border-steel focus:outline-none disabled:bg-paper disabled:text-ink-faint'

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto,1fr] gap-x-6 gap-y-2 text-[14px]">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-faint">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

/** 一個數字加一句說明。用在總覽，不做成一排相同的卡片。 */
export function Figure({ value, label, note }: { value: ReactNode; label: string; note?: string }) {
  return (
    <div>
      <p className="text-[28px] font-bold leading-none">{value}</p>
      <p className="mt-1.5 text-[14px] text-ink-soft">{label}</p>
      {note && <p className="text-[13px] text-ink-faint">{note}</p>}
    </div>
  )
}

/** AI 預填或建議的值。醫師確認或修改後改用 state 顯示。 */
export function AiBadge({ state = 'suggested' }: { state?: 'suggested' | 'edited' | 'confirmed' }) {
  const styles = {
    suggested: ['bg-amber-wash text-amber', 'AI 建議'],
    edited: ['bg-steel-wash text-steel-dark', '已修改'],
    confirmed: ['bg-ok-wash text-ok', '已確認'],
  } as const
  const [cls, text] = styles[state]
  return <span className={`inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[12px] font-medium ${cls}`}>{text}</span>
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 rounded-full bg-paper-deep" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-1.5 rounded-full bg-steel" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
      <span className="w-10 text-right text-[12px] text-ink-faint">{Math.round(value)}%</span>
    </div>
  )
}

export interface TimelineEntry {
  title: string
  time: string
  by?: string
  note?: string
  tone?: Tone
}

/** 依時間排列的事件，例如版本歷史、模型階段、工作事件。 */
export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className="space-y-0">
      {entries.map((e, i) => (
        <li key={i} className="grid grid-cols-[16px_1fr] gap-3">
          <span className="flex flex-col items-center">
            <span className={`mt-1.5 h-2.5 w-2.5 rounded-full ${e.tone === 'ok' ? 'bg-ok' : e.tone === 'alert' ? 'bg-alert' : e.tone === 'amber' ? 'bg-amber' : 'bg-steel'}`} />
            {i < entries.length - 1 && <span className="w-px flex-1 bg-line" />}
          </span>
          <span className="pb-4">
            <span className="block text-[14px] font-medium">{e.title}</span>
            <span className="block text-[13px] text-ink-faint">
              {e.time}
              {e.by && `・${e.by}`}
            </span>
            {e.note && <span className="mt-0.5 block text-[13px] text-ink-soft">{e.note}</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** 標示該區塊是示範內容，避免被誤認為真實結果。 */
export function DemoNote({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-amber/30 bg-amber-wash px-3 py-2 text-[13px] text-amber">{children}</p>
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="mb-3 inline-flex items-center gap-1.5 text-[14px] text-steel hover:underline">
      <ArrowLeft className="h-4 w-4" aria-hidden />
      {children}
    </Link>
  )
}
