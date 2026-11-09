import { useState } from 'react'
import { Flame } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { fmt } from '../../api/ml'
import { Button, Field, Panel, Pill, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../components/live'

type Zone = 'segmentation' | 'egfr' | 'grade'
interface Option {
  id: string
  stage: 'clinical' | 'candidate'
  score: number | null
}
interface PlanInfo {
  options: Record<Zone, Option[]>
  current: { zones: Record<Zone, { model_id: string | null; stage: string | null; candidate: boolean }>; candidate: boolean; candidate_label: string; problems: string[] }
  loaded: { model_id: string; device: string }[]
}
interface ClinicalValues {
  clinical_plan: Record<Zone, string | null>
  clinical_receiver_port: number
  clinical_device_mode: boolean
}

const ZONES: [Zone, string, string][] = [
  ['segmentation', '分割', '腎長、回音比、P 指數、遮罩疊圖'],
  ['egfr', 'eGFR', 'P(eGFR<60) 與各類機率（整次檢查整合）'],
  ['grade', '回音分級', '目前沒有分級資料，通常不選'],
]

/** 設定 › 醫師端（M3）：分析方案（三區各一個模型，可用候選並加標示）、上傳連接埠、超音波模式。 */
export default function ClinicalSettings() {
  const plan = useApi<PlanInfo>('/clinical/plan')
  const settings = useApi<ClinicalValues>('/settings')
  const [draft, setDraft] = useState<Partial<Record<Zone, string | null>>>({})
  const [port, setPort] = useState<number | null>(null)
  const [job, setJob] = useState<string | null>(null)
  const save = useAction(() =>
    api.put<ClinicalValues>('/settings', {
      clinical_plan: { ...settings.data!.clinical_plan, ...draft },
      ...(port != null ? { clinical_receiver_port: port } : {}),
    }),
  )
  const warm = useAction(() => api.post<{ job_id: string }>('/clinical/warmup'))
  if (!plan.data || !settings.data) return plan.error || settings.error ? <ErrorNote error={plan.error ?? settings.error} /> : <Loading />
  const current = { ...settings.data.clinical_plan, ...draft }
  const p = plan.data

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Panel title="分析方案">
        <p className="mb-3 text-[14px] text-ink-soft">
          每一區選一個模型。優先用「臨床上線」；某一區沒有時可以選「候選」，結果、報告與 PDF 會標示「{p.current.candidate_label}」。「研究」「退役」的模型不能選。被選中的模型不能退役或移入回收桶。
        </p>
        <div className="space-y-3">
          {ZONES.map(([zone, label, hint]) => (
            <Field key={zone} label={`${label}模型`} hint={hint}>
              <select className={inputClass} value={current[zone] ?? ''} onChange={(e) => setDraft({ ...draft, [zone]: e.target.value || null })}>
                <option value="">（不使用）</option>
                {p.options[zone].map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.id}・{o.stage === 'clinical' ? '臨床上線' : '候選'}
                    {o.score != null ? `・交叉驗證 ${fmt(o.score)}` : ''}
                  </option>
                ))}
              </select>
            </Field>
          ))}
          <Field label="雙機展示的上傳連接埠" hint="A 電腦用瀏覽器連到這個連接埠上傳影像（只限區網、只能上傳）">
            <input type="number" min={1024} max={65535} className={inputClass} value={port ?? settings.data.clinical_receiver_port} onChange={(e) => setPort(Number(e.target.value))} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              disabled={save.busy || (!Object.keys(draft).length && port == null)}
              onClick={async () => {
                if (await save.run()) {
                  setDraft({})
                  setPort(null)
                  void settings.reload()
                  void plan.reload()
                }
              }}
            >
              儲存醫師端設定
            </Button>
            <Button
              icon={Flame}
              disabled={warm.busy || !Object.values(p.current.zones).some((z) => z.model_id)}
              onClick={async () => {
                const r = await warm.run()
                if (r) setJob(r.job_id)
              }}
            >
              預先載入模型
            </Button>
          </div>
          <ErrorNote error={save.error ?? warm.error} />
          {job && <JobProgress jobId={job} onDone={() => void plan.reload()} />}
        </div>
      </Panel>

      <div className="space-y-5">
        <Panel title="目前狀態">
          <ul className="space-y-2 text-[14px]">
            {ZONES.map(([zone, label]) => {
              const z = p.current.zones[zone]
              return (
                <li key={zone} className="flex flex-wrap items-center gap-2">
                  <span className="w-20 text-ink-soft">{label}</span>
                  {z.model_id ? <span className="font-medium">{z.model_id}</span> : <span className="text-ink-faint">不使用</span>}
                  {z.candidate && <Pill tone="amber">{p.current.candidate_label}</Pill>}
                  {z.stage === 'clinical' && <Pill tone="ok">臨床上線</Pill>}
                </li>
              )
            })}
          </ul>
          {p.current.problems.map((m) => (
            <p key={m} className="mt-2 text-[13px] text-alert">
              {m}
            </p>
          ))}
          <p className="mt-3 text-[13px] text-ink-soft">
            已預先載入：{p.loaded.length ? p.loaded.map((l) => `${l.model_id}（${l.device}）`).join('、') : '沒有'}。按「開始接收」時也會自動預先載入；顯示卡正在訓練時改用 CPU。
          </p>
        </Panel>
        <Panel title="超音波機器模式">
          <p className="text-[14px] text-ink-soft">
            接超音波機器時，報告會輸出姓名與病歷號（只存在醫師端受限區）。需要 IRB／醫院同意，會在 M3 第二階段（階段 F）提供，目前不能開啟。
          </p>
          <p className="mt-2">
            <Pill>{settings.data.clinical_device_mode ? '已開啟' : '關閉'}</Pill>
          </p>
        </Panel>
      </div>
    </div>
  )
}
