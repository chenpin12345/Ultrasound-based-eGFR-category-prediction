import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ScanSearch } from 'lucide-react'
import { api, imageUrl } from '../../api/client'
import { useAction } from '../../api/hooks'
import { fmt, type ModelInfo } from '../../api/ml'
import { Button, Field, KeyValue, PageHeader, Panel, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress } from '../../components/live'
import { ModelPicker, topClass, type PipelineResult } from './Pipelines'
import { useAllModels } from '../../api/models'

export default function Analysis() {
  const [params] = useSearchParams()
  const models = useAllModels()
  const [imageId, setImageId] = useState(params.get('image') ?? '')
  const [seg, setSeg] = useState('')
  const [cls, setCls] = useState<string[]>([])
  const [job, setJob] = useState<string | null>(null)
  const [result, setResult] = useState<PipelineResult | null>(null)
  const start = useAction(() => api.post<{ job_id: string }>('/pipelines', { seg_model_id: seg, classifier_ids: cls, image_ids: [imageId.trim()] }))
  const load = useAction((id: string) => api.get<PipelineResult>(`/pipelines/${id}`))
  const row = result?.images[0]
  const modelOf = (id: string): ModelInfo | undefined => models.data?.models.find((m) => m.id === id)

  return (
    <>
      <PageHeader title="AI 分析" description="對單張影像執行分割與分類，檢查模型在個別影像上的表現。結果僅供研究，不是診斷。" />
      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Panel title="設定">
          <Field label="影像編號">
            <input className={inputClass} value={imageId} onChange={(e) => setImageId(e.target.value)} placeholder="IMG-…" />
          </Field>
          <div className="mt-3">
            <ModelPicker models={models.data?.models ?? []} seg={seg} setSeg={setSeg} cls={cls} setCls={setCls} />
          </div>
          <ErrorNote error={start.error} />
          <div className="mt-3">
            <Button
              variant="primary"
              icon={ScanSearch}
              disabled={start.busy || !imageId.trim() || (!seg && !cls.length)}
              onClick={async () => {
                setResult(null)
                const r = await start.run()
                if (r) setJob(r.job_id)
              }}
            >
              分析
            </Button>
          </div>
          {job && (
            <div className="mt-4">
              <JobProgress
                jobId={job}
                onDone={async (j) => {
                  if (j.status === 'completed') {
                    const r = await load.run(job)
                    if (r) setResult(r)
                  }
                }}
              />
            </div>
          )}
        </Panel>
        <div className="space-y-5">
          {row && (
            <>
              <Panel title={`${row.image_id}`} flush>
                <div className="relative overflow-hidden rounded-md bg-viewer">
                  <img src={imageUrl(row.image_id, 'model')} alt="去識別化影像" className="block h-auto w-full" />
                  {seg && <img src={`/api/pipelines/${result?.job_id}/masks/${row.image_id}`} alt="預測遮罩" className="pointer-events-none absolute inset-0 h-full w-full" />}
                </div>
                <p className="px-4 py-2 text-[12px] text-ink-faint">疊圖：青＝腎實質、紫＝腎竇、黃＝肝、綠＝脾（和標註編輯器相同）。</p>
              </Panel>
              <Panel title="結果">
                <KeyValue
                  items={[
                    ['側別', row.side === 'right' ? '右腎（參考：肝）' : row.side === 'left' ? '左腎（參考：脾）' : '未知'],
                    ...(seg
                      ? ([
                          ['腎長／寬', `${fmt(row.length_mm, 1)}／${fmt(row.width_mm, 1)} mm`],
                          ['皮質／參考比值（平均、中位數）', `${fmt(row.ratio_mean)}、${fmt(row.ratio_median)}`],
                          ['P 指數（探索性）', fmt(row.p_index)],
                          ['可靠', row.reliable ? '是' : `否：${String(row.reasons || '')}`],
                        ] as [string, string][])
                      : []),
                    ...(result?.models ?? []).map((m) => [m, topClass(row[m], modelOf(m))] as [string, string]),
                  ]}
                />
              </Panel>
            </>
          )}
          <ErrorNote error={load.error} />
        </div>
      </div>
    </>
  )
}
