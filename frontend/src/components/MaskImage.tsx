import { useEffect, useRef, useState } from 'react'

export function MaskImage({ src, mask, only = false, opacity = .35, alt }: { src?: string; mask: string; only?: boolean; opacity?: number; alt: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let cancelled = false
    setReady(false); setError('')
    const load = (url: string) => new Promise<HTMLImageElement>((resolve, reject) => {
      const im = new Image(); im.onload = () => resolve(im); im.onerror = () => reject(new Error('圖片載入失敗')); im.src = url
    })
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(e => e.isIntersecting)) return
      observer.disconnect()
      void Promise.all([load(mask), !only && src ? load(src) : Promise.resolve(null)]).then(([m, base]) => {
        if (cancelled || !canvas.current) return
        if (!only && !base) throw new Error('尚未產生對應處理圖')
        if (base && (base.naturalWidth !== m.naturalWidth || base.naturalHeight !== m.naturalHeight)) throw new Error('尺寸不一致，無法安全疊圖')
        const c = canvas.current; c.width = m.naturalWidth; c.height = m.naturalHeight
        const ctx = c.getContext('2d'); if (!ctx) throw new Error('瀏覽器無法顯示 Canvas')
        const layer = document.createElement('canvas'); layer.width = c.width; layer.height = c.height
        const lc = layer.getContext('2d')!; lc.drawImage(m, 0, 0)
        const data = lc.getImageData(0, 0, c.width, c.height)
        const color = only ? [45, 212, 191] : [251, 191, 36]
        for (let i = 0; i < data.data.length; i += 4) {
          const visible = data.data[i] > 127 && data.data[i+3] > 0
          data.data[i] = color[0]; data.data[i+1] = color[1]; data.data[i+2] = color[2]; data.data[i+3] = visible ? 255 : 0
        }
        lc.putImageData(data, 0, 0)
        ctx.fillStyle = '#101E30'; ctx.fillRect(0, 0, c.width, c.height)
        if (base) ctx.drawImage(base, 0, 0)
        ctx.globalAlpha = only ? 1 : opacity; ctx.drawImage(layer, 0, 0); ctx.globalAlpha = 1
        setReady(true)
      }).catch(reason => { if (!cancelled) setError(String(reason.message || reason)) })
    }, { rootMargin: '150px' })
    if (canvas.current) observer.observe(canvas.current)
    return () => { cancelled = true; observer.disconnect() }
  }, [src, mask, only, opacity])
  return <div className="relative flex h-full w-full items-center justify-center bg-[#101E30]">
    <canvas ref={canvas} role="img" aria-label={alt} className={`max-h-full max-w-full object-contain ${ready ? '' : 'invisible'}`} />
    {!ready && <p className="absolute inset-0 flex items-center justify-center p-3 text-center text-xs text-white" role="status">{error || '載入影像…'}</p>}
  </div>
}
