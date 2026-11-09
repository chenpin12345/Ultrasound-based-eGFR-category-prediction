import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { imageUrl, type ImageDetail, type Point, type Shape, type Structure } from '../api'

export type Tool = 'trace' | 'polygon' | 'adjust' | 'erase'

const area = (pts: Point[]) => Math.abs(pts.reduce((sum, [x, y], i) => {
  const [nx, ny] = pts[(i + 1) % pts.length]
  return sum + x * ny - nx * y
}, 0)) / 2

/** Douglas-Peucker：減少描邊的點，之後才好用「調整」拖曳。 */
function simplify(pts: Point[], tolerance: number): Point[] {
  if (pts.length < 3) return pts
  const [ax, ay] = pts[0]
  const [bx, by] = pts[pts.length - 1]
  const length = Math.hypot(bx - ax, by - ay) || 1
  let worst = 0
  let index = 0
  for (let i = 1; i < pts.length - 1; i++) {
    const [x, y] = pts[i]
    const distance = Math.abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / length
    if (distance > worst) {
      worst = distance
      index = i
    }
  }
  if (worst <= tolerance) return [pts[0], pts[pts.length - 1]]
  return [...simplify(pts.slice(0, index + 1), tolerance).slice(0, -1), ...simplify(pts.slice(index), tolerance)]
}

