import { Maximize2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { formatBytes } from '../lib/format'
import { MaskImage } from './MaskImage'

export interface PreviewItem { id?: string; name: string; url: string; thumbnailUrl?: string; detail?: string; badge?: string; maskUrl?: string; maskOnly?: boolean; unavailable?: string; featureValues?: Record<string, number | null> }

export function FilePreviewGallery({ files }: { files: File[] }) {
  const [items, setItems] = useState<PreviewItem[]>([])
  useEffect(() => {
    const next = files.filter((file) => file.type.startsWith('image/') || /\.(jpe?g|png|jfif|webp|bmp)$/i.test(file.name)).map((file) => ({ name: file.name, url: URL.createObjectURL(file), detail: formatBytes(file.size) }))
    setItems(next)
    return () => next.forEach((item) => URL.revokeObjectURL(item.url))
  }, [files])
  return <PreviewGallery items={items} />
}

export function PreviewGallery({ items }: { items: PreviewItem[] }) {
  const [selected, setSelected] = useState<PreviewItem | null>(null)
  const [opacity, setOpacity] = useState(.35)
  const dialog = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!selected) return
    const previous = document.activeElement as HTMLElement | null
    const button = dialog.current?.querySelector<HTMLButtonElement>('button'); button?.focus()
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelected(null) }
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const controls = dialog.current?.querySelectorAll<HTMLElement>('button, input, a[href], select')
      if (!controls?.length) return
      const first = controls[0], last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', close)
    window.addEventListener('keydown', trap)
    return () => { window.removeEventListener('keydown', close); window.removeEventListener('keydown', trap); previous?.focus() }
  }, [selected])
  useEffect(() => setSelected(null), [items])
  const visual = (item: PreviewItem, full = false) => item.unavailable
    ? <p className="flex h-full items-center justify-center p-3 text-center text-xs text-slate-300">{item.unavailable}</p>
    : item.maskUrl ? <MaskImage src={item.url} mask={item.maskUrl} only={item.maskOnly} opacity={opacity} alt={`${item.name} · ${item.badge || '影像'}`} />
      : <img src={!full && item.thumbnailUrl ? item.thumbnailUrl : item.url} alt={item.name} loading="lazy" className="h-full w-full object-contain" onError={event => { event.currentTarget.alt = `無法載入：${item.name}` }} />
  if (!items.length) return null
  return (
    <>
      {items.some(item => item.maskUrl && !item.maskOnly) && <label className="mb-3 flex items-center gap-3 text-sm text-slate-600">Mask 疊圖透明度 <input aria-label="Mask 疊圖透明度" type="range" min="0" max="70" value={Math.round(opacity * 100)} onChange={event => setOpacity(Number(event.target.value) / 100)} />{Math.round(opacity * 100)}%</label>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-8">
        {items.map((item) => (
          <button key={item.id || `${item.name}-${item.url}`} type="button" className="group overflow-hidden rounded-xl border border-slate-200 bg-white text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-clinical-600" onClick={() => setSelected(item)}>
            <div className="relative aspect-square overflow-hidden bg-[#101E30]">
              {visual(item)}
              <span className="absolute right-2 top-2 rounded-lg bg-slate-950/70 p-1.5 text-white opacity-0 transition group-hover:opacity-100"><Maximize2 className="h-3.5 w-3.5" /></span>
              {item.badge && <span className="absolute bottom-2 left-2 rounded-md bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-slate-700">{item.badge}</span>}
            </div>
            <div className="p-2"><p className="truncate text-xs font-medium text-slate-700" title={item.name}>{item.name}</p>{item.detail && <p className="mt-0.5 text-xs text-slate-500">{item.detail}</p>}{item.featureValues && <div className="mt-1 space-y-0.5 text-xs text-slate-600">{Object.entries(item.featureValues).map(([name, value]) => <p key={name}>{name}: {value == null ? '未提供' : value.toFixed(name === 'Length_px' ? 2 : 4)}</p>)}</div>}</div>
          </button>
        ))}
      </div>
      {selected && (
        <div ref={dialog} className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/80 p-4" role="dialog" aria-modal="true" aria-label={`預覽 ${selected.name}`} onClick={() => setSelected(null)}>
          <button className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20" aria-label="關閉預覽" onClick={() => setSelected(null)}><X className="h-6 w-6" /></button>
          <div className="w-full max-w-5xl" onClick={(event) => event.stopPropagation()}>
            <div className="h-[72vh] overflow-hidden rounded-xl">{visual(selected, true)}</div>
            <p className="mt-3 text-center text-sm font-medium text-white">{selected.name}</p>
            {selected.featureValues && <div className="mt-2 flex flex-wrap justify-center gap-4 text-sm text-white">{Object.entries(selected.featureValues).map(([name, value]) => <span key={name}>{name}: {value == null ? '未提供' : value.toFixed(name === 'Length_px' ? 2 : 4)}</span>)}</div>}
          </div>
        </div>
      )}
    </>
  )
}
