import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, Check, CircleDashed, FileClock, FileText, Info, Loader2, Minus, RotateCcw, Wrench, XCircle } from 'lucide-react'
import { BackLink, Button, KeyValue, Panel, Pill, inputClass } from '../../components/ui'
import { GradeScale, type Grade } from '../../components/GradeScale'
import { Drawer } from '../../components/overlays'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import {
  CANDIDATE_LABEL, DM_LABEL, SEX_LABEL, SIDE_LABEL, clinicalImageUrl, examTone, mm, overlayUrl, pct, when,
  type ExamDetail, type ExamImage, type Side, type StepResult,
} from '../../api/clinical'

const STEP_NAMES = { segmentation: '分割與量測', egfr: 'eGFR', grade: '回音分級' } as const
const STEP_ICON: Record<StepResult['status'], JSX.Element> = {
  done: <Check className="h-4 w-4 text-ok" aria-label="完成" />,
  failed: <XCircle className="h-4 w-4 text-alert" aria-label="失敗" />,
  skipped: <AlertTriangle className="h-4 w-4 text-amber" aria-label="略過" />,
  not_configured: <Minus className="h-4 w-4 text-ink-faint" aria-label="未設定" />,
}
const EDIT_NAMES: Record<string, string> = {
  exclude: '排除影像', include: '還原影像', side: '指定側別', length: '修改腎長', grade: '修改分級', clinical: '補填臨床資料', reanalyze: '重新分析', layout: '建立版面範本', transfer: '轉入研究',
}
const show = (v: unknown): string => {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k === 'side' ? '' : `${k}：`}${k === 'side' ? SIDE_LABEL[x as Side] ?? x : show(x)}`).join('，')
  return String(v)
}

/** 影像檢視器：放大、平移、亮度、對比只影響顯示；疊圖畫在去識別化影像上。 */
function Viewer({ image, analysisId, hasMask }: { image: ExamImage; analysisId: string | null; hasMask: boolean }) {
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [bright, setBright] = useState(100)
  const [contrast, setContrast] = useState(100)
  const [overlay, setOverlay] = useState(true)
  const drag = useRef<{ x: number; y: number } | null>(null)
  useEffect(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }, [image.id])
  const down = (e: ReactPointerEvent) => {
    drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
  }
  const move = (e: ReactPointerEvent) => drag.current && zoom > 1 && setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y })
  const style = { transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: 'center' }
  return (
    <div>
      <div
        className={`relative flex aspect-[4/3] items-center justify-center overflow-hidden rounded-md bg-black ${zoom > 1 ? 'cursor-grab' : ''}`}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={() => (drag.current = null)}
        onWheel={(e) => setZoom((z) => Math.min(6, Math.max(1, z * (e.deltaY < 0 ? 1.15 : 1 / 1.15))))}
      >
        <div className="relative max-h-full max-w-full" style={style}>
          <img src={clinicalImageUrl(image.id)} alt={`影像 ${image.seq}（去識別化）`} className="block max-h-[60vh] max-w-full select-none" draggable={false}
            style={{ filter: `brightness(${bright}%) contrast(${contrast}%)` }} />
          {overlay && hasMask && analysisId && (
            <img src={overlayUrl(analysisId, image.id)} alt="" aria-hidden className="pointer-events-none absolute inset-0 h-full w-full select-none" draggable={false} />
          )}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px]">
        <label className="flex items-center gap-2">放大<input type="range" min={1} max={6} step={0.1} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="w-24 accent-steel" /></label>
        <label className="flex items-center gap-2">亮度<input type="range" min={40} max={200} value={bright} onChange={(e) => setBright(Number(e.target.value))} className="w-24 accent-steel" /></label>
        <label className="flex items-center gap-2">對比<input type="range" min={40} max={250} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} className="w-24 accent-steel" /></label>
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-steel" checked={overlay} disabled={!hasMask} onChange={(e) => setOverlay(e.target.checked)} />遮罩疊圖</label>
        <button type="button" className="text-steel hover:underline" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); setBright(100); setContrast(100) }}>重設</button>
        <a href={clinicalImageUrl(image.id)} target="_blank" rel="noreferrer" className="text-steel hover:underline">全尺寸</a>
      </div>
    </div>
  )
}

function ClinicalForm({ exam, onSaved }: { exam: ExamDetail; onSaved: () => void }) {
  const [age, setAge] = useState(exam.clinical.age?.toString() ?? '')
  const [sex, setSex] = useState(exam.clinical.sex ?? '')
  const [dm, setDm] = useState(exam.clinical.diabetes)
  const save = useAction(async () => {
    await api.patch(`/clinical/exams/${exam.id}/clinical`, { age: age === '' ? null : Number(age), sex: sex || null, diabetes: dm })
    onSaved()
  })
  const locked = exam.status === 'signed'
  return (
    <div id="clinical">
      <div className="grid grid-cols-3 gap-2">
        <label className="text-[13px]">年齡<input className={`${inputClass} mt-1`} inputMode="numeric" value={age} disabled={locked} onChange={(e) => setAge(e.target.value)} /></label>
        <label className="text-[13px]">性別
          <select className={`${inputClass} mt-1`} value={sex} disabled={locked} onChange={(e) => setSex(e.target.value)}>
            <option value="">未填</option><option value="M">男</option><option value="F">女</option>
          </select>
        </label>
        <label className="text-[13px]">糖尿病
          <select className={`${inputClass} mt-1`} value={dm} disabled={locked} onChange={(e) => setDm(e.target.value as typeof dm)}>
            <option value="unknown">不明</option><option value="yes">有</option><option value="no">無</option>
          </select>
        </label>
      </div>
      {exam.missing_clinical.length > 0 && <p className="mt-2 text-[13px] text-amber">缺{exam.missing_clinical.join('、')}：用到臨床資料的模型會略過。補填後按「重新分析」。</p>}
      {save.error && <p className="mt-2 text-[13px] text-alert">{save.error.message}</p>}
      {!locked && <div className="mt-2"><Button disabled={save.busy} onClick={() => void save.run()}>儲存臨床資料</Button></div>}
    </div>
  )
}

function SidePanel({ exam, side, onChanged }: { exam: ExamDetail; side: Side; onChanged: () => void }) {
  const res = exam.analysis?.results.sides?.[side]
  const override = exam.overrides[side] ?? {}
  const [length, setLength] = useState('')
  const locked = exam.status === 'signed'
  const patch = useAction(async (body: Record<string, unknown>) => {
    await api.patch(`/clinical/exams/${exam.id}/sides/${side}`, body)
    setLength('')
    onChanged()
  })
  const prev = exam.previous?.sides?.[side]
  if (!res) return <p className="text-[14px] text-ink-faint">這一側沒有可分析的影像。</p>
  const shownLength = override.length_mm ?? res.length_mm
  const aiGrade = res.grade ? (Number(res.grade.predicted.slice(1)) as Grade) : undefined
  const chosen = override.grade ? (Number(override.grade.slice(1)) as Grade) : undefined
  return (
    <div className="space-y-3">
      <KeyValue
        items={[
          ['腎長', <span key="l">{mm(shownLength)} {override.length_mm !== undefined ? <Pill tone="steel">已修改（AI {mm(res.length_mm)}）</Pill> : res.length_mm !== null && <Pill tone="amber">AI 建議</Pill>}</span>],
          ['超音波師量的長度', mm(res.sonographer_length_mm)],
          ['回音比（皮質／參考器官）', res.ratio_mean?.toFixed(3) ?? '—'],
          ['P 指數', res.p_index?.toFixed(3) ?? '—'],
          ['影像', `${res.images} 張`],
          ...(prev ? ([['前次腎長', `${mm(prev.length_mm)}${prev.length_mm && shownLength ? `（變化 ${(shownLength - prev.length_mm).toFixed(1)} mm）` : ''}`]] as [string, string][]) : []),
        ]}
      />
      {res.missing.length > 0 && <p className="text-[13px] text-amber">{res.missing.join('；')}</p>}
      {!locked && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[13px]">修改腎長（mm）
            <input className={`${inputClass} mt-1 w-28`} inputMode="decimal" value={length} onChange={(e) => setLength(e.target.value)} />
          </label>
          <Button disabled={!length || patch.busy} onClick={() => void patch.run({ length_mm: Number(length) })}>儲存</Button>
          {override.length_mm !== undefined && <Button variant="ghost" icon={RotateCcw} onClick={() => void patch.run({ length_mm: null })}>改回 AI</Button>}
        </div>
      )}
      {res.grade && (
        <div>
          <p className="mb-1.5 text-[13px] text-ink-faint">回音分級（按 0–3 選擇，Enter 確認 AI 建議）</p>
          <GradeScale probabilities={res.grade.probs} selected={chosen ?? aiGrade} confirmed={chosen !== undefined}
            onSelect={locked ? undefined : (g) => void patch.run({ grade: `G${g}` })} />
        </div>
      )}
      {patch.error && <p className="text-[13px] text-alert">{patch.error.message}</p>}
    </div>
  )
}

export default function ExamWorkspace() {
  const { examId } = useParams()
  const navigate = useNavigate()
  const { data: exam, error, reload } = useApi<ExamDetail>(`/clinical/exams/${examId}`, [examId])
  usePolling(reload, 3000, Boolean(exam && (exam.analysis_running || ['receiving', 'analyzing'].includes(exam.status))))
  const [current, setCurrent] = useState(0)
  const [side, setSide] = useState<Side>('right')
  const [history, setHistory] = useState(false)
  const [modelInfo, setModelInfo] = useState(false)
  const [notice, setNotice] = useState('')

  const images = exam?.images ?? []
  const shown = images.filter((i) => i.status === 'ok' || i.status === 'excluded')
  const image = shown[Math.min(current, shown.length - 1)]
  const analysis = exam?.analysis ?? null
  const masks = new Set((analysis?.results.images ?? []).filter((r) => r.mask).map((r) => r.image_id))
  const locked = exam?.status === 'signed'

  const act = useAction(async (fn: () => Promise<unknown>, done?: string) => {
    await fn()
    if (done) setNotice(done)
    await reload()
  })
  const setImage = useCallback((img: ExamImage, body: Record<string, unknown>) => act.run(() => api.patch(`/clinical/exams/${exam!.id}/images/${img.id}`, body)), [act, exam])

  // 快捷鍵：←／→ 換影像、R／L 指定側別、0–3 選分級、Enter 確認 AI 分級
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (!exam || locked || ['INPUT', 'SELECT', 'TEXTAREA'].includes(t.tagName)) return
      if (e.key === 'ArrowRight') setCurrent((c) => Math.min(shown.length - 1, c + 1))
      else if (e.key === 'ArrowLeft') setCurrent((c) => Math.max(0, c - 1))
      else if ((e.key === 'r' || e.key === 'R') && image) void setImage(image, { side: 'right' })
      else if ((e.key === 'l' || e.key === 'L') && image) void setImage(image, { side: 'left' })
      else if (/^[0-3]$/.test(e.key) && analysis?.results.sides?.[side]?.grade) void act.run(() => api.patch(`/clinical/exams/${exam.id}/sides/${side}`, { grade: `G${e.key}` }))
      else if (e.key === 'Enter') {
        const g = analysis?.results.sides?.[side]?.grade?.predicted
        if (g) void act.run(() => api.patch(`/clinical/exams/${exam.id}/sides/${side}`, { grade: g }), `${SIDE_LABEL[side]}分級已確認為 ${g}`)
      } else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [exam, locked, shown.length, image, side, analysis, act, setImage])

  if (error && !exam) return <p className="rounded-md bg-alert-wash px-3 py-2 text-alert">{error.message}</p>
  if (!exam) return <p className="text-ink-soft">讀取中…</p>

  const egfr = analysis?.results.egfr
  const unassigned = analysis?.results.unassigned ?? []
  const hidden = images.filter((i) => i.status === 'layout_mismatch' || i.status === 'residual')
  const openReport = async () => {
    const r = await api.post<{ id: string }>(`/clinical/exams/${exam.id}/report`)
    navigate(`/clinical/exams/${exam.id}/report?id=${r.id}`)
  }

  return (
    <>
      <BackLink to="/clinical/worklist">回工作清單</BackLink>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-[24px] font-bold leading-tight">
          {exam.id}
          <span className="ml-3 text-[16px] font-normal text-ink-soft">
            <Link to={`/clinical/patients/${exam.patient.id}`} className="hover:underline">{exam.patient.case_code}</Link>
            {exam.patient.name && `・${exam.patient.name}・${exam.patient.mrn}`}
            ・{exam.clinical.sex ? SEX_LABEL[exam.clinical.sex] : '性別未填'} {exam.clinical.age ?? '—'} 歲・糖尿病{DM_LABEL[exam.clinical.diabetes]}・{images.length} 張影像
          </span>
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={examTone[exam.status]}>{exam.status_label}</Pill>
          <Button icon={FileClock} variant="ghost" onClick={() => setHistory(true)}>修改紀錄</Button>
          <Button icon={Info} variant="ghost" onClick={() => setModelInfo(true)}>模型</Button>
          {!locked && <Button icon={RotateCcw} disabled={act.busy || exam.analysis_running} onClick={() => void act.run(() => api.post(`/clinical/exams/${exam.id}/reanalyze`), '已排入重新分析')}>重新分析</Button>}
          {analysis && !exam.analysis_running && (
            <Button variant="primary" icon={FileText} onClick={() => void act.run(openReport)}>{exam.report ? '開啟報告' : '建立報告'}</Button>
          )}
        </div>
      </div>

      {analysis?.candidate && <p className="mb-4 rounded-md border border-amber/30 bg-amber-wash px-3 py-2 text-[14px] text-amber">這次分析用了候選模型：{CANDIDATE_LABEL}。</p>}
      {notice && <p className="mb-4 rounded-md bg-steel-wash px-3 py-2 text-[14px] text-steel-dark">{notice}</p>}
      {act.error && <p className="mb-4 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{act.error.message}</p>}
      {locked && <p className="mb-4 rounded-md bg-paper-deep px-3 py-2 text-[14px] text-ink-soft">報告已簽核，工作區唯讀；要修改請在報告頁按「修訂」。</p>}
      {hidden.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-amber/30 bg-amber-wash px-3 py-2 text-[14px] text-amber">
          <span>{hidden.length} 張影像{hidden.some((i) => i.status === 'layout_mismatch') ? '版面不符（沒見過的影像尺寸）' : '去識別化後仍偵測到文字'}，沒有顯示也沒有分析。</span>
          {hidden.some((i) => i.status === 'layout_mismatch') && (
            <Button icon={Wrench} disabled={act.busy} onClick={() => void act.run(() => api.post(`/clinical/exams/${exam.id}/layout`), '已建立版面範本並重新去識別化；可到「版面範本」微調。')}>
              從最接近的範本建立
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel title={image ? `影像 ${image.seq}／${shown.length}` : '影像'} aside={image && (
            <span className="flex items-center gap-2 text-[13px]">
              {image.side ? <Pill tone="steel">{SIDE_LABEL[image.side]}{image.side_source === 'manual' ? '（手動）' : ''}</Pill> : <Pill tone="amber">未指定側別</Pill>}
              {image.status === 'excluded' && <Pill tone="alert">已排除：{image.exclude_reason}</Pill>}
            </span>
          )}>
            {image ? (
              <>
                <Viewer image={image} analysisId={analysis?.id ?? null} hasMask={masks.has(image.id)} />
                {!locked && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button onClick={() => void setImage(image, { side: 'right' })}>設為右腎（R）</Button>
                    <Button onClick={() => void setImage(image, { side: 'left' })}>設為左腎（L）</Button>
                    {image.status === 'ok' ? (
                      <Button onClick={() => { const reason = window.prompt('排除這張影像的原因：'); if (reason) void setImage(image, { excluded: true, reason }) }}>排除影像</Button>
                    ) : (
                      <Button onClick={() => void setImage(image, { excluded: false })}>還原影像</Button>
                    )}
                  </div>
                )}
                {(image.deid.missing ?? []).length > 0 && <p className="mt-2 text-[13px] text-amber">去識別化缺項：{image.deid.missing!.join('、')}</p>}
                <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
                  {shown.map((img, i) => (
                    <button key={img.id} type="button" onClick={() => setCurrent(i)} aria-label={`影像 ${img.seq}`}
                      className={`relative shrink-0 overflow-hidden rounded border-2 ${img.id === image.id ? 'border-steel' : 'border-transparent'} ${img.status === 'excluded' ? 'opacity-40' : ''}`}>
                      <img src={clinicalImageUrl(img.id, 'thumb')} alt="" className="h-16 w-20 object-cover" />
                      <span className="absolute bottom-0 left-0 bg-ink/70 px-1 text-[11px] text-white">{img.side === 'right' ? 'R' : img.side === 'left' ? 'L' : '?'}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-[12px] text-ink-faint">快捷鍵：←／→ 換影像、R／L 指定側別、0–3 選分級、Enter 確認 AI 分級。滾輪放大、拖曳平移。</p>
              </>
            ) : (
              <p className="text-ink-soft">沒有可顯示的影像。</p>
            )}
          </Panel>
          {unassigned.length > 0 && <p className="rounded-md bg-amber-wash px-3 py-2 text-[14px] text-amber">{unassigned.length} 張影像判斷不出側別，沒有納入左右側整合；請選影像後按 R 或 L，再重新分析。</p>}
        </div>

        <div className="space-y-5">
          <Panel title="分析步驟" aside={exam.analysis_running && <Loader2 className="h-4 w-4 animate-spin text-steel" aria-label="分析中" />}>
            {analysis ? (
              <ul className="space-y-2 text-[14px]">
                {(Object.keys(STEP_NAMES) as (keyof typeof STEP_NAMES)[]).map((k) => {
                  const s = analysis.steps[k]
                  return (
                    <li key={k} className="flex gap-2">
                      {s ? STEP_ICON[s.status] : <CircleDashed className="h-4 w-4 text-ink-faint" />}
                      <span><span className="font-medium">{STEP_NAMES[k]}</span>{s?.message && <span className="block text-[13px] text-ink-soft">{s.message}</span>}</span>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="text-[14px] text-ink-soft">{exam.analysis_running ? '分析中…' : '還沒有分析。'}</p>
            )}
            {analysis?.inputs.device_note && <p className="mt-2 text-[13px] text-ink-faint">{analysis.inputs.device_note}</p>}
          </Panel>
          <Panel title="臨床資料（這次檢查）"><ClinicalForm key={exam.clinical.source + exam.clinical.age + exam.clinical.diabetes} exam={exam} onSaved={() => void reload()} /></Panel>
          <Panel title="eGFR（整次檢查）">
            {egfr ? (
              <>
                <p className="text-[28px] font-bold leading-none">{pct(egfr.p_lt60)}</p>
                <p className="mt-1 text-[14px] text-ink-soft">P(eGFR&lt;60)・預測類別 {egfr.predicted}・{egfr.images} 張影像整合</p>
                <p className="mt-2 text-[13px] text-ink-faint">{egfr.classes.map((c, i) => `${c} ${pct(egfr.probs[i])}`).join('、')}</p>
                {exam.previous?.p_lt60 !== undefined && exam.previous?.p_lt60 !== null && <p className="mt-1 text-[13px] text-ink-soft">前次 {pct(exam.previous.p_lt60)}（{when(exam.previous.received_at).slice(0, 10)}）</p>}
                <p className="mt-2 text-[12px] text-ink-faint">機率是模型輸出，不等於準確率；不是 CKD 診斷。</p>
              </>
            ) : (
              <p className="text-[14px] text-ink-soft">{analysis?.steps.egfr?.message || '沒有 eGFR 結果。'}</p>
            )}
          </Panel>
          <Panel title="左右腎" aside={
            <div className="flex gap-1" role="tablist" aria-label="側別">
              {(['right', 'left'] as Side[]).map((s) => (
                <button key={s} type="button" role="tab" aria-selected={side === s} onClick={() => setSide(s)}
                  className={`rounded px-2.5 py-1 text-[13px] ${side === s ? 'bg-steel text-white' : 'text-ink-soft hover:bg-paper'}`}>{SIDE_LABEL[s]}</button>
              ))}
            </div>
          }>
            <SidePanel key={side} exam={exam} side={side} onChanged={() => void reload()} />
          </Panel>
          {exam.previous && (
            <Panel title="與前次檢查比較">
              <p className="text-[14px] text-ink-soft">
                前次 <Link to={`/clinical/exams/${exam.previous.exam_id}`} className="text-steel hover:underline">{exam.previous.exam_id}</Link>（{when(exam.previous.received_at).slice(0, 10)}）：
                右腎 {mm(exam.previous.sides.right?.length_mm)}、左腎 {mm(exam.previous.sides.left?.length_mm)}、eGFR&lt;60 {pct(exam.previous.p_lt60)}
              </p>
            </Panel>
          )}
        </div>
      </div>

      <Drawer open={history} title="修改紀錄" onClose={() => setHistory(false)}>
        {exam.edits.length ? (
          <ol className="space-y-3 text-[14px]">
            {exam.edits.map((e) => (
              <li key={e.id} className="border-b border-line pb-2">
                <p className="font-medium">{EDIT_NAMES[e.kind] ?? e.kind}{e.image_id && <span className="ml-1 text-[12px] text-ink-faint">{e.image_id}</span>}</p>
                <p className="text-ink-soft">{show(e.before)} → {show(e.after)}{e.reason && `（${e.reason}）`}</p>
                <p className="text-[12px] text-ink-faint">{when(e.created_at)}・{e.actor}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-ink-soft">還沒有修改。</p>
        )}
        <p className="mt-4 text-[13px] text-ink-faint">分析紀錄：{exam.analyses.map((a) => `${a.id}（${a.status}）`).join('、') || '—'}</p>
      </Drawer>
      <Drawer open={modelInfo} title="這次分析用的模型" onClose={() => setModelInfo(false)}>
        {analysis && Object.keys(analysis.models).length ? (
          <ul className="space-y-3 text-[14px]">
            {Object.entries(analysis.models).map(([zone, m]) => (
              <li key={zone} className="border-b border-line pb-2">
                <p className="font-medium">{STEP_NAMES[zone as keyof typeof STEP_NAMES] ?? zone}</p>
                <p className="font-mono text-[13px]">{m.model_id}</p>
                <p className="text-[13px] text-ink-soft">階段：{m.stage === 'candidate' ? `候選（${CANDIDATE_LABEL}）` : m.stage === 'clinical' ? '臨床上線' : m.stage}・來自訓練 {m.run_id}・合約第 {m.contract_version} 版</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-ink-soft">這次分析沒有使用模型（分析方案是空的）。到「設定 › 醫師端」選模型。</p>
        )}
        <p className="mt-4 text-[13px] text-ink-faint">分析紀錄建立後不會被修改；重新分析會新增一筆。{analysis && `本次：${analysis.id}・${when(analysis.created_at)}・裝置 ${analysis.device || '—'}`}</p>
      </Drawer>
    </>
  )
}
