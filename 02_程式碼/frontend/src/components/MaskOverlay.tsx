import type { Shape } from './AnnotationCanvas'
import { structures } from './AnnotationCanvas'

const colorOf = (s: string) => structures.find((x) => x.id === s)?.color ?? '#fff'

/** 在去識別化影像上疊遮罩形狀（座標為影像原始像素）。 */
export function ImageWithMask({ src, width, height, shapes, opacity = 0.7 }: { src: string; width: number; height: number; shapes?: Shape[]; opacity?: number }) {
  return (
    <div className="relative overflow-hidden rounded-md bg-viewer">
      <img src={src} alt="去識別化超音波影像" className="block h-auto w-full" width={width} height={height} />
      {shapes && shapes.length > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          <g opacity={opacity}>
            {shapes.map((s) =>
              s.kind === 'polygon' ? (
                <polygon key={s.id} points={s.points.map((p) => p.join(',')).join(' ')} fill={colorOf(s.structure)} fillOpacity={0.35} stroke={colorOf(s.structure)} strokeWidth={Math.max(1, width / 400)} />
              ) : (
                <polyline key={s.id} points={s.points.map((p) => p.join(',')).join(' ')} fill="none" stroke={colorOf(s.structure)} strokeOpacity={0.6} strokeWidth={s.width} strokeLinecap="round" strokeLinejoin="round" />
              ),
            )}
          </g>
        </svg>
      )}
    </div>
  )
}
