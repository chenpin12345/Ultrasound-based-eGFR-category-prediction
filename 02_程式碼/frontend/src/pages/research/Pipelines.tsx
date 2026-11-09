import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Workflow } from 'lucide-react'
import { api } from '../../api/client'
import { useAction } from '../../api/hooks'
import { fmt, modelHref, type ModelInfo } from '../../api/ml'
import { useAllModels } from '../../api/models'
import { Button, Field, PageHeader, Panel, Table, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress } from '../../components/live'

export interface PipelineResult {
  job_id: string
  models: string[]
  images: (Record<string, unknown> & { image_id: string; patient_id: string; side: string | null })[]
  by_patient_side: (Record<string, unknown> & { patient_id: string; side: string | null; images: number; ratio_mean: number | null })[]
}

/** 機率陣列顯示成「最可能的類別（機率）」；eGFR 另外顯示 P(eGFR<60)。 */
export const topClass = (probs: unknown, model?: ModelInfo) => {
  if (!Array.isArray(probs)) return '—'
  const p = probs as number[]
  const best = p.indexOf(Math.max(...p))
  const classes = model?.classes
  if (model?.task === 'egfr') {
    const k = p.length
    const lt60 = k === 2 ? p[1] : k === 3 ? p[1] + p[2] : p[2] + p[3] + p[4]
    return `${classes?.[best] ?? best}（P(<60) ${(lt60 * 100).toFixed(0)}%）`
  }
  if (p.length === 2) return `${(p[1] * 100).toFixed(0)}%`
  return `${classes?.[best] ?? `G${best}`}（${(p[best] * 100).toFixed(0)}%）`
}

export function ModelPicker({ models, seg, setSeg, cls, setCls }: { models: ModelInfo[]; seg: string; setSeg: (v: string) => void; cls: string[]; setCls: (v: string[]) => void }) {
  const segModels = models.filter((m) => m.task === 'segmentation' && m.stage !== 'retired')
  const zones: [string, ModelInfo[]][] = [
    ['eGFR 模型', models.filter((m) => m.task === 'egfr' && m.stage !== 'retired')],
    ['回音分級模型', models.filter((m) => m.task === 'grade' && m.stage !== 'retired')],
  ]
  return (
    <div className="space-y-3">
      <Field label="分割模型（腎長、回音比值）">
        <select className={inputClass} value={seg} onChange={(e) => setSeg(e.target.value)}>
          <option value="">不使用</option>
          {segModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id}（{m.stage_label}）
            </option>
          ))}
        </select>
      </Field>
      {zones.map(([title, list]) => (
        <fieldset key={title}>
          <legend className="mb-1 text-[14px] font-medium">{title}</legend>
          {list.length ? (
            list.map((m) => (
              <label key={m.id} className="flex items-center gap-2 py-0.5 text-[14px]">
                <input type="checkbox" className="accent-steel" checked={cls.includes(m.id)} onChange={(e) => setCls(e.target.checked ? [...cls, m.id] : cls.filter((x) => x !== m.id))} />
                {m.id}（{m.stage_label}）{m.egfr_classes ? `・${m.egfr_classes} 類` : ''}
                {m.features ? '・需要臨床資料或分割模型' : ''}
              </label>
            ))
          ) : (
            <p className="text-[13px] text-ink-faint">還沒有{title}。</p>
          )}
        </fieldset>
      ))}
    </div>
  )
}

export default function Pipelines() {
  const models = useAllModels()
  const [seg, setSeg] = useState('')
  const [cls, setCls] = useState<string[]>([])
  const [ids, setIds] = useState('')
  const [job, setJob] = useState<string | null>(null)
  const [result, setResult] = useState<PipelineResult | null>(null)
  const start = useAction(() =>
    api.post<{ job_id: string }>('/pipelines', {
      seg_model_id: seg,
      classifier_ids: cls,
      image_ids: ids.trim() ? ids.split(/[\s,，]+/).filter(Boolean) : null,
    }),
  )
  const load = useAction((id: string) => api.get<PipelineResult>(`/pipelines/${id}`))

  return (
    <>
      <PageHeader title="流程執行" description="一鍵完成：分割 → 回音特徵 → 分類。每個步驟先檢查模型合約，不符就拒絕；結果存在 03_資料\04_模型產出\預測結果。" />
      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Panel title="設定">
          <ModelPicker models={models.data?.models ?? []} seg={seg} setSeg={setSeg} cls={cls} setCls={setCls} />
          <div className="mt-3">
            <Field label="影像範圍" hint="留空＝全部可用影像；或貼上影像編號（以空白或逗號分隔）">
              <textarea className={`${inputClass} h-20`} value={ids} onChange={(e) => setIds(e.target.value)} />
            </Field>
          </div>
          <ErrorNote error={start.error ?? models.error} />
          <div className="mt-3">
            <Button
              variant="primary"
              icon={Workflow}
              disabled={start.busy || (!seg && !cls.length)}
              onClick={async () => {
                setResult(null)
                const r = await start.run()
                if (r) setJob(r.job_id)
              }}
            >
              執行流程
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
        <Panel title={result ? `結果（每位病人、每一側腎）` : '結果'} flush>
          {result ? (
            <Table
              minWidth={640}
              head={['病人', '側別', '影像數', '回音比值（中位數）', ...result.models.map((m) => <Link key={m} to={modelHref(m)} className="text-steel hover:underline">{m}</Link>)]}
              rows={result.by_patient_side.map((r) => [r.patient_id ?? '—', r.side === 'right' ? '右' : r.side === 'left' ? '左' : '—', r.images, fmt(r.ratio_mean), ...result.models.map((m) => topClass(r[m], models.data?.models.find((x) => x.id === m)))])}
            />
          ) : (
            <p className="px-5 py-4 text-[14px] text-ink-soft">{load.error ? '' : '執行完成後顯示。eGFR 模型顯示最可能的類別與 P(eGFR<60)，回音分級模型顯示最可能的分級。'}</p>
          )}
          <ErrorNote error={load.error} />
        </Panel>
      </div>
    </>
  )
}
