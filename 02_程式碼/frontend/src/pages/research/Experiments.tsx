import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import type { SplitInfo } from '../../api/types'
import type { FeatureSetInfo, TaskId } from '../../api/ml'
import { Button, EmptyState, Field, Panel, Table, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'

interface ExperimentRow {
  id: string
  name: string
  template: string
  config: { task: TaskId; dataset_version_id: string; split_id: string; feature_set_id: string | null }
  runs: number
  completed: number
  created_by: string
  created_at: string
}

export const templateLabel: Record<string, string> = { init: '隨機初始化 vs ImageNet', ablation: '消融實驗 A0–A5', custom: '自訂', egfr_compare: 'eGFR 比較組' }

/** 分割或回音分級的實驗（嵌在各自的訓練頁）。eGFR 的比較在 eGFR 區（決策 D28）。 */
export default function Experiments({ task }: { task: 'segmentation' | 'grade' }) {
  const navigate = useNavigate()
  const list = useApi<{ experiments: ExperimentRow[] }>(`/experiments?task=${task}`, [task])
  const versions = useApi<{ versions: { id: string }[] }>('/dataset-versions')
  const splits = useApi<{ splits: SplitInfo[] }>('/splits')
  const featureSets = useApi<{ feature_sets: FeatureSetInfo[] }>('/features')
  const crossFitted = featureSets.data?.feature_sets.filter((f) => f.spec.cross_fitted && f.status === 'completed') ?? []
  const templates = task === 'grade' ? ['init', 'ablation', 'custom'] : ['init', 'custom']
  const [form, setForm] = useState({ name: '', template: 'init', version: '', split: '', feature: '', epochs: task === 'segmentation' ? 60 : 40 })
  useEffect(() => {
    setForm((f) => ({ ...f, version: f.version || versions.data?.versions[0]?.id || '', split: f.split || splits.data?.splits[0]?.id || '', feature: f.feature || crossFitted[0]?.id || '' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versions.data, splits.data, featureSets.data])
  const create = useAction(() =>
    api.post<{ id: string }>('/experiments', {
      name: form.name,
      template: form.template,
      task,
      dataset_version_id: form.version,
      split_id: form.split,
      feature_set_id: form.template === 'ablation' ? form.feature || null : null,
      base_config: { epochs: form.epochs },
    }),
  )

  return (
    <Panel title={task === 'segmentation' ? '分割實驗' : '回音分級實驗'}>
      <p className="text-[13px] text-ink-soft">一組用同一資料集版本與切分的訓練，逐折比較並用 Nadeau-Bengio 校正 t 檢定判斷差異。建立實驗只會建立草稿訓練，由你按開始。</p>
      <div className="mt-3 grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div>
          {list.loading && !list.data ? (
            <Loading />
          ) : list.data?.experiments.length ? (
            <Table
              minWidth={520}
              head={['編號', '名稱', '範本', '進度', '建立']}
              rows={list.data.experiments.map((e) => [
                <Link key="id" to={`/research/experiments/${e.id}`} className="font-medium text-steel hover:underline">
                  {e.id}
                </Link>,
                e.name,
                templateLabel[e.template] ?? e.template,
                `${e.completed}／${e.runs} 完成`,
                e.created_at.slice(0, 10),
              ])}
            />
          ) : (
            <EmptyState icon={FlaskConical} title="還沒有實驗" body="用右邊的範本建立第一個實驗。" />
          )}
          <ErrorNote error={list.error} />
        </div>
        <div className="space-y-3">
          <Field label="範本">
            <select className={inputClass} value={form.template} onChange={(e) => setForm({ ...form, template: e.target.value })}>
              {templates.map((k) => (
                <option key={k} value={k}>
                  {templateLabel[k]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="名稱（選填）">
            <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="資料集版本">
            <select className={inputClass} value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })}>
              {versions.data?.versions.map((v) => (
                <option key={v.id}>{v.id}</option>
              ))}
            </select>
          </Field>
          <Field label="切分">
            <select className={inputClass} value={form.split} onChange={(e) => setForm({ ...form, split: e.target.value })}>
              {splits.data?.splits.map((s) => (
                <option key={s.id}>{s.id}</option>
              ))}
            </select>
          </Field>
          {form.template === 'ablation' && (
            <Field label="交叉擬合特徵集" hint="來自分割模型的交叉預測遮罩；用人工遮罩算的特徵會洩漏答案，不能用">
              <select className={inputClass} value={form.feature} onChange={(e) => setForm({ ...form, feature: e.target.value })}>
                <option value="">請選擇</option>
                {crossFitted.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.id}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Epoch 上限">
            <input type="number" min={1} className={inputClass} value={form.epochs} onChange={(e) => setForm({ ...form, epochs: Number(e.target.value) })} />
          </Field>
          {form.template === 'ablation' && <p className="text-[13px] text-ink-soft">A0 只用影像、A1 ImageNet、A2 ＋腎長、A3 ＋腎長＋回音比值、A4 打亂特徵（負對照）、A5 同 A3 用 ImageNet。</p>}
          <ErrorNote error={create.error} />
          <Button
            variant="primary"
            icon={FlaskConical}
            disabled={create.busy || !form.version || !form.split}
            onClick={async () => {
              const r = await create.run()
              if (r) navigate(`/research/experiments/${r.id}`)
            }}
          >
            建立實驗（草稿）
          </Button>
        </div>
      </div>
    </Panel>
  )
}
