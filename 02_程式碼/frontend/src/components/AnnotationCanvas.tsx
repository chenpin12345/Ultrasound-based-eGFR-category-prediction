import { useRef, useState, type PointerEvent } from 'react'
import { UltrasoundSketch } from './UltrasoundSketch'

export type Tool = 'brush' | 'polygon' | 'eraser'
export type Point = [number, number]

export interface Shape {
  id: number
  structure: string
  kind: 'stroke' | 'polygon'
  points: Point[]
  width: number
}

export const structures = [
  { id: 'parenchyma', label: '腎實質', value: 1, color: '#5EC4D6', key: '1' },
  { id: 'sinus', label: '腎竇', value: 2, color: '#C792EA', key: '2' },
  { id: 'liver', label: '肝', value: 3, color: '#E0B455', key: '3' },
  { id: 'spleen', label: '脾', value: 4, color: '#9CCB6B', key: '4' },
] as const

const colorOf = (structure: string) => structures.find((s) => s.id === structure)?.color ?? '#fff'
const toPath = (pts: Point[]) => pts.map((p) => p.join(',')).join(' ')

/**
 * 標註畫布：底圖是示意圖，上面疊一層 SVG 讓使用者畫遮罩。
 * 形狀與復原紀錄由父元件管理，這裡只負責繪製與指標事件。
 */
export function AnnotationCanvas({
  shapes,
  tool,
  structure,
  opacity,
  brushWidth,
  zoom,
  onAdd,
  onErase,
  background,
}: {
  shapes: Shape[]
  tool: Tool
  structure: string
  opacity: number
  brushWidth: number
  zoom: number
  onAdd: (shape: Omit<Shape, 'id'>) => void
  onErase: (id: number) => void
  /** 去識別化影像；座標系統就是影像原始像素。沒有時用示意圖（640×460）。 */
  background?: { src: string; width: number; height: number }
}) {
  const vw = background?.width ?? 640
  const vh = background?.height ?? 460
  const svgRef = useRef<SVGSVGElement>(null)
  const [draft, setDraft] = useState<Point[]>([])
  const drawing = useRef(false)

  const toLocal = (e: PointerEvent<SVGSVGElement>): Point => {
    const svg = svgRef.current!
    const pt = svg.createSVGPoint()
    pt.x = e.clientX
    pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse())
    return [Math.round(p.x), Math.round(p.y)]
  }

  const closePolygon = () => {
    if (draft.length >= 3) onAdd({ structure, kind: 'polygon', points: draft, width: 2 })
    setDraft([])
  }

  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    if (tool === 'brush') {
      drawing.current = true
      e.currentTarget.setPointerCapture(e.pointerId)
      setDraft([toLocal(e)])
    } else if (tool === 'polygon') {
      if (e.detail >= 2) closePolygon()
      else setDraft((d) => [...d, toLocal(e)])
    }
  }

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    if (tool === 'brush' && drawing.current) setDraft((d) => [...d, toLocal(e)])
  }

  const onPointerUp = () => {
    if (tool === 'brush' && drawing.current) {
      drawing.current = false
      if (draft.length > 1) onAdd({ structure, kind: 'stroke', points: draft, width: brushWidth })
      setDraft([])
    }
  }

  return (
    <div className="overflow-auto rounded-md bg-viewer" style={{ maxHeight: 560 }}>
      <div className="relative origin-top-left" style={{ width: `${zoom * 100}%` }}>
        {background ? (
          <img src={background.src} alt="去識別化超音波影像" className="block h-auto w-full select-none" draggable={false} width={vw} height={vh} />
        ) : (
          <UltrasoundSketch overlays={{ kidney: false, sinus: false, reference: false }} caption={false} />
        )}
        <svg
          ref={svgRef}
          viewBox={`0 0 ${vw} ${vh}`}
          className={`absolute inset-0 h-full w-full touch-none ${tool === 'eraser' ? 'cursor-pointer' : 'cursor-crosshair'}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onKeyDown={(e) => {
            if (e.key === 'Enter') closePolygon()
            if (e.key === 'Escape') setDraft([])
          }}
          tabIndex={0}
          role="application"
          aria-label="標註畫布。多邊形：點擊加點、雙擊或 Enter 完成、Esc 取消。"
        >
          <g opacity={opacity}>
            {shapes.map((s) =>
              s.kind === 'polygon' ? (
                <polygon
                  key={s.id}
                  points={toPath(s.points)}
                  fill={colorOf(s.structure)}
                  fillOpacity={0.45}
                  stroke={colorOf(s.structure)}
                  strokeWidth={Math.max(2, vw / 320)}
                  onPointerDown={(e) => {
                    if (tool === 'eraser') {
                      e.stopPropagation()
                      onErase(s.id)
                    }
                  }}
                />
              ) : (
                <polyline
                  key={s.id}
                  points={toPath(s.points)}
                  fill="none"
                  stroke={colorOf(s.structure)}
                  strokeOpacity={0.7}
                  strokeWidth={s.width}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  onPointerDown={(e) => {
                    if (tool === 'eraser') {
                      e.stopPropagation()
                      onErase(s.id)
                    }
                  }}
                />
              ),
            )}
          </g>
          {draft.length > 0 &&
            (tool === 'brush' ? (
              <polyline points={toPath(draft)} fill="none" stroke={colorOf(structure)} strokeOpacity={0.7} strokeWidth={brushWidth} strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <g>
                <polyline points={toPath(draft)} fill="none" stroke={colorOf(structure)} strokeWidth={Math.max(2, vw / 320)} strokeDasharray={`${vw / 100} ${vw / 160}`} />
                {draft.map(([x, y], i) => (
                  <circle key={i} cx={x} cy={y} r={Math.max(4, vw / 160)} fill={colorOf(structure)} />
                ))}
              </g>
            ))}
        </svg>
      </div>
    </div>
  )
}
