import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Ban, PenTool, RotateCcw } from 'lucide-react'
import { api, imageUrl } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { sideLabel, statusLabel, viewLabel, type ImageInfo } from '../../api/types'
import { BackLink, Button, KeyValue, Panel, Pill, Table, inputClass, type Tone } from '../../components/ui'
import { ConfirmDialog } from '../../components/overlays'
import { ErrorNote, Loading } from '../../components/live'
import { ImageWithMask } from '../../components/MaskOverlay'
import type { Shape } from '../../components/AnnotationCanvas'

const statusTone: Record<ImageInfo['status'], Tone> = { usable: 'ok', excluded: 'neutral', pending_review: 'amber' }
const REASONS = ['腎臟截斷', '陰影遮蔽', '非長軸', '增益異常', '非腎臟', '去識別化殘留', '重複']
const spacingText: Record<string, string> = { ok: '刻度與數字一致', ticks_only: '只用刻度計算', ocr_only: '只用數字計算', mismatch: '刻度與數字不一致', missing: '讀不到' }

interface MaskInfo {
  latest: { version: number; annotator: string; status: string; shapes: Shape[]; created_at: string } | null
  history: { id: number; version: number; annotator: string; status: string; created_at: string }[]
}

export default function ImageDetail() {
  const { imageId = '' } = useParams()
  const image = useApi<ImageInfo>(`/images/${imageId}`)
  const masks = useApi<MaskInfo>(`/annotation/masks/${imageId}`)
  const [kind, setKind] = useState<'model' | 'calc'>('model')
  const [overlay, setOverlay] = useState(true)
  const [excludeOpen, setExcludeOpen] = useState(false)
  const [reason, setReason] = useState(REASONS[0])
  const patch = useAction((body: Record<string, unknown>) => api.patch(`/images/${imageId}`, body))

  if (image.loading && !image.data) return <Loading />
  if (!image.data) return <ErrorNote error={image.error} />
  const i = image.data
  const update = async (body: Record<string, unknown>) => {
    await patch.run(body)
    void image.reload()
  }

  return (
    <>
      <BackLink to="/research/datasets?tab=images">回資料集</BackLink>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-[24px] font-bold">{i.id}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={statusTone[i.status]}>{statusLabel[i.status]}</Pill>
          {i.status !== 'excluded' ? (
            <Button icon={Ban} onClick={() => setExcludeOpen(true)}>
              排除這張影像
            </Button>
          ) : (
            <Button icon={RotateCcw} onClick={() => void update({ status: 'usable' })}>
              還原為可用
            </Button>
          )}
          {i.status === 'pending_review' && (
            <Button variant="primary" onClick={() => void update({ status: 'usable' })}>
              確認沒問題，設為可用
            </Button>
          )}
          <Link to={`/research/annotation/mask?image=${i.id}`} className="inline-flex min-h-[38px] items-center gap-2 rounded-md border border-line bg-white px-3.5 text-[14px] font-medium hover:bg-paper">
            <PenTool className="h-4 w-4" aria-hidden />
            標註遮罩
          </Link>
        </div>
      </div>
      <ErrorNote error={patch.error} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel flush>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2 text-[13px]">
            <span className="flex gap-1" role="tablist" aria-label="影像版本">
              {(
                [
                  ['model', '模型輸入用'],
                  ['calc', '灰階計算用'],
                ] as const
              ).map(([k, l]) => (
                <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => setKind(k)} className={`rounded px-2.5 py-1 ${kind === k ? 'bg-steel-wash font-semibold text-steel-dark' : 'text-ink-soft hover:bg-paper'}`}>
                  {l}
                </button>
              ))}
            </span>
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" className="accent-steel" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} disabled={!masks.data?.latest} />
              顯示遮罩{masks.data?.latest ? `（第 ${masks.data.latest.version} 版）` : '（尚無）'}
            </label>
          </div>
          <div className="p-3">
            <ImageWithMask src={imageUrl(i.id, kind)} width={i.width} height={i.height} shapes={overlay ? masks.data?.latest?.shapes : undefined} />
            <p className="mt-2 text-[12px] text-ink-faint">
              {kind === 'model' ? '模型輸入用：文字區已清空，caliper 已修補。' : '灰階計算用：caliper 與扇形區外標為無效（透明），計算灰階比值時會排除。'}
            </p>
          </div>
        </Panel>

        <div className="space-y-5">
          {i.review_reasons.length > 0 && (
            <Panel title="待確認的原因">
              <ul className="list-disc space-y-1 pl-5 text-[14px] text-amber">
                {i.review_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="影像資料">
            <KeyValue
              items={[
                ['病人', i.patient_id ? <Link key="p" to={`/research/datasets?tab=patients`} className="text-steel hover:underline">{i.patient_id}</Link> : '尚未對照'],
                ['eGFR 分組', i.egfr_group ?? '—'],
                ['機型與尺寸', `${i.machine}・${i.width} × ${i.height}`],
                ['匯入批次', <Link key="b" to={`/research/datasets/imports/${i.batch_id}`} className="text-steel hover:underline">{i.batch_id}</Link>],
                ['像素間距', i.pixel_spacing_mm ? `${i.pixel_spacing_mm.toFixed(4)} mm（${spacingText[i.spacing_check] ?? i.spacing_check}）` : '讀不到深度尺'],
                ['技師量的腎長', i.sonographer_length_mm ? `${i.sonographer_length_mm} mm` : '—'],
                ['增益', i.gain ?? '—'],
                ['caliper 像素', i.caliper_pixels],
                ['去識別化檢查', i.deid_check === 'pass' ? '通過' : i.deid_check === 'residual' ? '有殘留，待確認' : '未檢查'],
              ]}
            />
            <p className="mt-3 text-[13px] text-ink-faint">原始檔名只存在受限的對照表，這裡不顯示。</p>
          </Panel>
          <Panel title="側別與切面">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[14px]">
                側別{i.side_source === 'bodymark' ? '（體表示意圖）' : i.side_source === 'ocr' ? '（OCR）' : i.side_source === 'manual' ? '（人工）' : i.side_source === 'circling' ? '（醫師圈選）' : ''}
                <select className={`${inputClass} mt-1`} value={i.side ?? ''} onChange={(e) => void update({ side: e.target.value })}>
                  <option value="" disabled>
                    未知
                  </option>
                  {(['right', 'left'] as const).map((s) => (
                    <option key={s} value={s}>
                      {sideLabel[s]}腎
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[14px]">
                切面
                <select className={`${inputClass} mt-1`} value={i.view ?? ''} onChange={(e) => void update({ view: e.target.value })}>
                  <option value="" disabled>
                    未標
                  </option>
                  {(['long', 'short', 'oblique'] as const).map((v) => (
                    <option key={v} value={v}>
                      {viewLabel[v]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </Panel>
          <Panel title="遮罩版本" flush>
            {masks.data && masks.data.history.length ? (
              <Table minWidth={300} head={['版本', '標註者', '狀態', '時間']} rows={masks.data.history.map((m) => [`第 ${m.version} 版`, m.annotator, m.status === 'draft' ? '草稿' : '完成', m.created_at.slice(0, 16).replace('T', ' ')])} />
            ) : (
              <p className="px-5 py-4 text-[14px] text-ink-soft">還沒有遮罩標註。</p>
            )}
          </Panel>
        </div>
      </div>

      <ConfirmDialog
        open={excludeOpen}
        title="排除這張影像"
        confirmLabel="排除"
        onClose={() => setExcludeOpen(false)}
        onConfirm={() => {
          setExcludeOpen(false)
          void update({ status: 'excluded', exclude_reason: reason })
        }}
      >
        <p>排除後不會用在訓練與評估，可以隨時還原。</p>
        <label className="mt-3 block text-[14px] text-ink">
          原因
          <select className={`${inputClass} mt-1`} value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
      </ConfirmDialog>
    </>
  )
}
