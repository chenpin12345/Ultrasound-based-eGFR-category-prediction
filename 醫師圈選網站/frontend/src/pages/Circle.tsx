import { ArrowLeft, Check, ChevronLeft, ChevronRight, Eraser, Eye, EyeOff, Hand, Maximize, PenLine, Redo2, Spline, Undo2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, SIDE_LABEL, STATUS_LABEL, type CompleteResult, type ImageDetail, type Shape, type Side, type Structure } from '../api'
import { Canvas, type Tool } from '../components/Canvas'

const CORE = ['kidney', 'sinus', 'liver', 'spleen']
const GRADES = [
  { value: 0, label: '0', hint: '皮質比參考器官黑' },
  { value: 1, label: '1', hint: '皮質與參考器官相近' },
  { value: 2, label: '2', hint: '皮質比參考器官白' },
  { value: 3, label: '3', hint: '皮質明顯變白，接近腎竇' },
]
const TOOLS: { id: Tool; label: string; key: string; icon: ReactNode; hint: string }[] = [
  { id: 'trace', label: '描邊', key: 'T', icon: <PenLine size={16} />, hint: '按住畫一圈，放開自動封閉' },
  { id: 'polygon', label: '點選', key: 'P', icon: <Spline size={16} />, hint: '逐點點選，雙擊或按 Enter 封閉，Esc 取消' },
  { id: 'adjust', label: '調整', key: 'A', icon: <Hand size={16} />, hint: '拖曳圓點調整；雙擊線段加點，雙擊圓點刪點' },
  { id: 'erase', label: '擦除', key: 'E', icon: <Eraser size={16} />, hint: '點一下圈選線內部，刪除整個圈選' },
]
const IDLE_LIMIT_MS = 60_000

