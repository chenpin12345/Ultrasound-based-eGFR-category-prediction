import { AlertTriangle, X } from 'lucide-react'
import { useEffect } from 'react'

export function ConfirmDialog({
  open, title, description, confirmLabel = '確認刪除', busy = false, onConfirm, onCancel,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  useEffect(() => {
    if (!open) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) onCancel() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [busy, onCancel, open])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/60 p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="flex items-start gap-4"><div className="rounded-xl bg-rose-50 p-3 text-rose-600"><AlertTriangle className="h-6 w-6" /></div><div className="min-w-0 flex-1"><h2 id="confirm-title" className="text-lg font-bold text-slate-900">{title}</h2><p className="mt-2 text-sm leading-6 text-slate-600">{description}</p></div><button className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" onClick={onCancel} disabled={busy} aria-label="關閉"><X className="h-5 w-5" /></button></div>
        <div className="mt-6 flex justify-end gap-2"><button className="btn-secondary" disabled={busy} onClick={onCancel}>取消</button><button className="btn-danger" disabled={busy} onClick={onConfirm}>{busy ? '處理中…' : confirmLabel}</button></div>
      </div>
    </div>
  )
}
