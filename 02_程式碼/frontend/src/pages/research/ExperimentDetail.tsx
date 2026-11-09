import { Link, useParams } from 'react-router-dom'
import { Play } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import { fmt, runStatusLabel, scoreLabel, taskLabel, type RunInfo, type TaskId } from '../../api/ml'
import { BackLink, Button, Panel, Pill, Table } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'
import { templateLabel } from './Experiments'
import { runTone } from './Training'

interface Detail {
  id: string
  name: string
  template: string
  note: string
  config: { task: TaskId; dataset_version_id: string; split_id: string; feature_set_id: string | null }
  runs: RunInfo[]
  comparisons: { run_a: string; run_b: string; folds: string[]; mean_diff: number | null; t: number | null; p: number | null }[]
  created_by: string
  created_at: string
}

export default function ExperimentDetail() {
  const { experimentId = '' } = useParams()
  const exp = useApi<Detail>(`/experiments/${experimentId}`)
  const active = Boolean(exp.data?.runs.some((r) => r.status === 'running' || r.status === 'queued'))
  usePolling(exp.reload, 5000, active)
  const startAll = useAction(() => api.post(`/experiments/${experimentId}/start`))

  if (exp.loading && !exp.data) return <Loading />
  if (!exp.data) return <ErrorNote error={exp.error} />
  const e = exp.data
  const label = scoreLabel[e.config.task]
  const name = (id: string) => e.runs.find((r) => r.id === id)?.name ?? id

  return (
    <>
      <BackLink to={e.config.task === 'segmentation' ? '/research/segmentation' : '/research/grading'}>回{e.config.task === 'segmentation' ? '分割' : '回音分級'}訓練</BackLink>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-bold">
            {e.id}・{e.name}
          </h1>
          <p className="text-ink-soft">
            {templateLabel[e.template] ?? e.template}・{taskLabel[e.config.task]}・{e.config.dataset_version_id}・{e.config.split_id}
            {e.config.feature_set_id ? `・特徵 ${e.config.feature_set_id}` : ''}
          </p>
        </div>
        <Button
          variant="primary"
          icon={Play}
          disabled={startAll.busy || !e.runs.some((r) => ['draft', 'stopped', 'failed', 'interrupted'].includes(r.status))}
          onClick={async () => {
            if (await startAll.run()) void exp.reload()
          }}
        >
          全部開始（依序執行）
        </Button>
      </div>
      <ErrorNote error={startAll.error} />
      <div className="space-y-5">
        <Panel title="訓練" flush>
          <Table
            minWidth={640}
            head={['訓練', '變體', '狀態', `平均最佳 ${label}`, 'out-of-fold']}
            rows={e.runs.map((r) => [
              <Link key="id" to={`/research/training/${r.id}`} className="text-steel hover:underline">
                {r.id}
              </Link>,
              r.name,
              <Pill key="s" tone={runTone(r.status)}>
                {runStatusLabel[r.status]}
              </Pill>,
              fmt(r.mean_best_score),
              r.oof ? Object.entries(r.oof).filter(([k, v]) => typeof v === 'number' && ['auc', 'qwk', 'dice', 'accuracy'].includes(k)).map(([k, v]) => `${k} ${fmt(v)}`).join('・') : '—',
            ])}
          />
        </Panel>
        <Panel title={`和第一個完成的訓練比較（逐折 ${label} 差，Nadeau-Bengio 校正 t 檢定）`} flush>
          {e.comparisons.length ? (
            <Table
              minWidth={600}
              head={['訓練', '對照', '平均差', 't', 'p']}
              rows={e.comparisons.map((c) => [name(c.run_a), name(c.run_b), fmt(c.mean_diff), fmt(c.t, 2), c.p == null ? '—' : c.p < 0.001 ? '< 0.001' : fmt(c.p)])}
            />
          ) : (
            <p className="px-5 py-4 text-[14px] text-ink-soft">至少兩個訓練完成後才會比較。折數少時檢定力低，p 值僅供參考。</p>
          )}
        </Panel>
      </div>
    </>
  )
}
