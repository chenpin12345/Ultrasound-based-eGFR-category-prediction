import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileDown, Sigma } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import { fmt, type FeatureSetInfo, type RunInfo } from '../../api/ml'
import { Button, EmptyState, Field, KeyValue, PageHeader, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'
import { OpenFolderButton } from '../../components/OpenFolder'

interface SideStat {
  n: number
  rho: number
  p: number
  median: number
}

interface Analysis {
  rows: number
  reliable: number
  by_side: Record<'right' | 'left', { ref_organ: string; n: number; ratio_mean?: SideStat; ratio_median?: SideStat; p_index?: SideStat }>
  length_vs_dist_a: { n: number; mean_diff_mm?: number; sd_mm?: number; loa_low_mm?: number; loa_high_mm?: number }
  unreliable_reasons: Record<string, number>
}

interface Row {
  image_id: string
  patient_id: string
  side: string | null
  ref_organ: string | null
  length_mm: number | null
  dist_a_mm: number | null
  ratio_mean: number | null
  ratio_median: number | null
  p_index: number | null
  depth_diff_mm: number | null
  reliable: boolean
  reasons: string
}

const stat = (s?: SideStat) => (s ? `ρ = ${fmt(s.rho)}（p ${s.p < 0.001 ? '< 0.001' : `= ${fmt(s.p)}`}，n = ${s.n}，中位數 ${fmt(s.median)}）` : '資料不足')

export default function Features() {
  const sets = useApi<{ feature_sets: FeatureSetInfo[] }>('/features')
  const runs = useApi<{ runs: RunInfo[] }>('/training/runs?task=segmentation')
  usePolling(sets.reload, 4000, Boolean(sets.data?.feature_sets.some((f) => f.status === 'running')))
  const [selected, setSelected] = useState('')
  const shown = selected || sets.data?.feature_sets.find((f) => f.status === 'completed')?.id || ''
  const shownStatus = sets.data?.feature_sets.find((f) => f.id === shown)?.status
  // 計算完成才讀取；狀態改變時重新讀取
  const detail = useApi<{ rows: Row[]; total: number; analysis: Analysis }>(shown && shownStatus === 'completed' ? `/features/${shown}?limit=100` : null, [shownStatus])
  const [source, setSource] = useState<'masks' | 'run'>('run')
  const [runId, setRunId] = useState('')
  const segRuns = runs.data?.runs.filter((r) => r.status === 'completed') ?? []
  const create = useAction(() => api.post<{ id: string }>('/features', { source, run_id: source === 'run' ? runId || segRuns[0]?.id : null }))
  const a = detail.data?.analysis
  const shownSet = sets.data?.feature_sets.find((f) => f.id === shown)
  const [exported, setExported] = useState<{ id: string; folder: string } | null>(null)
  const exp = useAction(() => api.post<{ folder: string }>(`/features/${shown}/export`))

  return (
    <>
      <PageHeader title="特徵擷取" description="皮質取腎實質外層帶；參考組織只取和皮質同深度的肝（右腎）或脾（左腎）；排除 caliper 與過曝像素；平均值與中位數都算，左右分開分析。" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          {a ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  icon={FileDown}
                  disabled={exp.busy}
                  onClick={async () => {
                    const r = await exp.run()
                    if (r) setExported({ id: shown, folder: r.folder })
                  }}
                >
                  匯出 {shown}（CSV）
                </Button>
                {exported?.id === shown && <OpenFolderButton kind="relpath" id={exported.folder} label="開啟匯出資料夾" />}
                {shownSet?.relpath && <OpenFolderButton kind="relpath" id={shownSet.relpath} label="開啟特徵集資料夾" />}
                <ErrorNote error={exp.error} />
              </div>
              <Panel title={`${shown}：回音比值與 eGFR（Spearman）`}>
                <KeyValue
                  items={[
                    ['可靠的影像', `${a.reliable}／${a.rows}`],
                    ['右腎／肝：平均值比', stat(a.by_side.right.ratio_mean)],
                    ['右腎／肝：中位數比', stat(a.by_side.right.ratio_median)],
                    ['左腎／脾：平均值比', stat(a.by_side.left.ratio_mean)],
                    ['左腎／脾：中位數比', stat(a.by_side.left.ratio_median)],
                    ['P 指數（探索性）右／左', `${stat(a.by_side.right.p_index)}；${stat(a.by_side.left.p_index)}`],
                  ]}
                />
                <p className="mt-3 text-[13px] text-ink-soft">文獻（排除肝病的病人）皮質／肝比值與 eGFR 約 ρ = −0.5 到 −0.7；比值越高（皮質越亮）eGFR 越低。</p>
              </Panel>
              <Panel title="自動腎長 vs 技師量的 Dist A（Bland-Altman）">
                <KeyValue
                  items={[
                    ['配對數', String(a.length_vs_dist_a.n)],
                    ['平均差（自動 − 技師）', a.length_vs_dist_a.mean_diff_mm == null ? '—' : `${fmt(a.length_vs_dist_a.mean_diff_mm, 1)} mm`],
                    ['95% 一致界限', a.length_vs_dist_a.loa_low_mm == null ? '—' : `${fmt(a.length_vs_dist_a.loa_low_mm, 1)} 到 ${fmt(a.length_vs_dist_a.loa_high_mm, 1)} mm`],
                  ]}
                />
                <p className="mt-3 text-[13px] text-ink-soft">不需要醫師就能檢查分割品質：一致界限越窄，自動量的腎長越接近技師。</p>
              </Panel>
              {Object.keys(a.unreliable_reasons).length > 0 && (
                <Panel title="不可靠的原因" flush>
                  <Table minWidth={360} head={['原因', '張數']} rows={Object.entries(a.unreliable_reasons).sort((x, y) => y[1] - x[1]).map(([k, v]) => [k, v])} />
                </Panel>
              )}
              <Panel title={`逐張影像（前 ${detail.data?.rows.length}／${detail.data?.total}）`} flush>
                <Table
                  minWidth={860}
                  head={['影像', '病人', '側別', '參考', '腎長', 'Dist A', '比值（平均）', '比值（中位數）', '深度差', '可靠']}
                  rows={(detail.data?.rows ?? []).map((r) => [
                    <Link key="i" to={`/research/datasets/images/${r.image_id}`} className="text-steel hover:underline">
                      {r.image_id}
                    </Link>,
                    r.patient_id,
                    r.side === 'right' ? '右' : r.side === 'left' ? '左' : '—',
                    r.ref_organ === 'liver' ? '肝' : r.ref_organ === 'spleen' ? '脾' : '—',
                    fmt(r.length_mm, 1),
                    fmt(r.dist_a_mm, 1),
                    fmt(r.ratio_mean),
                    fmt(r.ratio_median),
                    r.depth_diff_mm == null ? '—' : `${fmt(r.depth_diff_mm, 1)} mm`,
                    r.reliable ? <Pill key="ok" tone="ok">可靠</Pill> : <span key="no" className="text-[12px] text-amber">{r.reasons || '否'}</span>,
                  ])}
                />
              </Panel>
            </>
          ) : shownStatus === 'running' ? (
            <Panel>
              <Loading text={`${shown} 計算中…`} />
            </Panel>
          ) : sets.loading && !sets.data ? (
            <Loading />
          ) : (
            <Panel>
              <EmptyState icon={Sigma} title="還沒有特徵集" body="右側選擇來源後按「擷取特徵」。" />
            </Panel>
          )}
          <ErrorNote error={detail.error} />
        </div>
        <div className="space-y-5">
          <Panel title="擷取特徵">
            <div className="space-y-3">
              <Field label="遮罩來源">
                <select className={inputClass} value={source} onChange={(e) => setSource(e.target.value as 'masks' | 'run')}>
                  <option value="run">分割訓練的 out-of-fold 遮罩（交叉擬合，可用於下游模型）</option>
                  <option value="masks">目前的遮罩（人工或草稿，只能探索）</option>
                </select>
              </Field>
              {source === 'run' && (
                <Field label="分割訓練">
                  <select className={inputClass} value={runId} onChange={(e) => setRunId(e.target.value)}>
                    {segRuns.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.id}・{r.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {source === 'run' && !segRuns.length && <p className="text-[13px] text-amber">還沒有完成的分割訓練。</p>}
              <ErrorNote error={create.error} />
              <Button
                variant="primary"
                icon={Sigma}
                disabled={create.busy || (source === 'run' && !segRuns.length)}
                onClick={async () => {
                  const r = await create.run()
                  if (r) {
                    setSelected(r.id)
                    void sets.reload()
                  }
                }}
              >
                擷取特徵
              </Button>
            </div>
          </Panel>
          <Panel title="特徵集" flush>
            {sets.data?.feature_sets.length ? (
              <ul className="divide-y divide-line">
                {sets.data.feature_sets.map((f) => (
                  <li key={f.id}>
                    <button type="button" onClick={() => setSelected(f.id)} className={`w-full px-5 py-3 text-left text-[14px] ${f.id === shown ? 'bg-steel-wash' : 'hover:bg-paper'}`}>
                      <span className="font-medium">{f.id}</span>
                      <span className="ml-2">{f.spec.cross_fitted ? <Pill tone="ok">交叉擬合</Pill> : <Pill>探索用</Pill>}</span>
                      <span className="block text-[12px] text-ink-faint">
                        {f.spec.source === 'run' ? `來自 ${f.spec.run_id}` : f.spec.source === 'mask_set' ? `遮罩組 ${f.spec.mask_set_id}` : '目前的遮罩'}・{f.status === 'completed' ? `${f.rows} 張` : '計算中…'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-[14px] text-ink-soft">尚無</p>
            )}
          </Panel>
        </div>
      </div>
    </>
  )
}
