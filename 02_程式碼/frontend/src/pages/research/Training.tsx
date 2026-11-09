import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FilePlus2, Play } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import type { SplitInfo } from '../../api/types'
import { fmt, runStatusLabel, scoreLabel, type RunInfo, type TaskId, type TaskInfo } from '../../api/ml'
import { Button, EmptyState, Field, PageHeader, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'
import { OpenFolderButton } from '../../components/OpenFolder'
import { PretrainedPanel, useWeights } from '../../components/PretrainedPanel'
import { useRunSelection } from '../../components/RunTrash'
import Experiments from './Experiments'
import LearningCurve from './LearningCurve'

interface VersionInfo {
  id: string
  note: string
  image_count: number
  patient_count: number
  created_at: string
}

const ARCHS: Record<TaskId, [string, string][]> = {
  segmentation: [['resnet34-unet', 'UNet＋ResNet-34 編碼器'], ['unet', '經典 UNet（只能隨機初始化）']],
  egfr: [['resnet18', 'ResNet-18'], ['resnet34', 'ResNet-34']],
  grade: [['resnet18', 'ResNet-18'], ['resnet34', 'ResNet-34']],
}
const HEADS: [string, string][] = [['corn', 'CORN（建議）'], ['coral', 'CORAL（正確版）'], ['sord', 'SORD 軟標籤'], ['ce', '一般 CE']]

export const runTone = (s: RunInfo['status']) => (s === 'completed' ? 'ok' : s === 'failed' ? 'alert' : s === 'running' || s === 'queued' ? 'steel' : 'neutral')

const TITLE: Record<'segmentation' | 'grade', [string, string]> = {
  segmentation: ['分割訓練', '腎實質、腎竇、肝、脾的分割。只用醫師上傳或人工確認過的遮罩；主切分測試集的病人不會進入訓練。訓練在獨立程序執行，同一時間只跑一個，可以停止並從上一個完成的 epoch 恢復。'],
  grade: ['回音分級訓練', '回音 Grade 0–3（需要醫師的回音分級標註）。訓練在獨立程序執行，同一時間只跑一個，可以停止並從上一個完成的 epoch 恢復。'],
}

/** 分割與回音分級的訓練頁（eGFR 在自己的區：EgfrTraining）。三區的清單不混放（決策 D28）。 */
export default function Training({ task }: { task: 'segmentation' | 'grade' }) {
  const tasks = useApi<{ tasks: TaskInfo[] }>('/training/tasks')
  const versions = useApi<{ versions: VersionInfo[] }>('/dataset-versions')
  const splits = useApi<{ splits: SplitInfo[] }>('/splits')
  const runs = useApi<{ runs: RunInfo[] }>(`/training/runs?task=${task}`, [task])
  const weights = useWeights()
  const active = Boolean(runs.data?.runs.some((r) => r.status === 'running' || r.status === 'queued'))
  usePolling(runs.reload, 4000, active)
  const selection = useRunSelection(runs.data?.runs ?? [], () => void runs.reload())

  const [form, setForm] = useState({ name: '', version: '', split: '', arch: 'resnet34-unet', init: 'random', head: 'corn', epochs: 60, batch_size: 4, img_size: 512, lr: 0.0003 })
  const [nn, setNn] = useState({ version: '', split: '', epochs: '250' })

  // 換任務時帶入預設值
  const defaults = tasks.data?.tasks.find((t) => t.id === task)?.defaults
  useEffect(() => {
    if (!defaults) return
    setForm((f) => ({ ...f, arch: String(defaults.arch), init: 'random', head: String(defaults.head ?? 'corn'), epochs: Number(defaults.epochs), batch_size: Number(defaults.batch_size), img_size: Number(defaults.img_size), lr: Number(defaults.lr) }))
  }, [task, defaults])
  useEffect(() => {
    const v = versions.data?.versions[0]?.id ?? ''
    const s = splits.data?.splits[0]?.id ?? ''
    setForm((f) => ({ ...f, version: f.version || v, split: f.split || s }))
    setNn((n) => ({ ...n, version: n.version || v, split: n.split || s }))
  }, [versions.data, splits.data])

  const create = useAction((start: boolean) =>
    api.post<{ id: string; job_id: string | null }>('/training/runs', {
      task,
      name: form.name,
      dataset_version_id: form.version,
      split_id: form.split,
      start,
      config: {
        arch: form.arch,
        init: form.init,
        ...(task === 'grade' ? { head: form.head } : {}),
        epochs: form.epochs,
        batch_size: form.batch_size,
        img_size: form.img_size,
        lr: form.lr,
      },
    }),
  )
  const nnunet = useAction(() => api.post<{ id: string; job_id: string }>('/training/nnunet', { dataset_version_id: nn.version, split_id: nn.split, epochs: nn.epochs }))

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: ['epochs', 'batch_size', 'img_size', 'lr'].includes(k) ? Number(e.target.value) : e.target.value })
  const ready = Boolean(form.version && form.split)
  const imagenetMissing = form.init === 'imagenet' && !weights.data?.weights.find((w) => w.name === (form.arch === 'resnet18' ? 'resnet18-imagenet' : 'resnet34-imagenet'))?.downloaded

  return (
    <>
      <PageHeader title={TITLE[task][0]} description={TITLE[task][1]} actions={<OpenFolderButton kind="relpath" id={`04_模型/01_訓練紀錄/${task === 'segmentation' ? '分割' : '回音分級'}`} label="開啟訓練資料夾" />} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel title="建立訓練">
            {tasks.loading && !tasks.data ? (
              <Loading />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="資料集版本" hint={versions.data?.versions.length ? undefined : '先到「資料集 › 資料集版本」凍結一個版本'}>
                  <select className={inputClass} value={form.version} onChange={set('version')}>
                    {versions.data?.versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.id}（{v.image_count} 張、{v.patient_count} 位）
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="切分">
                  <select className={inputClass} value={form.split} onChange={set('split')}>
                    {splits.data?.splits.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id}（{s.folds} 折）
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="名稱（選填）">
                  <input className={inputClass} value={form.name} onChange={set('name')} placeholder="例如：分割基準" />
                </Field>
                <Field label="架構">
                  <select className={inputClass} value={form.arch} onChange={set('arch')}>
                    {ARCHS[task].map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="初始化（D2）">
                  <select className={inputClass} value={form.init} onChange={set('init')} disabled={form.arch === 'unet'}>
                    <option value="random">隨機初始化（預設）</option>
                    <option value="imagenet">ImageNet 預訓練</option>
                  </select>
                </Field>
                {task === 'grade' && (
                  <Field label="輸出頭">
                    <select className={inputClass} value={form.head} onChange={set('head')}>
                      {HEADS.map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label="Epoch 上限" hint="會依驗證成績提早停止">
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
              </div>
            )}
            {imagenetMissing && <p className="mt-3 text-[13px] text-amber">還沒下載這個架構的 ImageNet 權重，請先在右側「預訓練權重」下載，否則開始時會被拒絕。</p>}
            <ErrorNote error={create.error} />
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="primary"
                icon={Play}
                disabled={!ready || create.busy}
                onClick={async () => {
                  if (await create.run(true)) void runs.reload()
                }}
              >
                建立並開始訓練
              </Button>
              <Button
                icon={FilePlus2}
                disabled={!ready || create.busy}
                onClick={async () => {
                  if (await create.run(false)) void runs.reload()
                }}
              >
                只建立草稿
              </Button>
            </div>
          </Panel>

          <Panel title="訓練紀錄" flush>
            {runs.loading && !runs.data ? (
              <Loading />
            ) : runs.data?.runs.length ? (
              <>
              {selection.bar}
              <Table
                minWidth={760}
                head={[selection.headCell, '編號', '名稱', '狀態', '交叉驗證', '建立']}
                rows={runs.data.runs.map((r) => [
                  selection.rowCell(r),
                  <Link key="id" to={`/research/training/${r.id}`} className="font-medium text-steel hover:underline">
                    {r.id}
                  </Link>,
                  r.name,
                  <Pill key="s" tone={runTone(r.status)}>
                    {runStatusLabel[r.status]}
                  </Pill>,
                  r.mean_best_score == null ? '—' : `${scoreLabel[r.task]} ${fmt(r.mean_best_score)}`,
                  `${r.created_at.slice(0, 16).replace('T', ' ')}・${r.created_by}`,
                ])}
              />
              </>
            ) : (
              <EmptyState icon={Play} title="還沒有訓練" body="選好資料集版本與切分後按「建立並開始訓練」。" />
            )}
          </Panel>

          {task === 'segmentation' && <LearningCurve />}

          <Experiments task={task} />
        </div>

        <div className="space-y-5">
          <PretrainedPanel />

          {task === 'segmentation' && (
          <Panel title="nnU-Net v2 基準">
            <p className="mb-3 text-[13px] text-ink-soft">用同一個切分訓練 nnU-Net，結果可以和內建 UNet 逐折比較。只用腎實質與腎竇都分得出來的遮罩。</p>
            <div className="space-y-3">
              <Field label="資料集版本">
                <select className={inputClass} value={nn.version} onChange={(e) => setNn({ ...nn, version: e.target.value })}>
                  {versions.data?.versions.map((v) => (
                    <option key={v.id}>{v.id}</option>
                  ))}
                </select>
              </Field>
              <Field label="切分">
                <select className={inputClass} value={nn.split} onChange={(e) => setNn({ ...nn, split: e.target.value })}>
                  {splits.data?.splits.map((s) => (
                    <option key={s.id}>{s.id}</option>
                  ))}
                </select>
              </Field>
              <Field label="Epoch 數">
                <select className={inputClass} value={nn.epochs} onChange={(e) => setNn({ ...nn, epochs: e.target.value })}>
                  <option value="100">100（快速）</option>
                  <option value="250">250（建議）</option>
                  <option value="1000">1000（nnU-Net 預設，非常久）</option>
                </select>
              </Field>
              <ErrorNote error={nnunet.error} />
              <Button
                icon={Play}
                disabled={!nn.version || !nn.split || nnunet.busy}
                onClick={async () => {
                  if (await nnunet.run()) void runs.reload()
                }}
              >
                開始 nnU-Net 訓練
              </Button>
            </div>
          </Panel>
          )}
        </div>
      </div>
    </>
  )
}
