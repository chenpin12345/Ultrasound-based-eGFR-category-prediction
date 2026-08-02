import { AlertCircle, CheckCircle2, Inbox, LoaderCircle, RefreshCw } from 'lucide-react'
import type { HTMLAttributes, ReactNode } from 'react'
import { statusLabel } from '../lib/format'

export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-2xl border border-slate-200/80 bg-white shadow-panel ${className}`} {...props} />
}

export function PageHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-clinical-600">ISU AI Research Workspace</p>
        <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

const statusClasses: Record<string, string> = {
  queued: 'bg-amber-50 text-amber-700 ring-amber-200', pending: 'bg-slate-100 text-slate-700 ring-slate-200',
  running: 'bg-sky-50 text-sky-700 ring-sky-200', stopping: 'bg-orange-50 text-orange-700 ring-orange-200',
  stopped: 'bg-slate-100 text-slate-700 ring-slate-200', completed: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  ready: 'bg-emerald-50 text-emerald-700 ring-emerald-200', active: 'bg-clinical-50 text-clinical-700 ring-clinical-200',
  failed: 'bg-rose-50 text-rose-700 ring-rose-200', interrupted: 'bg-violet-50 text-violet-700 ring-violet-200',
  cancelled: 'bg-slate-100 text-slate-600 ring-slate-200', training: 'bg-sky-50 text-sky-700 ring-sky-200',
}

export function StatusBadge({ status }: { status?: string }) {
  const normalized = status || 'unknown'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${statusClasses[normalized] || 'bg-slate-100 text-slate-600 ring-slate-200'}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${normalized === 'running' || normalized === 'training' ? 'animate-pulse bg-current' : 'bg-current'}`} />
      {statusLabel(normalized)}
    </span>
  )
}

export function ProgressBar({ value, label, detail }: { value: number; label?: string; detail?: string }) {
  const safe = Math.max(0, Math.min(100, value))
  return (
    <div>
      {(label || detail) && <div className="mb-1.5 flex justify-between gap-3 text-xs text-slate-600"><span>{label}</span><span>{detail || `${safe.toFixed(0)}%`}</span></div>}
      <div className="h-2.5 overflow-hidden rounded-full bg-slate-100" aria-label={label || '進度'} aria-valuenow={safe} role="progressbar">
        <div className="h-full rounded-full bg-gradient-to-r from-clinical-500 to-cyan-500 transition-[width] duration-500" style={{ width: `${safe}%` }} />
      </div>
    </div>
  )
}

export function StatePanel({
  loading, error, empty, emptyTitle = '目前沒有資料', emptyDescription, onRetry, children,
}: {
  loading?: boolean
  error?: string | null
  empty?: boolean
  emptyTitle?: string
  emptyDescription?: string
  onRetry?: () => void
  children: ReactNode
}) {
  if (loading) {
    return (
      <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-8 text-sm text-slate-600">
        <LoaderCircle className="h-7 w-7 animate-spin text-clinical-600" />
        正在載入資料…
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-8 text-center">
        <AlertCircle className="h-8 w-8 text-rose-600" />
        <div><p className="font-semibold text-rose-900">無法取得資料</p><p className="mt-1 text-sm text-rose-700">{error}</p></div>
        {onRetry && <button className="btn-secondary" onClick={onRetry}><RefreshCw className="h-4 w-4" />重新載入</button>}
      </div>
    )
  }
  if (empty) {
    return (
      <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-8 text-center">
        <Inbox className="h-9 w-9 text-slate-400" />
        <div><p className="font-semibold text-slate-800">{emptyTitle}</p>{emptyDescription && <p className="mt-1 max-w-lg text-sm text-slate-500">{emptyDescription}</p>}</div>
      </div>
    )
  }
  return <>{children}</>
}

export function StatCard({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: string; icon?: ReactNode }) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div><p className="text-sm font-medium text-slate-500">{label}</p><p className="mt-2 text-2xl font-bold tracking-tight text-ink">{value}</p>{hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}</div>
        {icon && <div className="rounded-xl bg-clinical-50 p-2.5 text-clinical-700">{icon}</div>}
      </div>
    </Card>
  )
}

export function InlineNotice({ tone = 'info', title, children }: { tone?: 'info' | 'warning' | 'success' | 'danger'; title?: string; children: ReactNode }) {
  const styles = {
    info: 'border-sky-200 bg-sky-50 text-sky-800', warning: 'border-amber-200 bg-amber-50 text-amber-900',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800', danger: 'border-rose-200 bg-rose-50 text-rose-800',
  }
  return <div className={`rounded-xl border px-4 py-3 text-sm leading-6 ${styles[tone]}`}>{title && <p className="font-semibold">{title}</p>}<div>{children}</div></div>
}

export function SuccessMessage({ children }: { children: ReactNode }) {
  return <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{children}</div>
}
