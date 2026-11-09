import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FlaskConical, ShieldCheck } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { fmt, stageLabel, taskLabel, type EvaluationInfo, type ModelInfo } from '../../api/ml'
import { zoneHome } from '../../api/ml'
import { BackLink, Button, Field, KeyValue, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ConfirmDialog } from '../../components/overlays'
import { ErrorNote, JobProgress, Loading } from '../../components/live'
import { EvaluationReport, evaluationHeadline } from '../../components/EvaluationReport'
import { stageTone } from './Registry'
import { OpenFolderButton } from '../../components/OpenFolder'

interface Detail extends ModelInfo {
  manifest: Record<string, unknown> & { training: { run_id: string; dataset_version_id: string; split_id: string }; temperature: number; ensemble: Record<string, string> }
  model_card: string
  evaluations: EvaluationInfo[]
}

interface Readiness {
  split_id: string
  locked: boolean
  patients: number
  images: number
  unverified_masks: number
  missing_features: number
  missing_masks: number
  ready: boolean
}

export default function ModelDetail() {
  const { modelId = '' } = useParams()
  const model = useApi<Detail>(`/models/${modelId}`)
  const readiness = useApi<Readiness>(`/models/${modelId}/test-readiness`)
  const people = useApi<{ people: { name: string; kind: string; active: boolean }[] }>('/people')
  const [stageOpen, setStageOpen] = useState<string | null>(null)
  const [approver, setApprover] = useState('')
  const [testOpen, setTestOpen] = useState(false)
  const [testJob, setTestJob] = useState<string | null>(null)
  const setStage = useAction((stage: string, confirm: string) => api.post(`/models/${modelId}/stage`, { stage, confirm_name: confirm, approver }))
  const startTest = useAction((confirm: string) => api.post<{ job_id: string }>(`/models/${modelId}/test`, { confirm }))

  if (model.loading && !model.data) return <Loading />
  if (!model.data) return <ErrorNote error={model.error} />
  const m = model.data
  const physicians = people.data?.people.filter((p) => p.kind === 'physician' && p.active) ?? []
  const nextStages = ['research', 'candidate', 'clinical', 'retired'].filter((s) => s !== m.stage)
  const test = m.evaluations.find((e) => e.target === 'test')

  return (
    <>
      <BackLink to={zoneHome[m.task].models}>回{zoneHome[m.task].label}模型</BackLink>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-bold leading-tight">{m.id}</h1>
          <p className="text-ink-soft">
            {taskLabel[m.task]}・由 <Link to={`/research/training/${m.manifest.training.run_id}`} className="text-steel underline">{m.manifest.training.run_id}</Link> 註冊・{m.created_at.slice(0, 10)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={stageTone(m.stage)}>{m.stage_label}</Pill>
          <OpenFolderButton kind="model" id={m.id} />
          {nextStages.map((s) => (
            <Button key={s} variant={s === 'clinical' ? 'primary' : 'secondary'} icon={s === 'clinical' ? ShieldCheck : undefined} onClick={() => setStageOpen(s)}>
              改為{stageLabel[s]}
            </Button>
          ))}
        </div>
      </div>
      <ErrorNote error={setStage.error} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel title="模型卡">
            <ModelCard text={m.model_card} />
          </Panel>
          <Panel title="評估紀錄" flush>
            {m.evaluations.length ? (
              <Table
                minWidth={520}
                head={['編號', '對象', '時間', '結果', '']}
                rows={m.evaluations.map((e) => [
                  e.id,
                  e.target === 'test' ? '固定測試集' : '交叉驗證',
                  `${e.created_at.slice(0, 16).replace('T', ' ')}・${e.created_by}`,
                  evaluationHeadline(e.metrics as Record<string, unknown>),
                  <OpenFolderButton key="f" kind="evaluation" id={e.id} label="資料夾" />,
                ])}
              />
            ) : (
              <p className="px-5 py-4 text-[14px] text-ink-soft">還沒有評估。交叉驗證的評估在訓練詳細頁；固定測試集在右側。</p>
            )}
          </Panel>
          {test && (
            <Panel title="固定測試集結果" flush>
              <EvaluationReport report={test.metrics as Record<string, unknown>} />
            </Panel>
          )}
        </div>

        <div className="space-y-5">
          <Panel title="合約與檔案">
            <KeyValue
              items={[
                ['合約版本', String(m.manifest.contract_version)],
                ['資料集版本', m.manifest.training.dataset_version_id],
                ['切分', m.manifest.training.split_id],
                ['集成模型數', String(Object.keys(m.manifest.ensemble).length)],
                ['校準溫度', fmt(m.manifest.temperature)],
                ['特徵', m.features ? `${m.features.feature_set_id}：${m.features.columns.join('、')}` : '只用影像'],
              ]}
            />
          </Panel>
          <Panel title="固定測試集（只能一次）">
            {readiness.data ? (
              <>
                <KeyValue
                  items={[
                    ['切分', readiness.data.split_id],
                    ['測試集', `${readiness.data.patients} 位病人、${readiness.data.images} 張影像`],
                    ...(m.task === 'segmentation'
                      ? ([['缺少醫師遮罩的病人側', String(readiness.data.unverified_masks)]] as [string, string][])
                      : ([['缺少輸入的測試影像', `遮罩 ${readiness.data.missing_masks} 張、量測特徵 ${readiness.data.missing_features} 張`]] as [string, string][])),
                    ['狀態', readiness.data.locked ? '已評估過（鎖定）' : readiness.data.ready ? '可以評估' : '尚未就緒'],
                  ]}
                />
                {m.task === 'segmentation' && readiness.data.unverified_masks > 0 && (
                  <p className="mt-2 text-[13px] text-amber">分割模型的最後評估需要每個測試病人側至少 1 張醫師上傳或人工確認的遮罩，請先在「標註與回饋 › 醫師圈選」完成測試集批次。</p>
                )}
                {m.task !== 'segmentation' && readiness.data.missing_masks + readiness.data.missing_features > 0 && (
                  <p className="mt-2 text-[13px] text-amber">這個模型需要遮罩組的遮罩或量測特徵，但部分測試影像沒有。請用同一個資料集版本產生遮罩組與特徵集。</p>
                )}
                <div className="mt-3">
                  <Button icon={FlaskConical} disabled={!readiness.data.ready || Boolean(testJob)} onClick={() => setTestOpen(true)}>
                    評估固定測試集
                  </Button>
                </div>
                {testJob && (
                  <div className="mt-3">
                    <JobProgress
                      jobId={testJob}
                      onDone={() => {
                        void model.reload()
                        void readiness.reload()
                      }}
                    />
                  </div>
                )}
              </>
            ) : (
              <Loading />
            )}
            <ErrorNote error={startTest.error ?? readiness.error} />
          </Panel>
          <Panel title="階段紀錄">
            <ul className="space-y-1 text-[14px]">
              {m.stage_history.map((h, i) => (
                <li key={i}>
                  {h.at.slice(0, 16).replace('T', ' ')}・{stageLabel[h.stage]}・{h.by}
                  {h.approver ? `（核准：${h.approver}）` : ''}
                  {h.note ? `・${h.note}` : ''}
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <ConfirmDialog
        open={stageOpen !== null}
        title={`改為「${stageLabel[stageOpen ?? 'research']}」`}
        confirmLabel="確認變更"
        danger={stageOpen === 'clinical'}
        requireText={stageOpen === 'clinical' ? m.id : undefined}
        onClose={() => setStageOpen(null)}
        onConfirm={async () => {
          if (await setStage.run(stageOpen ?? '', m.id)) {
            setStageOpen(null)
            void model.reload()
          }
        }}
      >
        {stageOpen === 'clinical' ? (
          <div className="space-y-3">
            <p>醫師端會開始使用這個模型；同任務原本的臨床模型會改回「候選」。</p>
            <Field label="核准醫師">
              <select className={inputClass} value={approver} onChange={(e) => setApprover(e.target.value)}>
                <option value="">請選擇</option>
                {physicians.map((p) => (
                  <option key={p.name}>{p.name}</option>
                ))}
              </select>
            </Field>
            {!physicians.length && <p className="text-[13px] text-amber">醫師名單是空的，請先到「設定 › 醫師與操作者名單」新增。</p>}
          </div>
        ) : (
          <p>變更會記錄在階段紀錄與稽核紀錄。</p>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={testOpen}
        title="評估固定測試集"
        confirmLabel="開始評估"
        danger
        requireText={m.id}
        onClose={() => setTestOpen(false)}
        onConfirm={async () => {
          const res = await startTest.run(m.id)
          setTestOpen(false)
          if (res) setTestJob(res.job_id)
        }}
      >
        <p>固定測試集只能評估一次，之後這個切分就會鎖定，避免依測試結果反覆調整模型。請確定這是最後要報告的模型。</p>
      </ConfirmDialog>
    </>
  )
}

/** 模型卡（markdown 的標題與條列）排成一般文字，不顯示 # 與 - 符號；第一行標題已在頁首，略過。 */
function ModelCard({ text }: { text: string }) {
  const blocks: { title: string; items: string[] }[] = []
  for (const line of text.split('\n')) {
    if (line.startsWith('## ')) blocks.push({ title: line.slice(3), items: [] })
    else if (line.startsWith('- ')) {
      if (!blocks.length) blocks.push({ title: '', items: [] })
      blocks[blocks.length - 1].items.push(line.slice(2))
    }
  }
  return (
    <div className="space-y-4 text-[14px] leading-6">
      {blocks.map((b, i) => (
        <section key={i}>
          {b.title && <h3 className="mb-1 font-semibold text-ink">{b.title}</h3>}
          <ul className="list-disc space-y-1 pl-5">
            {b.items.map((item, j) => {
              const k = item.indexOf('：')
              return (
                <li key={j}>
                  {k > 0 ? (
                    <>
                      <span className="text-ink-soft">{item.slice(0, k)}：</span>
                      {item.slice(k + 1)}
                    </>
                  ) : (
                    item
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
