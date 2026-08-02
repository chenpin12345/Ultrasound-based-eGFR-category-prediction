import { Maximize2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { formatBytes } from '../lib/format'

interface PreviewItem { name: string; url: string; detail?: string; badge?: string }

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
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelected(null) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [])
  if (!items.length) return null
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {items.map((item) => (
          <button key={`${item.name}-${item.url}`} type="button" className="group overflow-hidden rounded-xl border border-slate-200 bg-white text-left" onClick={() => setSelected(item)}>
            <div className="relative aspect-square overflow-hidden bg-slate-100">
              <img src={item.url} alt={item.name} className="h-full w-full object-cover transition duration-300 group-hover:scale-105" />
              <span className="absolute right-2 top-2 rounded-lg bg-slate-950/70 p-1.5 text-white opacity-0 transition group-hover:opacity-100"><Maximize2 className="h-3.5 w-3.5" /></span>
              {item.badge && <span className="absolute bottom-2 left-2 rounded-md bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-slate-700">{item.badge}</span>}
            </div>
            <div className="p-2"><p className="truncate text-xs font-medium text-slate-700">{item.name}</p>{item.detail && <p className="mt-0.5 text-[11px] text-slate-400">{item.detail}</p>}</div>
          </button>
        ))}
      </div>
      {selected && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/80 p-4" role="dialog" aria-modal="true" aria-label={`預覽 ${selected.name}`} onClick={() => setSelected(null)}>
          <button className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20" aria-label="關閉預覽" onClick={() => setSelected(null)}><X className="h-6 w-6" /></button>
          <div className="max-h-full max-w-5xl" onClick={(event) => event.stopPropagation()}>
            <img src={selected.url} alt={selected.name} className="max-h-[82vh] max-w-full rounded-xl object-contain shadow-2xl" />
            <p className="mt-3 text-center text-sm font-medium text-white">{selected.name}</p>
          </div>
        </div>
      )}
    </>
  )
}
