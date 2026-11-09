import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BarChart3, PackagePlus, Play, Square } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import { configRows, fmt, metricLabel, modelHref, runStatusLabel, scoreLabel, taskLabel, type RunDetail } from '../../api/ml'
import { zoneHome } from '../../api/ml'
import { BackLink, Button, Field, KeyValue, Panel, Pill, Table, Tabs, inputClass } from '../../components/ui'
import { LineChartPanel } from '../../components/charts'
import { ConfirmDialog } from '../../components/overlays'
import { ErrorNote, JobProgress, Loading } from '../../components/live'
import { EvaluationReport } from '../../components/EvaluationReport'
import { runTone } from './Training'
import { OpenFolderButton } from '../../components/OpenFolder'

const metricRows = (m: Record<string, unknown> | undefined) =>
  Object.entries(m ?? {})
    .filter(([, v]) => typeof v === 'number' || v == null)
    .map(([k, v]) => [metricLabel[k] ?? k, fmt(v)] as [string, string])

export default function TrainingRun() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const run = useApi<RunDetail>(`/training/runs/${runId}`)
  const live = run.data?.status === 'running' || run.data?.status === 'queued'
  usePolling(run.reload, 3000, live)
  const folds = Object.keys(run.data?.history ?? {})
  const [fold, setFold] = useState('')
  const shownFold = fold && folds.includes(fold) ? fold : folds[folds.length - 1] ?? ''
  const [stopOpen, setStopOpen] = useState(false)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [reg, setReg] = useState({ name: '', version: '1.0.0', note: '' })

  const stop = useAction(() => api.post(`/jobs/${run.data?.job_id}/stop`))
  const start = useAction(() => api.post(`/training/runs/${runId}/start`))
  const evaluate = useAction(() => api.post<Record<string, unknown>>(`/training/runs/${runId}/evaluate`))
  const register = useAction(() => api.post<{ id: string }>('/models', { run_id: runId, ...reg }))
  const [report, setReport] = useState<Record<string, unknown> | null>(null)

  if (run.loading && !run.data) return <Loading />
  if (!run.data) return <ErrorNote error={run.error} />
  const r = run.data
  const history = (r.history[shownFold] ?? []).map((h) => ({ epoch: Number(h.epoch), train_loss: Number(h.train_loss), val_loss: h.val_loss === '' ? null : Number(h.val_loss), val_score: Number(h.val_score) }))
  const cfg = r.effective_config
  const isNnunet = Boolean(r.config.framework)
  const isBaseline = cfg.arch === 'logreg' // ③⑥ 有序邏輯迴歸：沒有逐 epoch 曲線，也不能註冊

  return (
    <>
      <BackLink to={zoneHome[r.task].training}>回{zoneHome[r.task].label}訓練</BackLink>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-bold leading-tight">
            {r.id}・{r.name}
          </h1>
          <p className="text-ink-soft">
            {taskLabel[r.task]}・{isNnunet ? 'nnU-Net v2' : isBaseline ? '有序邏輯迴歸（基準，CPU）' : `${cfg.arch}${cfg.head ? `＋${cfg.head}` : ''}・${cfg.init === 'imagenet' ? 'ImageNet 初始化' : '隨機初始化'}`}・{r.dataset_version_id}・{r.split_id}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={runTone(r.status)}>{runStatusLabel[r.status]}</Pill>
          <OpenFolderButton kind="run" id={r.id} />
          {live && r.job_id && (
            <Button icon={Square} onClick={() => setStopOpen(true)}>
              停止
            </Button>
          )}
          {['draft', 'stopped', 'failed', 'interrupted'].includes(r.status) && !isNnunet && (
            <Button
              icon={Play}
              disabled={start.busy}
              onClick={async () => {
                if (await start.run()) void run.reload()
              }}
            >
              {r.status === 'draft' ? '開始訓練' : '從 checkpoint 恢復'}
            </Button>
          )}
          {r.status === 'completed' && (
            <>
              <Button
                icon={BarChart3}
                disabled={evaluate.busy}
                onClick={async () => {
                  const res = await evaluate.run()
                  if (res) setReport(res)
                }}
              >
                評估交叉驗證
              </Button>
              {!isNnunet && !isBaseline && (
                <Button variant="primary" icon={PackagePlus} onClick={() => setRegisterOpen(true)}>
                  註冊為模型
                </Button>
              )}
            </>
          )}
        </div>
      </div>
      <ErrorNote error={stop.error ?? start.error ?? evaluate.error} />

      {live && r.job_id && (
        <Panel className="mb-5">
          <JobProgress jobId={r.job_id} onDone={() => void run.reload()} />
        </Panel>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Panel title="訓練曲線" aside={folds.length > 1 ? <Tabs label="選擇折" value={shownFold} onChange={setFold} tabs={folds.map((f) => ({ id: f, label: f }))} /> : undefined}>
            {history.length ? (
              <div className="grid gap-4 lg:grid-cols-2">
                <LineChartPanel
                  data={history}
                  xKey="epoch"
                  xLabel="epoch"
                  series={[
                    { key: 'train_loss', label: '訓練 loss', color: '#2F6F8F' },
                    { key: 'val_loss', label: '驗證 loss', color: '#C7772E', dashed: true },
                  ]}
                />
                <LineChartPanel data={history} xKey="epoch" xLabel="epoch" series={[{ key: 'val_score', label: `驗證 ${scoreLabel[r.task]}`, color: '#3E8E5E' }]} />
              </div>
            ) : (
              <p className="text-[14px] text-ink-soft">
                {isNnunet
                  ? 'nnU-Net 的訓練曲線在它自己的紀錄資料夾（04_模型\\nnUNet）。'
                  : isBaseline
                    ? '基準模型（有序邏輯迴歸）一次擬合完成，沒有逐 epoch 的曲線；只用來比較，不能註冊成模型。'
                    : '開始訓練後，每個 epoch 結束會在這裡畫出曲線。'}
              </p>
            )}
          </Panel>

          <Panel title="各折結果（最佳 epoch）" flush>
            {r.summary.folds?.length ? (
              <Table
                minWidth={560}
                head={['折', '最佳 epoch', `最佳 ${scoreLabel[r.task]}`, '跑了幾個 epoch', '訓練／驗證影像']}
                rows={r.summary.folds.map((f) =>
                  f.skipped
                    ? [f.fold, f.skipped, '—', '—', '—']
                    : [f.fold, f.best_epoch ?? '—', fmt(f.best_score), f.epochs_run ?? '—', `${f.train_images ?? '—'}／${f.val_images ?? '—'}`],
                )}
              />
            ) : (
              <p className="px-5 py-4 text-[14px] text-ink-soft">訓練完成後顯示。各折都回報「最佳 epoch」的成績，不是最後一個 epoch。</p>
            )}
          </Panel>

          {(report ?? r.latest_evaluation?.metrics) && (
            <Panel title="交叉驗證評估（含病人層級與 95% 信賴區間）" flush>
              <EvaluationReport report={(report ?? r.latest_evaluation?.metrics) as Record<string, unknown>} />
            </Panel>
          )}

          {r.latest_test && (
            <Panel title={`固定測試集結果（${r.latest_test.created_at.slice(0, 10)}・${r.latest_test.created_by}）`} aside={<OpenFolderButton kind="evaluation" id={r.latest_test.id} label="資料夾" />} flush>
              <EvaluationReport report={r.latest_test.metrics} />
            </Panel>
          )}
        </div>

        <div className="space-y-5">
          <Panel title="交叉驗證摘要">
            <KeyValue
              items={[
                [`平均最佳 ${scoreLabel[r.task]}`, `${fmt(r.summary.mean_best_score)}${r.summary.std_best_score != null ? ` ± ${fmt(r.summary.std_best_score)}` : ''}`],
                ...(r.summary.temperature ? ([['校準溫度', fmt(r.summary.temperature)]] as [string, string][]) : []),
                ...metricRows(r.summary.oof as Record<string, unknown>),
              ]}
            />
          </Panel>
          <Panel title="設定">
            <KeyValue items={configRows(cfg)} />
          </Panel>
        </div>
      </div>

      <ConfirmDialog
        open={stopOpen}
        title="停止訓練"
        confirmLabel="停止"
        onClose={() => setStopOpen(false)}
        onConfirm={async () => {
          setStopOpen(false)
          await stop.run()
          void run.reload()
        }}
      >
        <p>會在安全的位置停下，保留上一個完成的 epoch。之後按「從 checkpoint 恢復」繼續，結果和不中斷相同。</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={registerOpen}
        title="註冊為模型"
        confirmLabel="註冊"
        onClose={() => setRegisterOpen(false)}
        onConfirm={async () => {
          const res = await register.run()
          if (res) {
            setRegisterOpen(false)
            navigate(modelHref(res.id))
          }
        }}
      >
        <div className="space-y-3">
          <p>會複製各折的最佳模型（推論時平均）並寫入模型卡；註冊後檔案不可修改。</p>
          <Field label="名稱" hint="小寫英文、數字、連字號，例如 seg-resnet34">
            <input className={inputClass} value={reg.name} onChange={(e) => setReg({ ...reg, name: e.target.value })} />
          </Field>
          <Field label="版本">
            <input className={inputClass} value={reg.version} onChange={(e) => setReg({ ...reg, version: e.target.value })} />
          </Field>
          <Field label="備註（選填）">
            <input className={inputClass} value={reg.note} onChange={(e) => setReg({ ...reg, note: e.target.value })} />
          </Field>
          <ErrorNote error={register.error} />
        </div>
      </ConfirmDialog>
    </>
  )
}
