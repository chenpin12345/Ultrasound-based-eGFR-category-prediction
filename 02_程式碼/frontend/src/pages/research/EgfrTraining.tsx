import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FilePlus2, GitCompare, Play } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import type { SplitInfo } from '../../api/types'
import { fmt, runStatusLabel, type RunInfo } from '../../api/ml'
import { Button, EmptyState, Field, PageHeader, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'
import { OpenFolderButton } from '../../components/OpenFolder'
import { PretrainedPanel, useWeights } from '../../components/PretrainedPanel'
import { useRunSelection } from '../../components/RunTrash'
import { runTone } from './Training'

interface Options {
  classes: Record<string, string[]>
  inputs: { code: string; label: string; inputs: string[]; needs_mask: boolean; cpu: boolean }[]
  presets: Record<string, string[]>
}

interface Group {
  id: string
  name: string
  created_at: string
  codes: string[]
  ks: number[]
  members: number
  completed: number
}

interface MaskSet {
  id: string
  status: string
  split_id: string
  seg_run_id: string
}

const KS = [2, 3, 5]
export const inputLabel = (cfg: Record<string, unknown>) => {
  const inputs = (cfg.inputs as string[] | undefined) ?? (cfg.features ? ['image', 'measures'] : ['image'])
  const names: Record<string, string> = { image: '影像', clinical: '臨床', measures: '遮罩量測', mask_channels: '遮罩通道' }
  return inputs.map((i) => names[i] ?? i).join('＋')
}

/** eGFR 區：勾選式比較組（輸入方式 ①–⑥ × 類別數 2／3／5）、單一模型、訓練紀錄（決策 D22–D24、D28）。 */
export default function EgfrTraining() {
  const navigate = useNavigate()
  const options = useApi<Options>('/egfr/options')
  const versions = useApi<{ versions: { id: string; image_count: number; patient_count: number }[] }>('/dataset-versions')
  const splits = useApi<{ splits: SplitInfo[] }>('/splits')
  const settings = useApi<{ primary_split_id: string | null }>('/settings')
  const maskSets = useApi<{ mask_sets: MaskSet[] }>('/mask-sets')
  const groups = useApi<{ comparisons: Group[] }>('/egfr/comparisons')
  const runs = useApi<{ runs: RunInfo[] }>('/training/runs?task=egfr')
  const weights = useWeights()
  usePolling(runs.reload, 4000, Boolean(runs.data?.runs.some((r) => r.status === 'running' || r.status === 'queued')))
  const selection = useRunSelection(runs.data?.runs ?? [], () => {
    void runs.reload()
    void groups.reload()
  })

  const [codes, setCodes] = useState<string[]>(['image'])
  const [ks, setKs] = useState<number[]>([2, 3, 5])
  const [form, setForm] = useState({ name: '', version: '', split: '', maskSet: '', arch: 'resnet34', init: 'imagenet', head: 'corn', epochs: 40, batch_size: 16, img_size: 384, lr: 0.0003, reuse: true })
  useEffect(() => {
    setForm((f) => ({
      ...f,
      version: f.version || versions.data?.versions[0]?.id || '',
      split: f.split || settings.data?.primary_split_id || splits.data?.splits[0]?.id || '',
    }))
  }, [versions.data, splits.data, settings.data])
  const readyMaskSets = (maskSets.data?.mask_sets ?? []).filter((m) => m.status === 'completed' && m.split_id === form.split)
  useEffect(() => {
    setForm((f) => ({ ...f, maskSet: readyMaskSets.some((m) => m.id === f.maskSet) ? f.maskSet : readyMaskSets[0]?.id ?? '' }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maskSets.data, form.split])

  const inputs = options.data?.inputs ?? []
  const noMask = !form.maskSet
  const effective = codes.filter((c) => !(noMask && inputs.find((i) => i.code === c)?.needs_mask))
  const count = useMemo(() => {
    const cpu = effective.filter((c) => inputs.find((i) => i.code === c)?.cpu).length * ks.length
    return { total: effective.length * ks.length, cpu, gpu: effective.length * ks.length - cpu }
  }, [effective, ks, inputs])
  const imagenetMissing = form.init === 'imagenet' && !weights.data?.weights.find((w) => w.name === `${form.arch}-imagenet`)?.downloaded

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: ['epochs', 'batch_size', 'img_size', 'lr'].includes(k) ? Number(e.target.value) : e.target.value })

  const create = useAction((start: boolean) =>
    api.post<{ id: string; reused: number }>('/egfr/comparisons', {
      name: form.name,
      dataset_version_id: form.version,
      split_id: form.split,
      inputs: effective,
      classes: ks,
      mask_set_id: form.maskSet || null,
      reuse: form.reuse,
      start,
      base_config: { arch: form.arch, init: form.init, head: form.head, epochs: form.epochs, batch_size: form.batch_size, img_size: form.img_size, lr: form.lr },
    }),
  )

  return (
    <>
      <PageHeader
        title="eGFR 訓練"
        description="勾選要比較的輸入方式與類別數，一次建立比較組。2 類（AUC(<60)）是主要結果；3、5 類為次要。訓練依序在 GPU 上執行，純臨床與純量測的基準在 CPU 上幾秒完成。"
        actions={<OpenFolderButton kind="relpath" id="04_模型/01_訓練紀錄/eGFR" label="開啟訓練資料夾" />}
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel title="建立 eGFR 比較">
            {!options.data ? (
              <Loading />
            ) : (
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_200px]">
                <fieldset>
                  <legend className="font-medium">輸入方式（可複選）</legend>
                  {(['無遮罩', '有遮罩'] as const).map((group) => (
                    <div key={group} className="mt-2">
                      <p className="text-[13px] text-ink-faint">
                        {group}
                        {group === '有遮罩' && (noMask ? '（需要先產生遮罩組：分割 › 遮罩組）' : `（遮罩組 ${form.maskSet}）`)}
                      </p>
                      {inputs
                        .filter((i) => i.needs_mask === (group === '有遮罩'))
                        .map((i) => (
                          <label key={i.code} className={`mt-1 flex items-center gap-2 text-[14px] ${i.needs_mask && noMask ? 'text-ink-faint' : ''}`}>
                            <input type="checkbox" className="accent-steel" disabled={i.needs_mask && noMask} checked={codes.includes(i.code) && !(i.needs_mask && noMask)} onChange={() => setCodes((c) => toggle(c, i.code))} />
                            {i.label}
                            {i.code === 'image_clinical' && '（糖尿病、年齡、性別）'}
                            {i.cpu && <span className="text-[12px] text-ink-faint">CPU 幾秒</span>}
                          </label>
                        ))}
                    </div>
                  ))}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {Object.entries(options.data.presets).map(([name, list]) => (
                      <Button key={name} variant="ghost" onClick={() => setCodes(list)}>
                        {name}
                      </Button>
                    ))}
                    <Button variant="ghost" onClick={() => setCodes(inputs.map((i) => i.code))}>
                      全選
                    </Button>
                    <Button variant="ghost" onClick={() => setCodes([])}>
                      清除
                    </Button>
                  </div>
                </fieldset>
                <fieldset>
                  <legend className="font-medium">類別數（可複選）</legend>
                  {KS.map((k) => (
                    <label key={k} className="mt-2 flex items-start gap-2 text-[14px]">
                      <input type="checkbox" className="mt-1 accent-steel" checked={ks.includes(k)} onChange={() => setKs((v) => toggle(v, k).sort())} />
                      <span>
                        {k} 類
                        <span className="block text-[12px] text-ink-faint">{options.data?.classes[String(k)].join('／')}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
              </div>
            )}
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="名稱（選填）">
                <input className={inputClass} value={form.name} onChange={set('name')} placeholder="例如：第一次比較" />
              </Field>
              <Field label="資料集版本">
                <select className={inputClass} value={form.version} onChange={set('version')}>
                  {versions.data?.versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.id}（{v.image_count} 張、{v.patient_count} 位）
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="切分" hint={settings.data?.primary_split_id ? `主切分：${settings.data.primary_split_id}` : undefined}>
                <select className={inputClass} value={form.split} onChange={set('split')}>
                  {splits.data?.splits.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.id}（{s.folds} 折）
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="遮罩組（④⑤⑥ 用）">
                <select className={inputClass} value={form.maskSet} onChange={set('maskSet')}>
                  <option value="">（沒有）</option>
                  {readyMaskSets.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id}（{m.seg_run_id}）
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="架構">
                <select className={inputClass} value={form.arch} onChange={set('arch')}>
                  <option value="resnet34">ResNet-34（建議）</option>
                  <option value="resnet18">ResNet-18</option>
                </select>
              </Field>
              <Field label="初始化">
                <select className={inputClass} value={form.init} onChange={set('init')}>
                  <option value="imagenet">ImageNet（建議）</option>
                  <option value="random">隨機</option>
                </select>
              </Field>
              <Field label="3、5 類的輸出層" hint="2 類固定為二元">
                <select className={inputClass} value={form.head} onChange={set('head')}>
                  <option value="corn">CORN（有序，建議）</option>
                  <option value="ce">一般 CE（對照）</option>
                </select>
              </Field>
              <Field label="Epoch 上限">
                <input type="number" min={1} className={inputClass} value={form.epochs} onChange={set('epochs')} />
              </Field>
              <Field label="Batch size">
                <input type="number" min={1} className={inputClass} value={form.batch_size} onChange={set('batch_size')} />
              </Field>
              <Field label="影像大小（px）">
                <input type="number" min={64} step={32} className={inputClass} value={form.img_size} onChange={set('img_size')} />
              </Field>
              <Field label="學習率">
                <input type="number" min={0} step={0.0001} className={inputClass} value={form.lr} onChange={set('lr')} />
              </Field>
              <label className="flex items-start gap-2 self-end text-[14px]">
                <input type="checkbox" className="mt-1 accent-steel" checked={form.reuse} onChange={(e) => setForm({ ...form, reuse: e.target.checked })} />
                <span>
                  沿用設定相同的已完成訓練
                  <span className="block text-[12px] text-ink-faint">取消勾選則全部重新訓練</span>
                </span>
              </label>
            </div>
            <p className="mt-4 rounded border border-line bg-paper px-3 py-2 text-[14px]">
              將建立：<strong>{count.total}</strong> 個模型（GPU {count.gpu} 個，CPU {count.cpu} 個）；粗估 {count.gpu} 小時（每個 GPU 模型約 1 小時，實際依提早停止而定）。
              {codes.length !== effective.length && <span className="block text-[12px] text-amber">沒有遮罩組，④⑤⑥ 不會建立。</span>}
            </p>
            {imagenetMissing && <p className="mt-2 text-[13px] text-amber">還沒下載 {form.arch} 的 ImageNet 權重，請先在右側下載，否則開始時會被拒絕。</p>}
            <ErrorNote error={create.error} />
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="primary"
                icon={Play}
                disabled={!count.total || !form.version || !form.split || create.busy}
                onClick={async () => {
                  const r = await create.run(true)
                  if (r) navigate(`/research/egfr/compare/${r.id}`)
                }}
              >
                建立並開始
              </Button>
              <Button
                icon={FilePlus2}
                disabled={!count.total || !form.version || !form.split || create.busy}
                onClick={async () => {
                  const r = await create.run(false)
                  if (r) navigate(`/research/egfr/compare/${r.id}`)
                }}
              >
                只建立（草稿）
              </Button>
            </div>
          </Panel>

          <Panel title="比較組" flush>
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
              <EmptyState icon={GitCompare} title="還沒有比較組" body="在上面勾選輸入方式與類別數後建立。" />
            )}
          </Panel>

          <Panel title="eGFR 訓練紀錄" flush>
            {runs.loading && !runs.data ? (
              <Loading />
            ) : runs.data?.runs.length ? (
              <>
              {selection.bar}
              <Table
                minWidth={800}
                head={[selection.headCell, '編號', '名稱', '類別數', '輸入方式', '狀態', '交叉驗證 AUC(<60)', '建立']}
                rows={runs.data.runs.map((r) => [
                  selection.rowCell(r),
                  <Link key="id" to={`/research/training/${r.id}`} className="font-medium text-steel hover:underline">
                    {r.id}
                  </Link>,
                  r.name,
                  `${Number(r.config.egfr_classes ?? 2)} 類`,
                  `${inputLabel(r.config)}${r.config.arch === 'logreg' ? '（基準）' : ''}`,
                  <Pill key="s" tone={runTone(r.status)}>
                    {runStatusLabel[r.status]}
                  </Pill>,
                  r.mean_best_score == null ? '—' : fmt((r.oof?.auc_lt60 as number | undefined) ?? (r.oof?.auc as number | undefined) ?? r.mean_best_score),
                  `${r.created_at.slice(0, 16).replace('T', ' ')}・${r.created_by}`,
                ])}
              />
              </>
            ) : (
              <EmptyState icon={Play} title="還沒有 eGFR 訓練" body="用上面的表單建立比較組。" />
            )}
            <ErrorNote error={runs.error ?? groups.error} />
          </Panel>
        </div>
        <div className="space-y-5">
          <PretrainedPanel />
          <Panel title="怎麼看結果">
            <ul className="list-disc space-y-2 pl-5 text-[13px] text-ink-soft">
              <li>所有模型都輸出 P(eGFR&lt;60)，用同一把尺（病人層級 AUC(&lt;60)）比較。</li>
              <li>預先指定的主要比較：② 影像＋臨床 vs ③ 純臨床（2 類）。差異的 95% 信賴區間不含 0，表示影像在臨床資料之外有幫助。</li>
              <li>eGFR 公式本身含年齡與性別，所以純臨床模型一定有一定的成績。</li>
              <li>5 類的 ≥90 只有 23 人（測試集 4 人），單一類別的指標只供參考。</li>
              <li>固定測試集只能用一次，等全部比較組完成後再一起評估。</li>
            </ul>
          </Panel>
        </div>
      </div>
    </>
  )
}