export function Circle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [image, setImage] = useState<ImageDetail | null>(null)
  const [structures, setStructures] = useState<Structure[]>([])
  const [shapes, setShapes] = useState<Shape[]>([])
  const [states, setStates] = useState<Record<string, string>>({})
  const [grade, setGrade] = useState<number | null>(null)
  const [unsure, setUnsure] = useState(false)
  const [gradeReason, setGradeReason] = useState('')
  const [note, setNote] = useState('')
  const [discuss, setDiscuss] = useState(false)
  const [unusable, setUnusable] = useState('')
  const [unusableOpen, setUnusableOpen] = useState(false)
  const [side, setSide] = useState<Side>(null)
  const [active, setActive] = useState('kidney')
  const [tool, setTool] = useState<Tool>('trace')
  const [showShapes, setShowShapes] = useState(true)
  const [brightness, setBrightness] = useState(100)
  const [contrast, setContrast] = useState(100)
  const [saveText, setSaveText] = useState('')
  const [problem, setProblem] = useState<CompleteResult | null>(null)
  const [loadError, setLoadError] = useState('')
  const undo = useRef<Shape[][]>([])
  const redo = useRef<Shape[][]>([])
  const timer = useRef<number>()
  const pending = useRef<Record<string, unknown> | null>(null)
  const clock = useRef({ last: Date.now(), seconds: 0 })

  const tick = useCallback(() => {
    const now = Date.now()
    const gap = now - clock.current.last
    clock.current.last = now
    if (gap < IDLE_LIMIT_MS) clock.current.seconds += gap / 1000  // 離開座位的時間不算
  }, [])

  const flush = useCallback(async (imageId: string) => {
    window.clearTimeout(timer.current)
    tick()
    const body = pending.current ?? {}
    const seconds = clock.current.seconds
    pending.current = null
    clock.current.seconds = 0
    if (Object.keys(body).length === 0 && seconds < 1) return
    setSaveText('儲存中…')
    try {
      const saved = await api<{ status: ImageDetail['status'] }>(`/images/${imageId}`, 'PUT', { ...body, seconds })
      setImage((current) => (current && current.id === imageId ? { ...current, status: saved.status } : current))
      setSaveText('已自動儲存')
    } catch {
      pending.current = { ...body, ...(pending.current ?? {}) }
      clock.current.seconds += seconds
      setSaveText('儲存失敗，稍後會再試一次')
      timer.current = window.setTimeout(() => flush(imageId), 3000)
      throw new Error('save failed')
    }
  }, [tick])

  const queue = useCallback((change: Record<string, unknown>) => {
    tick()
    pending.current = { ...(pending.current ?? {}), ...change }
    setSaveText('未儲存…')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => flush(id).catch(() => undefined), 400)
  }, [flush, id, tick])

  useEffect(() => {
    let alive = true
    setImage(null)
    setProblem(null)
    setLoadError('')
    undo.current = []
    redo.current = []
    clock.current = { last: Date.now(), seconds: 0 }
    Promise.all([api<ImageDetail>(`/images/${id}`), api<{ structures: Structure[] }>('/structures')])
      .then(([detail, list]) => {
        if (!alive) return
        setImage(detail)
        setStructures(list.structures)
        setShapes(detail.shapes)
        setStates(detail.states)
        setGrade(detail.grade)
        setUnsure(detail.grade_unsure)
        setGradeReason(detail.grade_reason)
        setNote(detail.note)
        setDiscuss(detail.discuss)
        setUnusable(detail.unusable_reason)
        setUnusableOpen(Boolean(detail.unusable_reason))
        setSide(detail.side)
        setSaveText('')
      })
      .catch((e: Error) => alive && setLoadError(e.message))
    return () => {
      alive = false
      flush(id).catch(() => undefined)
    }
  }, [flush, id])

  useEffect(() => {
    const leave = () => {
      if (!pending.current) return
      tick()
      fetch(`/api/images/${id}`, { method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...pending.current, seconds: clock.current.seconds }) })
    }
    window.addEventListener('pagehide', leave)
    return () => window.removeEventListener('pagehide', leave)
  }, [id, tick])

  const change = useCallback((next: Shape[]) => {
    undo.current.push(shapes)
    redo.current = []
    setShapes(next)
    queue({ shapes: next })
  }, [queue, shapes])

  const stepHistory = useCallback((from: typeof undo, to: typeof undo) => {
    const previous = from.current.pop()
    if (!previous) return
    to.current.push(shapes)
    setShapes(previous)
    queue({ shapes: previous })
  }, [queue, shapes])

  const available = structures.filter((s) => s.active || shapes.some((x) => x.structure === s.code))
  const hotkeys = available.filter((s) => s.active).slice(0, 9)
  const adjusted = brightness !== 100 || contrast !== 100

  const go = useCallback(async (target: string | null) => {
    await flush(id).catch(() => undefined)
    navigate(target ? `/circle/${target}` : '/')
  }, [flush, id, navigate])

  const finish = useCallback(async (force = false) => {
    if (!image) return
    try {
      await flush(id)
      const result = await api<CompleteResult>(`/images/${id}/complete`, 'POST', { force })
      if (!result.ok) {
        setProblem(result)
        return
      }
      setProblem(null)
      const summary = await api<{ next_id: string | null }>('/summary')
      navigate(summary.next_id ? `/circle/${summary.next_id}` : '/')
    } catch {
      setProblem({ ok: false, status: image.status, errors: ['還沒存好，請等「已自動儲存」後再按一次。'], warnings: [] })
    }
  }, [flush, id, image, navigate])

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest('input, textarea, select')) return
      const key = e.key.toLowerCase()
      if ((e.ctrlKey || e.metaKey) && key === 'z') {
        e.preventDefault()
        if (e.shiftKey) stepHistory(redo, undo)
        else stepHistory(undo, redo)
      } else if ((e.ctrlKey || e.metaKey) && key === 'y') {
        e.preventDefault()
        stepHistory(redo, undo)
      } else if (e.ctrlKey || e.metaKey || e.altKey) {
        return
      } else if (/^[1-9]$/.test(e.key)) {
        const item = hotkeys[Number(e.key) - 1]
        if (item) setActive(item.code)
      } else if (key === 't' || key === 'p' || key === 'a' || key === 'e') {
        setTool(TOOLS.find((t) => t.key.toLowerCase() === key)!.id)
      } else if (key === 'h') {
        setShowShapes((v) => !v)
      } else if (e.key === 'Enter' && !(e.target as HTMLElement).closest('button')) {
        finish()
      } else if (e.key === 'ArrowLeft' && image?.prev_id) {
        go(image.prev_id)
      } else if (e.key === 'ArrowRight' && image?.next_id) {
        go(image.next_id)
      }
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [finish, go, hotkeys, image, stepHistory])

  if (loadError) return <div className="p-8 text-alert">{loadError} <Link to="/" className="text-steel underline">回首頁</Link></div>
  if (!image) return <div className="h-full bg-viewer" />

  const setState = (code: string, value: 'absent' | 'unlabeled') => {
    const next = { ...states }
    if (next[code] === value) delete next[code]
    else next[code] = value
    setStates(next)
    queue({ states: next })
  }
  const changeSide = (value: Side) => {
    setSide(value)
    const old = value === 'right' ? 'liver' : value === 'left' ? 'spleen' : side === 'right' ? 'spleen' : 'liver'
    const next = { ...states }
    if (next[old] === 'absent') delete next[old]
    if (value) next[value === 'right' ? 'spleen' : 'liver'] = 'absent'
    setStates(next)
    queue({ side: value })
  }
  const chooseGrade = (value: number | null) => {
    setGrade(value)
    setUnsure(value === null)
    queue({ grade: value, grade_unsure: value === null })
  }
  const reference = side === 'right' ? '肝' : side === 'left' ? '脾' : '參考器官'
  const activeItem = structures.find((s) => s.code === active)
  const activeTool = TOOLS.find((t) => t.id === tool)!

  return (
    <div className="flex h-full min-h-0 flex-col bg-viewer text-viewer-text">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-viewer-line px-3 py-2 text-sm">
        <Link to="/" onClick={() => flush(id).catch(() => undefined)} className="flex items-center gap-1 text-viewer-soft hover:text-white"><ArrowLeft size={16} />首頁</Link>
        <span className="font-medium">第 {image.position} / {image.total} 張</span>
        <span className="text-viewer-soft">{image.id}</span>
        <span className="rounded bg-viewer-panel px-2 py-0.5 text-xs">{STATUS_LABEL[image.status]}</span>
        <span className="ml-auto text-viewer-soft" role="status">{saveText}</span>
        <button type="button" aria-label="上一張" title="上一張（←）" disabled={!image.prev_id} onClick={() => go(image.prev_id)} className="rounded p-1 hover:bg-viewer-panel disabled:opacity-30"><ChevronLeft size={18} /></button>
        <button type="button" aria-label="下一張" title="下一張（→）" disabled={!image.next_id} onClick={() => go(image.next_id)} className="rounded p-1 hover:bg-viewer-panel disabled:opacity-30"><ChevronRight size={18} /></button>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-1.5 border-b border-viewer-line px-3 py-1.5 text-sm">
            {TOOLS.map((t) => (
              <button key={t.id} type="button" title={t.hint} onClick={() => setTool(t.id)} aria-pressed={tool === t.id}
                className={`flex items-center gap-1.5 rounded px-2.5 py-1 ${tool === t.id ? 'bg-steel text-white' : 'hover:bg-viewer-panel'}`}>
                {t.icon}{t.label}<kbd className="text-xs opacity-60">{t.key}</kbd>
              </button>
            ))}
            <span className="mx-1 h-5 w-px bg-viewer-line" />
            <button type="button" aria-label="復原" title="復原（Ctrl+Z）" onClick={() => stepHistory(undo, redo)} className="rounded p-1.5 hover:bg-viewer-panel"><Undo2 size={16} /></button>
            <button type="button" aria-label="重做" title="重做（Ctrl+Y）" onClick={() => stepHistory(redo, undo)} className="rounded p-1.5 hover:bg-viewer-panel"><Redo2 size={16} /></button>
            <button type="button" aria-label={showShapes ? '隱藏圈選' : '顯示圈選'} title="隱藏或顯示圈選（H）" onClick={() => setShowShapes((v) => !v)} className="rounded p-1.5 hover:bg-viewer-panel">{showShapes ? <Eye size={16} /> : <EyeOff size={16} />}</button>
            <span className="mx-1 h-5 w-px bg-viewer-line" />
            <label className="flex items-center gap-1 text-viewer-soft">亮度<input type="range" min={40} max={200} value={brightness} onChange={(e) => setBrightness(Number(e.target.value))} className="w-20 accent-steel" /></label>
            <label className="flex items-center gap-1 text-viewer-soft">對比<input type="range" min={40} max={250} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} className="w-20 accent-steel" /></label>
            {adjusted && <button type="button" onClick={() => { setBrightness(100); setContrast(100) }} className="rounded px-1.5 py-0.5 text-viewer-soft hover:bg-viewer-panel">還原</button>}
            <span className="ml-auto flex items-center gap-1 text-xs text-viewer-soft"><Maximize size={13} />滾輪縮放 · 空白鍵拖曳 · 0 回到全圖</span>
          </div>
          <div className="min-h-0 flex-1">
            <Canvas image={image} shapes={shapes} structures={structures} active={active} tool={tool} showShapes={showShapes} brightness={brightness} contrast={contrast} onChange={change} />
          </div>
          <div className="border-t border-viewer-line px-3 py-1 text-xs text-viewer-soft">{activeTool.hint}</div>
        </main>

        <aside className="flex w-[300px] shrink-0 flex-col gap-3 overflow-y-auto border-l border-viewer-line p-3 text-sm">
          <section aria-label="腎臟側別" className={`rounded border p-2 ${side ? 'border-viewer-line bg-viewer-panel' : 'border-amber bg-amber-wash text-ink'}`}>
            <div className="flex items-baseline justify-between gap-2">
              <h2 className={`text-xs ${side ? 'text-viewer-soft' : ''}`}>{side ? '系統判定側別，請確認' : '系統判斷不出側別，請選擇'}</h2>
              {side && <span className="text-xs text-viewer-soft">參考器官：{reference}</span>}
            </div>
            <p className="mt-0.5 text-xl font-medium">{side ? SIDE_LABEL[side] : '未知'}</p>
            <div className="mt-1.5 flex gap-1">
              {(['right', 'left', null] as Side[]).map((value) => (
                <button key={value ?? 'unknown'} type="button" onClick={() => changeSide(value)} aria-pressed={side === value}
                  className={`h-7 flex-1 rounded border text-xs ${side === value ? 'border-steel bg-steel text-white' : side ? 'border-viewer-line hover:bg-viewer' : 'border-amber hover:bg-white'}`}>
                  {value ? SIDE_LABEL[value] : '未知'}
                </button>
              ))}
            </div>
          </section>

          <section aria-label="圈選項目">
            <div className="mb-1 flex items-center justify-between">
              <h2 className="font-medium">圈選項目</h2>
              <Link to="/colors" onClick={() => flush(id).catch(() => undefined)} className="text-xs text-viewer-soft hover:text-white">新增顏色</Link>
            </div>
            <ul className="space-y-0.5">
              {available.map((item) => {
                const count = shapes.filter((s) => s.structure === item.code).length
                const key = hotkeys.findIndex((h) => h.code === item.code) + 1
                const core = CORE.includes(item.code)
                return (
                  <li key={item.code} className={`rounded ${active === item.code ? 'bg-viewer-panel' : ''}`}>
                    <button type="button" onClick={() => setActive(item.code)} aria-pressed={active === item.code} className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-viewer-panel">
                      <span className="w-3 text-xs text-viewer-soft">{key || ''}</span>
                      <span className="h-3.5 w-3.5 shrink-0 rounded-sm" style={item.line === 'dashed' ? { border: `2px dashed ${item.color}` } : { background: item.color }} />
                      <span className="min-w-0 flex-1 truncate">{item.name}</span>
                      <span className="text-xs text-viewer-soft">{count > 0 ? `已圈 ${count}` : core ? (states[item.code] === 'absent' ? '不在影像中' : states[item.code] === 'unlabeled' ? '未標' : '待處理') : ''}</span>
                    </button>
                    {core && count === 0 && active === item.code && (
                      <div className="flex gap-1 px-1.5 pb-1.5 pl-[42px]">
                        {(['absent', 'unlabeled'] as const).map((value) => (
                          <button key={value} type="button" onClick={() => setState(item.code, value)} aria-pressed={states[item.code] === value}
                            className={`rounded border border-viewer-line px-1.5 py-0.5 text-xs ${states[item.code] === value ? 'bg-steel text-white' : 'hover:bg-viewer'}`}>
                            {value === 'absent' ? '不在影像中' : '未標'}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
            {activeItem && <p className="mt-1.5 rounded bg-viewer-panel p-2 text-xs leading-relaxed text-viewer-soft">{activeItem.meaning}</p>}
          </section>

          <section aria-label="回音分級">
            <h2 className="mb-1 font-medium">回音分級（皮質比{reference}）</h2>
            {adjusted ? (
              <p className="rounded bg-viewer-panel p-2 text-xs text-viewer-soft">判讀時要用原始亮度。<button type="button" className="ml-1 text-white underline" onClick={() => { setBrightness(100); setContrast(100) }}>還原亮度對比</button></p>
            ) : (
              <>
                <div className="flex gap-1">
                  {GRADES.map((g) => (
                    <button key={g.value} type="button" title={g.hint} onClick={() => chooseGrade(g.value)} aria-pressed={grade === g.value && !unsure}
                      className={`h-8 flex-1 rounded border border-viewer-line ${grade === g.value && !unsure ? 'bg-steel text-white' : 'hover:bg-viewer-panel'}`}>{g.label}</button>
                  ))}
                  <button type="button" onClick={() => chooseGrade(null)} aria-pressed={unsure} className={`h-8 flex-[2] rounded border border-viewer-line text-xs ${unsure ? 'bg-steel text-white' : 'hover:bg-viewer-panel'}`}>無法判斷</button>
                </div>
                <p className="mt-1 text-xs text-viewer-soft">{unsure ? '' : grade !== null ? GRADES[grade].hint : '比同深度的皮質和參考器官'}</p>
                {unsure && (
                  <label className="mt-1 block text-xs text-viewer-soft">原因
                    <input value={gradeReason} maxLength={80} onChange={(e) => { setGradeReason(e.target.value); queue({ grade_reason: e.target.value }) }} className="mt-0.5 w-full rounded border border-viewer-line bg-viewer-panel px-2 py-1 text-sm text-viewer-text" />
                  </label>
                )}
              </>
            )}
          </section>

          <section aria-label="備註">
            <label className="block font-medium">備註
              <textarea value={note} rows={2} maxLength={500} onChange={(e) => { setNote(e.target.value); queue({ note: e.target.value }) }} className="mt-1 w-full resize-none rounded border border-viewer-line bg-viewer-panel px-2 py-1 text-sm font-normal" />
            </label>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-viewer-soft">
              <label className="flex items-center gap-1"><input type="checkbox" checked={discuss} onChange={(e) => { setDiscuss(e.target.checked); queue({ discuss: e.target.checked }) }} className="accent-steel" />需要討論</label>
              <label className="flex items-center gap-1"><input type="checkbox" checked={unusableOpen} onChange={(e) => { setUnusableOpen(e.target.checked); if (!e.target.checked) { setUnusable(''); queue({ unusable_reason: '' }) } }} className="accent-steel" />影像不能用</label>
            </div>
            {unusableOpen && (
              <label className="mt-1 block text-xs text-viewer-soft">不能用的原因
                <input value={unusable} maxLength={200} onChange={(e) => { setUnusable(e.target.value); queue({ unusable_reason: e.target.value }) }} className="mt-0.5 w-full rounded border border-viewer-line bg-viewer-panel px-2 py-1 text-sm text-viewer-text" />
              </label>
            )}
          </section>

          {problem && (
            <section role="alert" className="rounded border border-amber bg-amber-wash p-2 text-xs text-ink">
              <ul className="list-disc space-y-0.5 pl-4">
                {problem.errors.map((text) => <li key={text}>{text}</li>)}
                {problem.warnings.map((text) => <li key={text}>{text}</li>)}
              </ul>
              {problem.errors.length === 0 && <button type="button" onClick={() => finish(true)} className="mt-1.5 rounded bg-amber px-2 py-1 text-white">確認無誤，仍要完成</button>}
            </section>
          )}

          <button type="button" onClick={() => finish()} className="sticky bottom-0 mt-auto flex shrink-0 items-center justify-center gap-1.5 rounded bg-steel px-3 py-2 font-medium text-white hover:bg-steel-dark">
            <Check size={16} />{unusable.trim() ? '標記不能用，下一張' : '完成，下一張'}<kbd className="text-xs opacity-70">Enter</kbd>
          </button>
        </aside>
      </div>
    </div>
  )
}