/** 影像與圈選層。座標都是影像原始像素；放大時改變實際尺寸，線寬才能維持固定。 */
export function Canvas({ image, shapes, structures, active, tool, showShapes, brightness, contrast, onChange }: {
  image: ImageDetail
  shapes: Shape[]
  structures: Structure[]
  active: string
  tool: Tool
  showShapes: boolean
  brightness: number
  contrast: number
  onChange: (shapes: Shape[]) => void
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 })
  const [draft, setDraftState] = useState<Point[]>([])
  const draftRef = useRef<Point[]>([])
  const setDraft = useCallback((next: Point[]) => {
    draftRef.current = next
    setDraftState(next)
  }, [])
  const [panKey, setPanKey] = useState(false)
  const tracing = useRef(false)
  const panning = useRef<{ x: number; y: number } | null>(null)
  const dragging = useRef<{ shape: number; point: number } | null>(null)
  const lastVertexDown = useRef({ shape: 0, point: -1, time: 0 })
  const [dragShapes, setDragShapes] = useState<Shape[] | null>(null)
  const fitScale = useRef(1)

  const fit = useCallback(() => {
    const box = boxRef.current
    if (!box) return
    const scale = Math.min(box.clientWidth / image.width, box.clientHeight / image.height)
    fitScale.current = scale
    setView({ scale, x: (box.clientWidth - image.width * scale) / 2, y: (box.clientHeight - image.height * scale) / 2 })
  }, [image.width, image.height])

  useEffect(() => {
    fit()
    setDraft([])
    const observer = new ResizeObserver(fit)
    if (boxRef.current) observer.observe(boxRef.current)
    return () => observer.disconnect()
  }, [fit, image.id])

  useEffect(() => setDraft([]), [tool, active, setDraft])

  const closeDraft = useCallback(() => {
    const points = draftRef.current
    setDraft([])
    if (points.length >= 3) onChange([...shapes, { id: Date.now(), structure: active, points }])
  }, [active, onChange, setDraft, shapes])

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest('input, textarea, select')
      if (e.code === 'Space' && !typing) {
        e.preventDefault()
        setPanKey(true)
      }
      if (typing) return
      if (draft.length > 0 && e.key === 'Enter') {
        e.preventDefault()
        e.stopImmediatePropagation()
        closeDraft()
      }
      if (e.key === 'Escape') setDraft([])
      if (e.key === 'Backspace' && draft.length > 0) setDraft(draftRef.current.slice(0, -1))
      if (e.key === '0') fit()
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space') setPanKey(false)
    }
    window.addEventListener('keydown', down, true)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down, true)
      window.removeEventListener('keyup', up)
    }
  }, [closeDraft, draft.length, fit, setDraft])

  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = box.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      setView((v) => {
        const scale = Math.min(fitScale.current * 12, Math.max(fitScale.current, v.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)))
        const ratio = scale / v.scale
        return { scale, x: mx - (mx - v.x) * ratio, y: my - (my - v.y) * ratio }
      })
    }
    box.addEventListener('wheel', wheel, { passive: false })
    return () => box.removeEventListener('wheel', wheel)
  }, [])

  const toImage = (e: { clientX: number; clientY: number }): Point => {
    const rect = svgRef.current!.getBoundingClientRect()
    const x = (e.clientX - rect.left) / view.scale
    const y = (e.clientY - rect.top) / view.scale
    return [Math.round(Math.min(Math.max(x, 0), image.width) * 10) / 10, Math.round(Math.min(Math.max(y, 0), image.height) * 10) / 10]
  }

  const down = (e: ReactPointerEvent) => {
    if (panKey || e.button === 1) {
      panning.current = { x: e.clientX - view.x, y: e.clientY - view.y }
      boxRef.current?.setPointerCapture(e.pointerId)
      return
    }
    if (e.button !== 0) return
    if (tool === 'trace') {
      tracing.current = true
      boxRef.current?.setPointerCapture(e.pointerId)
      setDraft([toImage(e)])
    } else if (tool === 'polygon') {
      // 指標事件不帶點擊次數，雙擊封閉交給 onDoubleClick；雙擊的第二下落在同一點，不重複加點
      const point = toImage(e)
      const current = draftRef.current
      const first = current[0]
      const last = current[current.length - 1]
      if (first && current.length >= 3 && Math.hypot(point[0] - first[0], point[1] - first[1]) * view.scale < 10) closeDraft()
      else if (!last || Math.hypot(point[0] - last[0], point[1] - last[1]) * view.scale >= 4) setDraft([...current, point])
    }
  }

  const move = (e: ReactPointerEvent) => {
    if (panning.current) {
      const { x, y } = panning.current
      setView((v) => ({ ...v, x: e.clientX - x, y: e.clientY - y }))
    } else if (tracing.current) {
      const point = toImage(e)
      const current = draftRef.current
      const last = current[current.length - 1]
      if (!last || Math.hypot(point[0] - last[0], point[1] - last[1]) * view.scale >= 2) setDraft([...current, point])
    } else if (dragging.current) {
      const { shape, point } = dragging.current
      const position = toImage(e)
      setDragShapes((current) => (current ?? shapes).map((s) => (s.id === shape ? { ...s, points: s.points.map((p, i) => (i === point ? position : p)) } : s)))
    }
  }

  const up = () => {
    panning.current = null
    if (tracing.current) {
      tracing.current = false
      const points = simplify(draftRef.current, Math.max(0.6, 1 / view.scale))
      setDraft([])
      if (points.length >= 3 && area(points) >= 4) onChange([...shapes, { id: Date.now(), structure: active, points }])
    }
    if (dragging.current) {
      dragging.current = null
      if (dragShapes) onChange(dragShapes)
      setDragShapes(null)
    }
  }

  const removeVertex = (shape: Shape, index: number) => {
    if (shape.points.length > 3) onChange(shapes.map((s) => (s.id === shape.id ? { ...s, points: s.points.filter((_, i) => i !== index) } : s)))
  }

  const insertVertex = (shape: Shape, index: number, e: { clientX: number; clientY: number }) => {
    const point = toImage(e)
    onChange(shapes.map((s) => (s.id === shape.id ? { ...s, points: [...s.points.slice(0, index + 1), point, ...s.points.slice(index + 1)] } : s)))
  }

  const style = (code: string) => structures.find((s) => s.code === code)
  const shown = [...(dragShapes ?? shapes)].sort((a, b) => area(b.points) - area(a.points))  // 小的在上層，才點得到
  const activeStyle = style(active)
  const handle = 5 / Math.max(view.scale, 0.01)
  const cursor = panKey ? 'grab' : tool === 'erase' || tool === 'adjust' ? 'default' : 'crosshair'

  return (
    <div
      ref={boxRef}
      className="relative h-full w-full touch-none select-none overflow-hidden bg-black"
      style={{ cursor }}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onContextMenu={(e) => e.preventDefault()}
      onDoubleClick={() => tool === 'polygon' && !panKey && closeDraft()}
      role="application"
      aria-label="圈選畫布"
    >
      <div className="absolute left-0 top-0" style={{ transform: `translate(${view.x}px, ${view.y}px)`, width: image.width * view.scale, height: image.height * view.scale }}>
        <img
          src={imageUrl(image.id)}
          alt={`超音波影像 ${image.id}`}
          draggable={false}
          className="block h-full w-full"
          style={{ filter: `brightness(${brightness}%) contrast(${contrast}%)`, imageRendering: view.scale > 2 * fitScale.current ? 'pixelated' : 'auto' }}
        />
        <svg ref={svgRef} viewBox={`0 0 ${image.width} ${image.height}`} className="absolute inset-0 h-full w-full" aria-hidden>
          {showShapes && shown.map((shape) => {
            const item = style(shape.structure)
            const color = item?.color ?? '#FFFFFF'
            const selected = shape.structure === active
            return (
              <g key={shape.id}>
                <polygon
                  points={shape.points.map((p) => p.join(',')).join(' ')}
                  fill={color}
                  fillRule="evenodd"
                  fillOpacity={selected ? 0.16 : 0.08}
                  stroke={color}
                  strokeWidth={selected ? 2.5 : 1.75}
                  strokeDasharray={item?.line === 'dashed' ? '7 5' : undefined}
                  vectorEffect="non-scaling-stroke"
                  style={{ cursor: tool === 'erase' ? 'pointer' : undefined, pointerEvents: tool === 'erase' ? 'all' : 'none' }}
                  onPointerDown={(e) => {
                    if (tool === 'erase' && e.button === 0 && !panKey) {
                      e.stopPropagation()
                      onChange(shapes.filter((s) => s.id !== shape.id))
                    }
                  }}
                />
                {tool === 'adjust' && selected && shape.points.map((point, i) => {
                  const next = shape.points[(i + 1) % shape.points.length]
                  return (
                    <line
                      key={`edge-${i}`}
                      x1={point[0]} y1={point[1]} x2={next[0]} y2={next[1]}
                      stroke="transparent"
                      strokeWidth={12}
                      vectorEffect="non-scaling-stroke"
                      style={{ cursor: 'copy', pointerEvents: 'stroke' }}
                      onDoubleClick={(e) => insertVertex(shape, i, e)}
                    />
                  )
                })}
                {tool === 'adjust' && selected && shape.points.map(([x, y], i) => (
                  <circle
                    key={`point-${i}`}
                    cx={x} cy={y} r={handle}
                    fill={color}
                    stroke="#000"
                    strokeWidth={1}
                    vectorEffect="non-scaling-stroke"
                    style={{ cursor: 'move', pointerEvents: 'all' }}
                    onPointerDown={(e) => {
                      if (e.button !== 0 || panKey) return
                      e.stopPropagation()
                      // 拖曳會鎖定指標，瀏覽器的 dblclick 送不到圓點，所以自己判斷雙擊
                      const last = lastVertexDown.current
                      lastVertexDown.current = { shape: shape.id, point: i, time: e.timeStamp }
                      if (last.shape === shape.id && last.point === i && e.timeStamp - last.time < 400) {
                        lastVertexDown.current = { shape: 0, point: -1, time: 0 }
                        removeVertex(shape, i)
                        return
                      }
                      dragging.current = { shape: shape.id, point: i }
                      boxRef.current?.setPointerCapture(e.pointerId)
                    }}
                  />
                ))}
              </g>
            )
          })}
          {draft.length > 0 && (
            <g>
              <polyline
                points={draft.map((p) => p.join(',')).join(' ')}
                fill="none"
                stroke={activeStyle?.color ?? '#fff'}
                strokeWidth={2.5}
                vectorEffect="non-scaling-stroke"
              />
              {tool === 'polygon' && draft.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={handle * (i === 0 ? 1.4 : 1)} fill={activeStyle?.color ?? '#fff'} />)}
            </g>
          )}
        </svg>
      </div>
    </div>
  )
}
