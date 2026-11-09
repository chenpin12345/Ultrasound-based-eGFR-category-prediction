import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Brush, Check, ChevronLeft, ChevronRight, Eraser, EyeOff, Hexagon, Redo2, Save, Undo2, ZoomIn } from 'lucide-react'
import { api, imageUrl } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { sideLabel } from '../../api/types'
import { BackLink, Button, EmptyState, Panel, Pill, inputClass } from '../../components/ui'
import { AnnotationCanvas, structures, type Shape, type Tool } from '../../components/AnnotationCanvas'
import { GradeScale, type Grade } from '../../components/GradeScale'
import { ErrorNote, Loading } from '../../components/live'
import { useOperator } from '../../auth/operator'
import { PenTool } from 'lucide-react'

type Task = 'mask' | 'grade' | 'side'
const TASK_NAME: Record<Task, string> = { mask: '腎實質、腎竇、肝、脾遮罩', grade: '回音分級 Grade 0–3', side: '側別與切面' }

interface ImageView {
  id: string
  width: number
  height: number
  side: 'right' | 'left' | null
  view: string | null
  machine: string
}
interface QueueItem {
  key: string
  done: boolean
  image?: ImageView
  patient_id?: string
  side?: 'right' | 'left'
  images?: ImageView[]
}

const tools: { id: Tool; label: string; icon: typeof Brush; key: string }[] = [
  { id: 'brush', label: '筆刷', icon: Brush, key: 'B' },
  { id: 'polygon', label: '多邊形', icon: Hexagon, key: 'P' },
  { id: 'eraser', label: '橡皮擦', icon: Eraser, key: 'E' },
]

