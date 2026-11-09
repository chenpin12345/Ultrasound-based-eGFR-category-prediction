import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { useParams } from 'react-router-dom'
import { Eye, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import type { Rect, Template } from '../../api/types'
import { BackLink, Button, Field, Panel, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../components/live'
import { ConfirmDialog } from '../../components/overlays'

type ReaderKey = keyof Template['readers']
const READER_NAMES: Record<ReaderKey, string> = { header: '讀取：標頭（年齡性別）', params: '讀取：右側參數', measure: '讀取：Dist A／B', side: '讀取：側別文字', ruler: '讀取：深度尺', bodymark: '讀取：體表示意圖（側別）' }

interface Box extends Rect {
  kind: 'mask' | 'reader'
  key?: ReaderKey
}

/** 版面範本編輯：拖拉方框定義遮蓋區（紅）與讀取區（藍）。座標用百分比，與解析度無關。 */
export default function TemplateEditor() {
  const { templateId = '' } = useParams()
  const tpl = useApi<Template>(`/templates/${templateId}`)
  const samples = useApi<{ image_ids: string[] }>(`/templates/${templateId}/samples`)
  const [boxes, setBoxes] = useState<Box[]>([])
  const [selected, setSelected] = useState(0)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [sample, setSample] = useState('')
  const drag = useRef<{ i: number; dx: number; dy: number } | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!tpl.data) return
    setBoxes([
      ...tpl.data.regions.map((r) => ({ ...r, kind: 'mask' as const })),
      ...(Object.entries(tpl.data.readers) as [ReaderKey, Rect][]).map(([k, r]) => ({ ...r, name: READER_NAMES[k], kind: 'reader' as const, key: k })),
    ])
  }, [tpl.data])
  useEffect(() => {
    if (samples.data?.image_ids.length && !sample) setSample(samples.data.image_ids[0])
  }, [samples.data, sample])

  const payload = () => ({
    regions: boxes.filter((b) => b.kind === 'mask').map(({ name, x, y, w, h }) => ({ name, x, y, w, h })),
    readers: Object.fromEntries(boxes.filter((b) => b.kind === 'reader').map((b) => [b.key, { x: b.x, y: b.y, w: b.w, h: b.h }])),
  })
  const save = useAction(() => api.put<{ version: number }>(`/templates/${templateId}`, payload()))
  const redeid = useAction(() => api.post<{ job_id: string }>('/images/redeid', { template_id: templateId }))
  const [redeidOpen, setRedeidOpen] = useState(false)
  const [redeidJob, setRedeidJob] = useState<string | null>(null)
  const preview = useAction(async () => {
    const blob = await api.post<Blob>(`/templates/${templateId}/preview?image_id=${sample}`, payload())
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old)
      return URL.createObjectURL(blob)
    })
  })

  if (tpl.loading && !tpl.data) return <Loading />
  if (!tpl.data) return <ErrorNote error={tpl.error} />
  const t = tpl.data

  const toPercent = (e: PointerEvent) => {
    const r = boxRef.current!.getBoundingClientRect()
    return { x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 }
  }
  const round = (v: number) => Math.round(Math.min(100, Math.max(0, v)) * 10) / 10
  const update = (i: number, p: Partial<Box>) => setBoxes((bs) => bs.map((b, j) => (j === i ? { ...b, ...p } : b)))
  const current = boxes[selected]

  return (
    <>
      <BackLink to="/research/preprocessing">回影像處理與遮罩</BackLink>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-bold">
            版面範本：{t.machine} {t.width} × {t.height}
          </h1>
          <p className="text-ink-soft">
            第 {t.version} 版・{t.updated_by}・{t.updated_at.slice(0, 16).replace('T', ' ')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={RefreshCw} disabled={redeid.busy || Boolean(redeidJob) || !t.images} onClick={() => setRedeidOpen(true)}>
            用目前範本重新去識別化
          </Button>
          <Button variant="primary" icon={Save} disabled={save.busy} onClick={async () => { await save.run(); void tpl.reload() }}>
            儲存為第 {t.version + 1} 版
          </Button>
        </div>
      </div>
      <ErrorNote error={save.error ?? preview.error ?? redeid.error} />
      {redeidJob && (
        <div className="mb-5">
          <JobProgress jobId={redeidJob} onDone={() => setRedeidJob(null)} />
        </div>
      )}
      <ConfirmDialog
        open={redeidOpen}
        title="重新去識別化"
        confirmLabel="開始"
        onClose={() => setRedeidOpen(false)}
        onConfirm={async () => {
          setRedeidOpen(false)
          const r = await redeid.run()
          if (r) setRedeidJob(r.job_id)
        }}
      >
        <p>用已儲存的第 {t.version} 版範本，從原始檔重做這個尺寸的 {t.images ?? 0} 張影像。影像編號、病人對照與標註都不變；人工排除的影像維持排除。仍偵測到文字的會重新列入「待人工確認」。請先儲存範本。</p>
      </ConfirmDialog>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel flush>
          <div className="p-3">
            <div
              ref={boxRef}
              className="relative select-none overflow-hidden rounded-md bg-viewer"
              style={{ aspectRatio: `${t.width} / ${t.height}` }}
              onPointerMove={(e) => {
                if (!drag.current) return
                const p = toPercent(e)
                const b = boxes[drag.current.i]
                update(drag.current.i, { x: round(Math.min(100 - b.w, p.x - drag.current.dx)), y: round(Math.min(100 - b.h, p.y - drag.current.dy)) })
              }}
              onPointerUp={() => (drag.current = null)}
              onPointerLeave={() => (drag.current = null)}
            >
              {previewUrl ? (
                <img src={previewUrl} alt="馬賽克預覽" className="absolute inset-0 h-full w-full" draggable={false} />
              ) : (
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
                  <path d="M40 12 Q50 10 60 12 L88 82 Q50 90 12 82 Z" fill="#3A4044" />
                </svg>
              )}
              {boxes.map((b, i) => (
                <button
                  key={i}
                  type="button"
                  onPointerDown={(e) => {
                    const p = toPercent(e)
                    drag.current = { i, dx: p.x - b.x, dy: p.y - b.y }
                    setSelected(i)
                    boxRef.current?.setPointerCapture(e.pointerId)
                  }}
                  className={`absolute cursor-move border-2 text-left text-[11px] ${
                    b.kind === 'mask' ? (i === selected ? 'border-[#E06C5A] bg-[#E06C5A]/30' : 'border-[#E06C5A]/70 bg-[#E06C5A]/10') : i === selected ? 'border-[#5EC4D6] bg-[#5EC4D6]/25' : 'border-dashed border-[#5EC4D6]/80'
                  }`}
                  style={{ left: `${b.x}%`, top: `${b.y}%`, width: `${b.w}%`, height: `${b.h}%` }}
                >
                  <span className="m-0.5 inline-block rounded bg-black/60 px-1 text-white">{b.name}</span>
                </button>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px]">
              <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-[#E06C5A]" />遮蓋區</span>
              <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm border-2 border-dashed border-[#5EC4D6]" />讀取區（OCR、深度尺）</span>
              <span className="ml-auto flex items-center gap-2">
                {samples.data?.image_ids.length ? (
                  <>
                    <select className={`${inputClass} w-auto py-1`} value={sample} onChange={(e) => setSample(e.target.value)} aria-label="預覽影像">
                      {samples.data.image_ids.map((id) => (
                        <option key={id}>{id}</option>
                      ))}
                    </select>
                    <Button icon={Eye} disabled={preview.busy} onClick={() => void preview.run()}>
                      用這張影像預覽
                    </Button>
                  </>
                ) : (
                  <span className="text-ink-faint">匯入這個尺寸的影像後才能預覽。</span>
                )}
              </span>
            </div>
            <p className="mt-2 text-[12px] text-ink-faint">預覽會先把整張原圖打成馬賽克（文字無法辨識），只用來確認方框位置是否對準。</p>
          </div>
        </Panel>

        <Panel
          title="區域"
          aside={
            <Button
              variant="ghost"
              icon={Plus}
              onClick={() => {
                setBoxes((bs) => [...bs, { name: `遮蓋區 ${bs.filter((b) => b.kind === 'mask').length + 1}`, x: 40, y: 40, w: 15, h: 10, kind: 'mask' }])
                setSelected(boxes.length)
              }}
            >
              新增遮蓋區
            </Button>
          }
        >
          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {boxes.map((b, i) => (
              <li key={i}>
                <button type="button" onClick={() => setSelected(i)} className={`w-full rounded px-2 py-1.5 text-left text-[14px] ${i === selected ? 'bg-steel-wash font-semibold' : 'hover:bg-paper'}`}>
                  <span className={`mr-2 inline-block h-2.5 w-2.5 rounded-sm ${b.kind === 'mask' ? 'bg-[#E06C5A]' : 'bg-[#5EC4D6]'}`} />
                  {b.name}
                </button>
              </li>
            ))}
          </ul>
          {current && (
            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4">
              {current.kind === 'mask' && (
                <div className="col-span-2">
                  <Field label="名稱">
                    <input className={inputClass} value={current.name ?? ''} onChange={(e) => update(selected, { name: e.target.value })} />
                  </Field>
                </div>
              )}
              {(['x', 'y', 'w', 'h'] as const).map((k) => (
                <Field key={k} label={{ x: '左（%）', y: '上（%）', w: '寬（%）', h: '高（%）' }[k]}>
                  <input type="number" step={0.5} min={0} max={100} className={inputClass} value={current[k]} onChange={(e) => update(selected, { [k]: round(Number(e.target.value)) })} />
                </Field>
              ))}
              {current.kind === 'mask' && (
                <div className="col-span-2">
                  <Button
                    icon={Trash2}
                    onClick={() => {
                      setBoxes((bs) => bs.filter((_, j) => j !== selected))
                      setSelected(0)
                    }}
                  >
                    刪除這個遮蓋區
                  </Button>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </>
  )
}
