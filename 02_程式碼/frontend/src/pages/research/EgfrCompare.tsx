import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Calculator, FileDown, FlaskConical, Lock, Play } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import { fmt, runStatusLabel, type RunStatus } from '../../api/ml'
import { ConfusionMatrix } from '../../components/charts'
import { BackLink, Button, Field, KeyValue, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../components/live'
import { ConfirmDialog, Drawer } from '../../components/overlays'
import { OpenFolderButton } from '../../components/OpenFolder'
import { runTone } from './Training'

interface CellMetrics {
  n_patients?: number
  auc_lt60?: number | null
  auc_lt60_ci?: [number | null, number | null] | null
  auc_lt30?: number | null
  auc_lt30_ci?: [number | null, number | null] | null
  qwk?: number | null
  qwk3?: number | null
  mae?: number | null
  accuracy?: number | null
  brier_lt60?: number | null
  ece_lt60?: number | null
  sensitivity?: number | null
  specificity?: number | null
  classes?: string[]
  confusion?: number[][]
  confusion3?: number[][]
  per_class_recall?: (number | null)[]
  class_counts?: number[]
}

interface Cell {
  code: string
  k: number
  run_id: string
  reused: boolean
  label: string
  status: RunStatus | 'missing'
  name: string
  metrics: CellMetrics
  test: { evaluation_id: string; auc_lt60: number | null; auc_lt60_ci: [number | null, number | null] | null; created_at: string } | null
}

interface Detail {
  id: string
  name: string
  created_at: string
  created_by: string
  config: { codes: string[]; ks: number[]; split_id: string; dataset_version_id: string; mask_set_id: string | null }
  cells: Cell[]
  labels: Record<string, string>
  primary: { a: string; b: string; k: number; metric: string }[]
}

interface Pairwise {
  run_a: string
  run_b: string
  metric: string
  patients: number
  a: number | null
  b: number | null
  diff: number | null
  ci: [number | null, number | null]
  p: number | null
  fold_ttest: { mean_diff: number | null; p: number | null; folds: number } | null
}

const METRICS: [keyof CellMetrics, string, string][] = [
  ['auc_lt60', 'AUC(<60)', '共同的尺：所有類別數都能比'],
  ['auc_lt30', 'AUC(<30)', '3、5 類'],
  ['qwk3', 'QWK（3 類）', '5 類合併成 3 類後的一致性'],
  ['qwk', 'QWK', '同類別數內比較'],
  ['mae', 'MAE（類）', '平均差幾類，越小越好'],
  ['accuracy', '準確率', ''],
]
const PAIR_METRICS: [string, string][] = [
  ['auc_lt60', 'AUC(<60)'],
  ['auc_lt30', 'AUC(<30)'],
  ['qwk3', 'QWK（3 類）'],
  ['qwk', 'QWK（同類別數）'],
]
const ci = (v?: [number | null, number | null] | null) => (v && v[0] != null && v[1] != null ? `${v[0].toFixed(3)}–${v[1].toFixed(3)}` : '')

/** eGFR 比較頁：列＝輸入方式 ①–⑥，欄＝2／3／5 類；兩兩比較用病人層級配對 bootstrap（決策 D24、D33）。 */
export default function EgfrCompare() {
  const { experimentId = '' } = useParams()
  const data = useApi<Detail>(`/egfr/comparisons/${experimentId}`, [experimentId])
  const live = Boolean(data.data?.cells.some((c) => c.status === 'running' || c.status === 'queued'))
  usePolling(data.reload, 5000, live)
  const [metric, setMetric] = useState<keyof CellMetrics>('auc_lt60')
  const [open, setOpen] = useState<Cell | null>(null)
  const [pair, setPair] = useState({ a: '', b: '', metric: 'auc_lt60' })
  const [result, setResult] = useState<Pairwise | null>(null)
  const [exported, setExported] = useState<string | null>(null)
  const start = useAction(() => api.post<{ jobs: string[] }>(`/egfr/comparisons/${experimentId}/start`))
  const exp = useAction(() => api.post<{ folder: string }>(`/egfr/comparisons/${experimentId}/export`))
  const compare = useAction((a: string, b: string, m: string) => api.get<Pairwise>(`/egfr/pairwise?a=${a}&b=${b}&metric=${m}`))

  if (!data.data) return data.error ? <ErrorNote error={data.error} /> : <Loading />
  const d = data.data
  const cell = (code: string, k: number) => d.cells.find((c) => c.code === code && c.k === k)
  const done = d.cells.filter((c) => c.status === 'completed')
  const pending = d.cells.filter((c) => !c.reused && ['draft', 'failed', 'stopped', 'interrupted'].includes(c.status)).length
  const runCompare = async (a: string, b: string, m: string) => {
    setPair({ a, b, metric: m })
    const r = await compare.run(a, b, m)
    if (r) setResult(r)
  }
  const labelOf = (runId: string) => {
    const c = d.cells.find((x) => x.run_id === runId)
    return c ? `${c.label}・${c.k} 類` : runId
  }

  return (
    <>
      <BackLink to="/research/egfr">回 eGFR 訓練</BackLink>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-bold leading-tight">
            {d.id}
            {d.name && d.name !== d.id ? `・${d.name}` : ''}
          </h1>
          <p className="text-ink-soft">
            {d.config.dataset_version_id}・{d.config.split_id}
            {d.config.mask_set_id ? `・遮罩組 ${d.config.mask_set_id}` : ''}・{d.created_at.slice(0, 10)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {pending > 0 && (
            <Button
              variant="primary"
              icon={Play}
              disabled={start.busy}
              onClick={async () => {
                if (await start.run()) void data.reload()
              }}
            >
              開始 {pending} 個未訓練的
            </Button>
          )}
          <Button
            icon={FileDown}
            disabled={exp.busy || !done.length}
            onClick={async () => {
              const r = await exp.run()
              if (r) setExported(r.folder)
            }}
          >
            匯出 CSV
          </Button>
          {exported && <OpenFolderButton kind="relpath" id={exported} label="開啟匯出資料夾" />}
        </div>
      </div>
      <ErrorNote error={start.error ?? exp.error} />

      <Panel
        title="比較格（病人層級、交叉驗證）"
        aside={
          <select className={inputClass} value={metric} onChange={(e) => setMetric(e.target.value as keyof CellMetrics)} aria-label="指標">
            {METRICS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        }
      >
        <p className="mb-3 text-[13px] text-ink-soft">{METRICS.find((m) => m[0] === metric)?.[2]}。點一格看完整報告與混淆矩陣。</p>
        <Table
          minWidth={560}
          head={['輸入方式', ...d.config.ks.map((k) => `${k} 類`)]}
          rows={d.config.codes.map((code) => [
            d.labels[code],
            ...d.config.ks.map((k) => {
              const c = cell(code, k)
              if (!c) return '—'
              const value = c.metrics[metric]
              const ciValue = metric === 'auc_lt60' ? c.metrics.auc_lt60_ci : metric === 'auc_lt30' ? c.metrics.auc_lt30_ci : null
              return (
                <button key={k} className="w-full rounded px-1 py-1 text-left hover:bg-paper" onClick={() => setOpen(c)}>
                  {c.status === 'completed' ? (
                    <>
                      <span className="text-[16px] font-semibold tabular-nums">{typeof value === 'number' ? value.toFixed(3) : '—'}</span>
                      {ciValue && <span className="block text-[12px] text-ink-faint">{ci(ciValue)}</span>}
                      {c.reused && <span className="block text-[12px] text-ink-faint">沿用 {c.run_id}</span>}
                    </>
                  ) : (
                    <Pill tone={c.status === 'missing' ? 'alert' : runTone(c.status)}>{c.status === 'missing' ? '找不到' : runStatusLabel[c.status]}</Pill>
                  )}
                </button>
              )
            }),
          ])}
        />
      </Panel>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Panel title="預先指定的主要比較">
          <ul className="space-y-2 text-[14px]">
            {d.primary.map((p) => {
              const a = cell(p.a, p.k)
              const b = cell(p.b, p.k)
              const ok = a?.status === 'completed' && b?.status === 'completed'
              const absent = !a || !b
              return (
                <li key={`${p.a}-${p.b}`} className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    {d.labels[p.a]} vs {d.labels[p.b]}（{p.k} 類，AUC(&lt;60)）
                  </span>
                  <Button variant="ghost" icon={Calculator} disabled={!ok || compare.busy} onClick={() => a && b && void runCompare(a.run_id, b.run_id, p.metric)}>
                    {ok ? '計算' : absent ? '不在這組' : '尚未完成'}
                  </Button>
                </li>
              )
            })}
          </ul>
          <p className="mt-3 text-[12px] text-ink-faint">第一列是預先指定的主要比較（決策 D33）；其餘為次要，報告時註明多重比較。</p>
        </Panel>
        <Panel title="兩兩比較（配對 bootstrap）">
          <div className="grid gap-3 sm:grid-cols-3">
            {(['a', 'b'] as const).map((side) => (
              <Field key={side} label={side === 'a' ? '模型 A' : '模型 B'}>
                <select className={inputClass} value={pair[side]} onChange={(e) => setPair({ ...pair, [side]: e.target.value })}>
                  <option value="">請選擇</option>
                  {done.map((c) => (
                    <option key={c.run_id} value={c.run_id}>
                      {c.label}・{c.k} 類
                    </option>
                  ))}
                </select>
              </Field>
            ))}
            <Field label="指標">
              <select className={inputClass} value={pair.metric} onChange={(e) => setPair({ ...pair, metric: e.target.value })}>
                {PAIR_METRICS.map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="mt-3">
            <Button icon={Calculator} disabled={!pair.a || !pair.b || pair.a === pair.b || compare.busy} onClick={() => void runCompare(pair.a, pair.b, pair.metric)}>
              比較
            </Button>
          </div>
          <ErrorNote error={compare.error} />
          {result && (
            <div className="mt-4">
              <KeyValue
                items={[
                  ['A', `${labelOf(result.run_a)}：${fmt(result.a)}`],
                  ['B', `${labelOf(result.run_b)}：${fmt(result.b)}`],
                  ['差異（A − B）', result.diff == null ? '—' : `${result.diff >= 0 ? '+' : ''}${result.diff.toFixed(3)}`],
                  ['95% 信賴區間', result.ci[0] == null ? '—' : `${result.ci[0]!.toFixed(3)} 到 ${result.ci[1]!.toFixed(3)}`],
                  ['p 值（配對 bootstrap）', fmt(result.p)],
                  ['逐折校正 t 檢定 p', result.fold_ttest ? fmt(result.fold_ttest.p) : '—'],
                  ['共同病人數', result.patients],
                ]}
              />
              <p className="mt-2 text-[13px] text-ink-soft">
                {result.ci[0] != null && result.ci[1] != null && (result.ci[0] > 0 || result.ci[1] < 0) ? '信賴區間不含 0：兩者有差異。' : '信賴區間含 0：看不出差異。'}
              </p>
            </div>
          )}
        </Panel>
      </div>

      <TestSetPanel current={d.id} splitId={d.config.split_id} labels={d.labels} cells={d.cells} />

      <Drawer open={Boolean(open)} title={open ? `${open.label}・${open.k} 類` : ''} onClose={() => setOpen(null)}>
        {open && (
          <div className="space-y-4 text-[14px]">
            <p>
              <Link to={`/research/training/${open.run_id}`} className="text-steel underline">
                {open.run_id}
              </Link>
              {open.reused && '（沿用已完成的訓練）'}
            </p>
            {open.status !== 'completed' ? (
              <p className="text-ink-soft">還沒完成（{open.status === 'missing' ? '找不到' : runStatusLabel[open.status]}）。</p>
            ) : (
              <>
                <KeyValue
                  items={[
                    ['病人數', open.metrics.n_patients ?? '—'],
                    ['AUC(<60)', `${fmt(open.metrics.auc_lt60)}　${ci(open.metrics.auc_lt60_ci)}`],
                    ...(open.k >= 3
                      ? ([
                          ['AUC(<30)', `${fmt(open.metrics.auc_lt30)}　${ci(open.metrics.auc_lt30_ci)}`],
                          ['QWK', fmt(open.metrics.qwk)],
                          ['QWK（3 類）', fmt(open.metrics.qwk3)],
                          ['MAE（類）', fmt(open.metrics.mae)],
                        ] as [string, string][])
                      : ([
                          ['敏感度', fmt(open.metrics.sensitivity)],
                          ['特異度', fmt(open.metrics.specificity)],
                        ] as [string, string][])),
                    ['準確率', fmt(open.metrics.accuracy)],
                    ['Brier(<60)', fmt(open.metrics.brier_lt60)],
                    ['ECE(<60)', fmt(open.metrics.ece_lt60)],
                  ]}
                />
                {open.metrics.confusion && open.metrics.classes && (
                  <div>
                    <p className="mb-1 font-medium">混淆矩陣（{open.k} 類）</p>
                    <ConfusionMatrix labels={open.metrics.classes} matrix={open.metrics.confusion} />
                  </div>
                )}
                {open.metrics.confusion3 && (
                  <div>
                    <p className="mb-1 font-medium">合併成 3 類</p>
                    <ConfusionMatrix labels={['≥60', '30–59', '<30']} matrix={open.metrics.confusion3} />
                  </div>
                )}
                {open.metrics.per_class_recall && open.metrics.classes && (
                  <div>
                    <p className="mb-1 font-medium">各類敏感度</p>
                    <ul className="text-[13px]">
                      {open.metrics.classes.map((c, i) => (
                        <li key={c}>
                          {c}：{fmt(open.metrics.per_class_recall?.[i])}（{open.metrics.class_counts?.[i] ?? 0} 位）
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <a href={`/api/training/runs/${open.run_id}/oof.csv`} className="text-steel underline">
                  下載每位病人的機率（CSV）
                </a>
              </>
            )}
          </div>
        )}
      </Drawer>
    </>
  )
}

interface GroupRow {
  id: string
  name: string
  created_at: string
  codes: string[]
  ks: number[]
  members: number
  completed: number
  split_id: string
}

interface Readiness {
  split_id: string
  locked: boolean
  members: number
  unfinished: string[]
  missing_inputs: Record<string, { missing_features: number; missing_masks: number }>
  other_unfinished_groups: string[]
  ready: boolean
}

interface TestResult {
  split_id: string
  evaluations: { run_id: string; code: string; k: number; evaluation_id: string; auc_lt60: number | null; auc_lt60_ci: [number | null, number | null] | null }[]
}

/** 固定測試集：勾選同一個切分的比較組一起評估，一次鎖定（決策 D27）。 */
function TestSetPanel({ current, splitId, labels, cells }: { current: string; splitId: string; labels: Record<string, string>; cells: Cell[] }) {
  const groups = useApi<{ comparisons: GroupRow[] }>('/egfr/comparisons')
  const same = (groups.data?.comparisons ?? []).filter((g) => g.split_id === splitId)
  const [picked, setPicked] = useState<string[]>([current])
  const ids = picked.filter((id) => same.some((g) => g.id === id)).sort()
  const readiness = useApi<Readiness>(ids.length ? `/egfr/test-readiness?experiment_ids=${ids.join(',')}` : null, [ids.join(',')])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [job, setJob] = useState<string | null>(null)
  const [result, setResult] = useState<TestResult | null>(null)
  const start = useAction(() => api.post<{ job_id: string }>('/egfr/test', { experiment_ids: ids, confirm: splitId }))
  const r = readiness.data
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  return (
    <Panel title="固定測試集（只能評估一次）" className="mt-5">
      <p className="mb-3 text-[14px] text-ink-soft">
        勾選要一起評估的比較組（必須是同一個切分 {splitId}）。全部一起評估、一起鎖定：評估後這個切分的 eGFR 測試集就不能再用，但不影響分割與回音分級的測試集。
      </p>
      {groups.loading && !groups.data ? (
        <Loading />
      ) : (
        <ul className="mb-3 space-y-1 text-[14px]">
          {same.map((g) => (
            <li key={g.id}>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={picked.includes(g.id)} disabled={Boolean(r?.locked)} onChange={() => toggle(g.id)} />
                <span className="font-medium">{g.id}</span>
                <span className="text-ink-soft">
                  {g.name}・{g.completed}／{g.members} 完成
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {r && (
        <div className="mb-3 space-y-1 text-[14px]">
          {r.locked ? (
            <p className="flex items-center gap-1 text-ink-soft">
              <Lock size={14} aria-hidden /> 這個切分的 eGFR 固定測試集已經評估過；結果列在下面，完整報告在各訓練詳細頁的「固定測試集結果」。
            </p>
          ) : (
            <>
              <p>
                共 {r.members} 個模型
                {r.unfinished.length > 0 ? <span className="text-alert">，還有 {r.unfinished.length} 個訓練沒完成，全部完成後才能評估。</span> : '，都已完成。'}
              </p>
              {Object.entries(r.missing_inputs).map(([run, g]) => (
                <p key={run} className="text-alert">
                  {run} 的測試影像缺少輸入（遮罩 {g.missing_masks} 張、量測特徵 {g.missing_features} 張）：請用同一個資料集版本產生遮罩組與特徵集。
                </p>
              ))}
              {r.other_unfinished_groups.length > 0 && (
                <p className="text-amber">
                  同一個切分還有比較組沒訓練完（{r.other_unfinished_groups.join('、')}）。測試集只能用一次，建議等它們完成後一起勾選評估。
                </p>
              )}
            </>
          )}
        </div>
      )}
      <Button variant="primary" icon={FlaskConical} disabled={!r?.ready || start.busy || Boolean(job)} onClick={() => setConfirmOpen(true)}>
        評估固定測試集
      </Button>
      <ErrorNote error={start.error ?? readiness.error ?? groups.error} />
      {job && (
        <div className="mt-3">
          <JobProgress
            jobId={job}
            onDone={(j) => {
              if (j.status === 'completed') setResult(j.result as unknown as TestResult)
              void readiness.reload()
            }}
          />
        </div>
      )}
      {!result && cells.some((c) => c.test) && (
        <div className="mt-4">
          <Table
            minWidth={520}
            head={['模型（這一組）', '病人層級 AUC(<60)', '95% 信賴區間', '評估']}
            rows={cells
              .filter((c) => c.test)
              .map((c) => [
                `${c.label}・${c.k} 類`,
                fmt(c.test!.auc_lt60),
                ci(c.test!.auc_lt60_ci) || '—',
                <Link key="r" to={`/research/training/${c.run_id}`} className="text-steel underline">
                  {c.test!.evaluation_id}
                </Link>,
              ])}
          />
        </div>
      )}
      {result && (
        <div className="mt-4">
          <Table
            minWidth={520}
            head={['模型', '病人層級 AUC(<60)', '95% 信賴區間', '訓練']}
            rows={result.evaluations.map((e) => [
              `${labels[e.code] ?? e.code}・${e.k} 類`,
              fmt(e.auc_lt60),
              ci(e.auc_lt60_ci) || '—',
              <Link key="r" to={`/research/training/${e.run_id}`} className="text-steel underline">
                {e.run_id}
              </Link>,
            ])}
          />
        </div>
      )}
      <ConfirmDialog
        open={confirmOpen}
        title="評估 eGFR 固定測試集"
        confirmLabel="開始評估"
        danger
        requireText={splitId}
        onClose={() => setConfirmOpen(false)}
        onConfirm={async () => {
          setConfirmOpen(false)
          const res = await start.run()
          if (res) setJob(res.job_id)
        }}
      >
        <p>
          將評估 {ids.join('、')} 的 {r?.members ?? 0} 個模型。評估後這個切分的 eGFR 測試集會鎖定，之後不能再評估（包括之後新建的比較組）。請輸入切分編號 {splitId} 確認。
        </p>
      </ConfirmDialog>
    </Panel>
  )
}

/** eGFR 比較組清單（側邊欄「eGFR 比較」）。 */
export function EgfrCompareIndex() {
  const groups = useApi<{ comparisons: { id: string; name: string; created_at: string; codes: string[]; ks: number[]; members: number; completed: number }[] }>('/egfr/comparisons')
  return (
    <>
      <BackLink to="/research/egfr">回 eGFR 訓練</BackLink>
      <h1 className="mb-4 text-[24px] font-bold leading-tight">eGFR 比較</h1>
      <Panel flush>
        {groups.data?.comparisons.length ? (
          <Table
            minWidth={600}
            head={['比較組', '名稱', '輸入方式 × 類別數', '進度', '建立']}
            rows={groups.data.comparisons.map((g) => [
              <Link key="id" to={`/research/egfr/compare/${g.id}`} className="font-medium text-steel hover:underline">
                {g.id}
              </Link>,
              g.name,
              `${g.codes.length} × ${g.ks.join('／')} 類`,
              `${g.completed}／${g.members} 完成`,
              g.created_at.slice(0, 10),
            ])}
          />
        ) : (
          <p className="px-5 py-4 text-[14px] text-ink-soft">
            還沒有比較組。到 <Link to="/research/egfr" className="text-steel underline">eGFR 訓練</Link> 勾選輸入方式與類別數建立。
          </p>
        )}
        <ErrorNote error={groups.error} />
      </Panel>
    </>
  )
}