export default function AnnotationEditor() {
  const { taskId = 'mask' } = useParams()
  const task = (['mask', 'grade', 'side'].includes(taskId) ? taskId : 'mask') as Task
  const [params] = useSearchParams()
  const { operator, physicians } = useOperator()
  const [physician, setPhysician] = useState('')
  const rater = task === 'grade' ? physician : operator

  const queue = useApi<{ items: QueueItem[]; total: number }>(rater || task !== 'grade' ? `/annotation/queue/${task}?rater=${encodeURIComponent(rater)}` : null, [rater])
  const items = useMemo(() => queue.data?.items ?? [], [queue.data])
  const [index, setIndex] = useState(0)
  const [imageIndex, setImageIndex] = useState(0)
  const item = items[index]

  // 初次載入：跳到指定影像，或第一個還沒完成的項目
  const [positioned, setPositioned] = useState(false)
  useEffect(() => {
    if (positioned || !items.length) return
    const target = params.get('image')
    const at = target ? items.findIndex((i) => i.key === target) : items.findIndex((i) => !i.done)
    setIndex(at >= 0 ? at : 0)
    setPositioned(true)
  }, [items, params, positioned])

  // 遮罩編輯狀態
  const [shapes, setShapes] = useState<Shape[]>([])
  const [undone, setUndone] = useState<Shape[]>([])
  const [tool, setTool] = useState<Tool>('polygon')
  const [structure, setStructure] = useState<string>('parenchyma')
  const [opacity, setOpacity] = useState(0.8)
  const [zoom, setZoom] = useState(1)
  const [flags, setFlags] = useState<{ occluded?: boolean; no_reference?: boolean }>({})
  // 分級／側別
  const [grade, setGrade] = useState<Grade | 'unsure' | undefined>()
  const [unsureReason, setUnsureReason] = useState('')
  const [sideValue, setSideValue] = useState<{ side?: string; view?: string; contradiction?: boolean }>({})
  const [saved, setSaved] = useState('')

  const current: ImageView | undefined = task === 'grade' ? item?.images?.[imageIndex] : item?.image
  const brushWidth = Math.max(6, Math.round((current?.width ?? 640) / 60))

  // 載入這個項目已存的標註
  useEffect(() => {
    setShapes([])
    setUndone([])
    setFlags({})
    setGrade(undefined)
    setUnsureReason('')
    setSideValue({})
    setSaved('')
    setImageIndex(0)
    if (!item || (task === 'grade' && !rater)) return
    let alive = true
    api
      .get<{ mask?: { shapes: Shape[]; flags: typeof flags } | null; grade?: { grade: number | null; unsure_reason: string | null } | null; label?: Record<string, unknown> | null }>(
        `/annotation/state/${task}/${encodeURIComponent(item.key)}?rater=${encodeURIComponent(rater)}`,
      )
      .then((s) => {
        if (!alive) return
        if (s.mask) {
          setShapes(s.mask.shapes)
          setFlags(s.mask.flags ?? {})
        }
        if (s.grade) {
          setGrade(s.grade.grade === null ? 'unsure' : (s.grade.grade as Grade))
          setUnsureReason(s.grade.unsure_reason ?? '')
        }
        if (s.label && task === 'side') setSideValue(s.label as typeof sideValue)
        if (!s.label && task === 'side' && item.image) setSideValue({ side: item.image.side ?? undefined, view: item.image.view ?? undefined })
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [item, task, rater])

  const save = useAction(async (status: 'draft' | 'done') => {
    if (!item) return
    if (task === 'mask') return api.put(`/annotation/masks/${item.key}`, { shapes, flags, status })
    if (task === 'grade')
      return api.put('/annotation/grades', {
        patient_id: item.patient_id,
        side: item.side,
        grade: grade === 'unsure' ? null : grade,
        unsure_reason: grade === 'unsure' ? unsureReason : null,
        rater,
        image_id: current?.id,
      })
    return api.put(`/annotation/labels/${item.key}`, { kind: 'side', value: sideValue })
  })

  const ready = task === 'mask' ? shapes.length > 0 : task === 'grade' ? grade !== undefined && (grade !== 'unsure' || unsureReason.trim() !== '') : Boolean(sideValue.side && sideValue.view)
  const go = useCallback((delta: number) => setIndex((i) => Math.min(items.length - 1, Math.max(0, i + delta))), [items.length])

  const finish = async () => {
    const ok = await save.run('done')
    if (ok === undefined) return
    queue.setData((q) => (q ? { ...q, items: q.items.map((x, i) => (i === index ? { ...x, done: true } : x)) } : q))
    setSaved('已儲存')
    go(1)
  }

  const undo = useCallback(() => {
    setShapes((s) => {
      if (!s.length) return s
      setUndone((u) => [...u, s[s.length - 1]])
      return s.slice(0, -1)
    })
  }, [])
  const redo = useCallback(() => {
    setUndone((u) => {
      if (!u.length) return u
      setShapes((s) => [...s, u[u.length - 1]])
      return u.slice(0, -1)
    })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      const k = e.key.toLowerCase()
      if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault()
        if (e.shiftKey) redo()
        else undo()
      } else if ((e.ctrlKey || e.metaKey) && k === 'y') {
        e.preventDefault()
        redo()
      } else if (e.key === 'ArrowRight') go(1)
      else if (e.key === 'ArrowLeft') go(-1)
      else if (task === 'mask' && k === 'b') setTool('brush')
      else if (task === 'mask' && k === 'p') setTool('polygon')
      else if (task === 'mask' && k === 'e') setTool('eraser')
      else if (task === 'mask' && ['1', '2', '3', '4'].includes(k)) setStructure(structures[Number(k) - 1].id)
      else if (task === 'grade' && ['0', '1', '2', '3'].includes(k)) setGrade(Number(k) as Grade)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo, redo, go, task])

  const doneCount = items.filter((i) => i.done).length
  const header = (
    <>
      <BackLink to="/research/annotation">回標註與回饋</BackLink>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold leading-tight">{TASK_NAME[task]}</h1>
          {item && (
            <p className="text-[14px] text-ink-soft">
              第 {index + 1}／{items.length} 項・{task === 'grade' ? `${item.patient_id}・${item.side ? sideLabel[item.side] : ''}腎` : item.key}・
              {rater ? `${rater} 已完成 ${doneCount} 項` : '尚未選擇標註者'}
            </p>
          )}
        </div>
        <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-soft">
          <EyeOff className="h-4 w-4" aria-hidden />
          盲測：不顯示 eGFR、其他分級與 AI 結果
        </span>
      </div>
    </>
  )

  if (task === 'grade' && !physician) {
    return (
      <>
        {header}
        <Panel title="選擇分級的醫師" className="max-w-lg">
          <p className="mb-3 text-[14px] text-ink-soft">回音分級要記錄是哪一位醫師判讀的，每位醫師的分級分開保存，之後用來計算醫師之間的一致性。</p>
          {physicians.length ? (
            <select className={inputClass} value={physician} onChange={(e) => setPhysician(e.target.value)}>
              <option value="">請選擇</option>
              {physicians.map((p) => (
                <option key={p.id}>{p.name}</option>
              ))}
            </select>
          ) : (
            <p className="text-[14px] text-amber">醫師名單是空的，請先到「設定 › 醫師與操作者名單」新增醫師。</p>
          )}
        </Panel>
      </>
    )
  }

  if (queue.loading && !queue.data) return (
    <>
      {header}
      <Loading />
    </>
  )
  if (!items.length || !item || !current)
    return (
      <>
        {header}
        <ErrorNote error={queue.error} />
        <EmptyState icon={PenTool} title="沒有可標註的項目" body={task === 'grade' ? '回音分級需要已對到病人、已知側別的可用影像。' : '還沒有可用的影像。請先匯入並確認影像。'} />
      </>
    )

  return (
    <>
      {header}
      {!rater && <ErrorNote message="請先在右上角選擇操作者，標註才會記錄是誰做的。" />}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Panel flush>
          {task === 'mask' && (
            <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2" role="toolbar" aria-label="繪圖工具">
              {tools.map((t) => {
                const Icon = t.icon
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTool(t.id)}
                    aria-pressed={tool === t.id}
                    title={`${t.label}（${t.key}）`}
                    className={`flex h-9 w-9 items-center justify-center rounded-md border ${tool === t.id ? 'border-steel bg-steel-wash text-steel-dark' : 'border-line text-ink-soft hover:bg-paper'}`}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                    <span className="sr-only">{t.label}</span>
                  </button>
                )
              })}
              <span className="mx-1 h-6 w-px bg-line" />
              <button type="button" onClick={undo} disabled={!shapes.length} title="復原（Ctrl+Z）" className="flex h-9 w-9 items-center justify-center rounded-md border border-line text-ink-soft hover:bg-paper disabled:opacity-40">
                <Undo2 className="h-4 w-4" aria-hidden />
                <span className="sr-only">復原</span>
              </button>
              <button type="button" onClick={redo} disabled={!undone.length} title="重做（Ctrl+Y）" className="flex h-9 w-9 items-center justify-center rounded-md border border-line text-ink-soft hover:bg-paper disabled:opacity-40">
                <Redo2 className="h-4 w-4" aria-hidden />
                <span className="sr-only">重做</span>
              </button>
              <span className="mx-1 h-6 w-px bg-line" />
              <label className="flex items-center gap-1.5 text-[13px] text-ink-soft">
                透明度
                <input type="range" min={0.2} max={1} step={0.1} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} className="w-20 accent-steel" />
              </label>
              <label className="ml-auto flex items-center gap-1.5 text-[13px] text-ink-soft">
                <ZoomIn className="h-4 w-4" aria-hidden />
                <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="rounded border border-line bg-white px-1.5 py-1">
                  <option value={1}>100%</option>
                  <option value={1.5}>150%</option>
                  <option value={2}>200%</option>
                </select>
              </label>
            </div>
          )}
          <div className="p-3">
            {task === 'mask' ? (
              <AnnotationCanvas
                shapes={shapes}
                tool={tool}
                structure={structure}
                opacity={opacity}
                brushWidth={brushWidth}
                zoom={zoom}
                background={{ src: imageUrl(current.id), width: current.width, height: current.height }}
                onAdd={(s) => {
                  setShapes((x) => [...x, { ...s, id: Date.now() }])
                  setUndone([])
                }}
                onErase={(id) => setShapes((x) => x.filter((s) => s.id !== id))}
              />
            ) : (
              <img src={imageUrl(current.id)} alt="去識別化超音波影像" className="block h-auto w-full rounded-md bg-viewer" />
            )}
            {task === 'grade' && item.images && item.images.length > 1 && (
              <div className="mt-3 flex gap-2 overflow-x-auto" aria-label="同一側的其他影像">
                {item.images.map((im, i) => (
                  <button key={im.id} type="button" onClick={() => setImageIndex(i)} className={`w-28 shrink-0 overflow-hidden rounded border ${i === imageIndex ? 'border-steel ring-1 ring-steel' : 'border-line'}`}>
                    <img src={imageUrl(im.id, 'thumb')} alt="" className="block h-16 w-full bg-viewer object-contain" />
                    <span className="block px-1.5 py-0.5 text-left text-[11px] text-ink-soft">{i === 0 ? '最長切面' : `影像 ${i + 1}`}</span>
                  </button>
                ))}
              </div>
            )}
            <p className="mt-2 text-[12px] text-ink-faint">
              {task === 'mask' ? '多邊形：點擊加點，雙擊或 Enter 完成，Esc 取消。橡皮擦：點一下要刪除的形狀。座標以影像原始像素儲存。' : '標註畫面不提供亮度調整，避免影響判斷。'}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2">
            <Button icon={ChevronLeft} onClick={() => go(-1)} disabled={index === 0}>
              上一項
            </Button>
            <div className="flex items-center gap-2">
              {saved && <span className="text-[13px] text-ok">{saved}</span>}
              {task === 'mask' && (
                <Button icon={Save} disabled={!shapes.length || save.busy || !rater} onClick={async () => { await save.run('draft'); setSaved('草稿已儲存') }}>
                  存草稿
                </Button>
              )}
              <Button variant="primary" icon={Check} disabled={!ready || save.busy || !rater} onClick={() => void finish()}>
                完成，下一項
              </Button>
            </div>
            <Button onClick={() => go(1)} disabled={index === items.length - 1}>
              下一項
              <ChevronRight className="h-4 w-4" aria-hidden />
            </Button>
          </div>
          <div className="px-3 pb-3">
            <ErrorNote error={save.error} />
          </div>
        </Panel>

        <div className="space-y-5">
          {task === 'mask' && (
            <Panel title="結構">
              <ul className="space-y-1.5" role="radiogroup" aria-label="選擇結構">
                {structures.map((s) => {
                  const count = shapes.filter((sh) => sh.structure === s.id).length
                  return (
                    <li key={s.id}>
                      <button type="button" role="radio" aria-checked={structure === s.id} onClick={() => setStructure(s.id)} className={`flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left ${structure === s.id ? 'border-steel bg-steel-wash' : 'border-line hover:bg-paper'}`}>
                        <span className="h-3.5 w-3.5 rounded-sm" style={{ background: s.color }} />
                        <span className="flex-1">{s.label}</span>
                        <span className="text-[12px] text-ink-faint">{count ? `${count} 筆` : `按 ${s.key}`}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
              <label className="mt-4 flex items-center gap-2 text-[14px]">
                <input type="checkbox" className="accent-steel" checked={Boolean(flags.occluded)} onChange={(e) => setFlags({ ...flags, occluded: e.target.checked })} />
                部分遮蔽（肋骨或腸氣）
              </label>
              <label className="mt-1.5 flex items-center gap-2 text-[14px]">
                <input type="checkbox" className="accent-steel" checked={Boolean(flags.no_reference)} onChange={(e) => setFlags({ ...flags, no_reference: e.target.checked })} />
                無參考器官
              </label>
            </Panel>
          )}

          {task === 'grade' && item.side && (
            <Panel title={`${sideLabel[item.side]}腎回音分級（與${item.side === 'right' ? '肝臟' : '脾臟'}比較）`}>
              <GradeScale selected={typeof grade === 'number' ? grade : undefined} confirmed onSelect={(g) => setGrade(g)} />
              <button type="button" onClick={() => setGrade('unsure')} className={`mt-3 w-full rounded-md border px-3 py-2 text-left text-[14px] ${grade === 'unsure' ? 'border-ink ring-2 ring-ink' : 'border-line hover:bg-paper'}`}>
                無法判斷
              </button>
              {grade === 'unsure' && (
                <input className={`${inputClass} mt-2`} placeholder="原因，例如：畫面中沒有肝臟" value={unsureReason} onChange={(e) => setUnsureReason(e.target.value)} />
              )}
              <p className="mt-2 text-[12px] text-ink-faint">分級醫師：{physician}・快捷鍵 0–3。</p>
            </Panel>
          )}

          {task === 'side' && (
            <Panel title="側別與切面">
              <div className="space-y-3 text-[14px]">
                <fieldset>
                  <legend className="font-medium">側別</legend>
                  {(['right', 'left'] as const).map((s) => (
                    <label key={s} className="mr-4 inline-flex items-center gap-1.5">
                      <input type="radio" name="side" className="accent-steel" checked={sideValue.side === s} onChange={() => setSideValue({ ...sideValue, side: s })} />
                      {sideLabel[s]}腎
                    </label>
                  ))}
                </fieldset>
                <fieldset>
                  <legend className="font-medium">切面</legend>
                  {(
                    [
                      ['long', '長軸'],
                      ['short', '短軸'],
                      ['oblique', '斜切'],
                    ] as const
                  ).map(([v, l]) => (
                    <label key={v} className="mr-4 inline-flex items-center gap-1.5">
                      <input type="radio" name="view" className="accent-steel" checked={sideValue.view === v} onChange={() => setSideValue({ ...sideValue, view: v })} />
                      {l}
                    </label>
                  ))}
                </fieldset>
                <label className="flex items-center gap-2">
                  <input type="checkbox" className="accent-steel" checked={Boolean(sideValue.contradiction)} onChange={(e) => setSideValue({ ...sideValue, contradiction: e.target.checked })} />
                  文字標示與影像內容矛盾
                </label>
                <p className="text-[12px] text-ink-faint">預設值是 OCR 讀到的側別；儲存後會更新影像資料。</p>
              </div>
            </Panel>
          )}

          <Panel title={`進度（${doneCount}／${items.length}）`}>
            <ol className="grid max-h-64 grid-cols-6 gap-1.5 overflow-y-auto" aria-label="項目清單">
              {items.map((it, i) => (
                <li key={it.key}>
                  <button type="button" onClick={() => setIndex(i)} title={it.key} className={`h-8 w-full rounded text-[12px] ${i === index ? 'bg-steel text-white' : it.done ? 'bg-ok-wash text-ok' : 'bg-paper-deep text-ink-soft'}`}>
                    {i + 1}
                  </button>
                </li>
              ))}
            </ol>
            <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
              <Pill tone="ok">已完成</Pill>
              <Pill>未完成</Pill>
            </div>
            <p className="mt-3 text-[12px] text-ink-faint">←／→ 換項；換項前請先按「完成」或「存草稿」，否則畫的內容不會保存。</p>
          </Panel>
        </div>
      </div>
    </>
  )
}
