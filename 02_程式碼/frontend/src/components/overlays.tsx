import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button, inputClass } from './ui'

function useEscape(onClose: () => void, active: boolean) {
  useEffect(() => {
    if (!active) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, active])
}

/**
 * 確認對話框。requireText 要求輸入指定文字才能確認（例如簽核時輸入醫師姓名、永久刪除時輸入「永久刪除」）。
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  danger = false,
  requireText,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  danger?: boolean
  requireText?: string
  onConfirm: () => void
  onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const firstField = useRef<HTMLInputElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useEscape(onClose, open)

  useEffect(() => {
    if (!open) return
    setTyped('')
    const t = setTimeout(() => (firstField.current ?? closeRef.current)?.focus(), 0)
    return () => clearTimeout(t)
  }, [open])

  if (!open) return null
  const ready = !requireText || typed.trim() === requireText

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-ink/40" aria-label="關閉" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="relative w-full max-w-md rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3">
          <h2 id={titleId} className="text-[17px] font-semibold">
            {title}
          </h2>
          <button ref={closeRef} onClick={onClose} className="rounded p-1 text-ink-soft hover:bg-paper" aria-label="關閉">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          className="space-y-4 px-5 py-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (ready) onConfirm()
          }}
        >
          <div className="text-[14px] text-ink-soft">{children}</div>
          {requireText && (
            <label className="block">
              <span className="text-[14px] font-medium">輸入「{requireText}」以確認</span>
              <input
                ref={firstField}
                className={`${inputClass} mt-1.5`}
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            </label>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button onClick={onClose}>取消</Button>
            <button
              type="submit"
              disabled={!ready}
              className={`inline-flex min-h-[38px] items-center rounded-md border px-3.5 text-[14px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 ${
                danger ? 'border-alert bg-alert hover:bg-alert/90' : 'border-steel bg-steel hover:bg-steel-dark'
              }`}
            >
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function Drawer({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useEscape(onClose, open)
  useEffect(() => {
    if (open) closeRef.current?.focus()
  }, [open])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50">
      <button className="absolute inset-0 bg-ink/30" aria-label="關閉" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="absolute inset-y-0 right-0 flex w-[min(92vw,440px)] flex-col border-l border-line bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 id={titleId} className="text-[17px] font-semibold">
            {title}
          </h2>
          <button ref={closeRef} onClick={onClose} className="rounded p-1 text-ink-soft hover:bg-paper" aria-label="關閉">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>
  )
}
