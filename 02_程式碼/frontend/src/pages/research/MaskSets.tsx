import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Layers3 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import type { RunInfo } from '../../api/ml'
import { Button, EmptyState, Field, PageHeader, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../components/live'
import { OpenFolderButton } from '../../components/OpenFolder'

interface MaskSet {
  id: string
  seg_run_id: string
  split_id: string
  dataset_version_id: string
  spec: { no_kidney?: number; folds?: string[]; note?: string }
  rows: number
  status: string
  relpath: string
  job_id: string | null
  created_at: string
}

interface Coverage extends MaskSet {
  images: number
  by_source: Record<string, number>
  no_kidney: string[]
  no_kidney_count: number
  sample: string[]
}

const tone = (s: string) => (s === 'completed' ? 'ok' : s === 'failed' ? 'alert' : 'steel')
const statusLabel: Record<string, string> = { queued: '排隊中', running: '產生中', completed: '完成', failed: '失敗' }

/** 交叉預測遮罩組（決策 D26）：用分割訓練替全部影像預測遮罩，給有遮罩的 eGFR（④⑤⑥）使用。 */
export default function MaskSets() {
  const sets = useApi<{ mask_sets: MaskSet[] }>('/mask-sets')
  const runs = useApi<{ runs: RunInfo[] }>('/training/runs?task=segmentation')
  const segRuns = (runs.data?.runs ?? []).filter((r) => r.status === 'completed' && !r.config.framework)
  const [run, setRun] = useState('')
  const [note, setNote] = useState('')
  const [job, setJob] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const create = useAction(() => api.post<{ id: string; job_id: string }>('/mask-sets', { seg_run_id: run || segRuns[0]?.id, note }))
  const detail = useApi<Coverage>(open ? `/mask-sets/${open}` : null, [open])

  return (
    <>
      <PageHeader
        title="遮罩組"
        description="用一個完成的分割訓練替資料集版本的每張影像預測遮罩：每位病人都用沒看過他的那一折模型，測試病人用各折模型平均。產生後會自動擷取回音與形態特徵，eGFR 的 ④⑤⑥ 就能使用。"
        actions={<OpenFolderButton kind="relpath" id="03_資料/04_模型產出/預測遮罩組" label="開啟遮罩組資料夾" />}
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel title="遮罩組" flush>
          {sets.loading && !sets.data ? (
            <Loading />
          ) : sets.data?.mask_sets.length ? (
            <Table
              minWidth={640}
              head={['遮罩組', '分割訓練', '切分', '張數', '找不到腎臟', '狀態', '']}
              rows={sets.data.mask_sets.map((m) => [
                <span key="i" className={open === m.id ? 'font-semibold text-steel' : 'font-medium'}>
                  {m.id}
                </span>,
                <Link key="r" to={`/research/training/${m.seg_run_id}`} className="text-steel underline">
                  {m.seg_run_id}
                </Link>,
                m.split_id,
                m.rows,
                m.spec.no_kidney ?? '—',
                <Pill key="s" tone={tone(m.status)}>
                  {statusLabel[m.status] ?? m.status}
                </Pill>,
                <Button key="o" variant="ghost" onClick={() => setOpen(m.id)}>
                  抽查
                </Button>,
              ])}
            />
          ) : (
            <EmptyState icon={Layers3} title="還沒有遮罩組" body="先用醫師圈選的遮罩完成一個分割訓練，再從右邊產生。" />
          )}
          <ErrorNote error={sets.error} />
        </Panel>
        <Panel title="產生遮罩組">
          <div className="space-y-3">
            <Field label="分割訓練" hint="必須每一折都完成；nnU-Net 基準不能使用">
              <select className={inputClass} value={run || segRuns[0]?.id || ''} onChange={(e) => setRun(e.target.value)}>
                {segRuns.length === 0 && <option value="">（沒有完成的分割訓練）</option>}
                {segRuns.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id}・{r.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="備註（選填）">
              <input className={inputClass} value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
            </Field>
            <Button
              variant="primary"
              icon={Layers3}
              disabled={!segRuns.length || create.busy}
              onClick={async () => {
                const r = await create.run()
                if (r) {
                  setJob(r.job_id)
                  setOpen(r.id)
                  void sets.reload()
                }
              }}
            >
              產生遮罩組
            </Button>
            {job && (
              <JobProgress
                jobId={job}
                onDone={() => {
                  void sets.reload()
                  void detail.reload()
                }}
              />
            )}
            <ErrorNote error={create.error} />
            <p className="text-[12px] text-ink-faint">在顯示卡上執行，975 張約需數分鐘；可以停止，之後從中斷處接續。</p>
          </div>
        </Panel>
      </div>

      {open && detail.data && (
        <Panel title={`${detail.data.id} 抽查`} className="mt-5">
          <p className="text-[14px]">
            共 {detail.data.images} 張：
            {Object.entries(detail.data.by_source)
              .map(([k, v]) => `${k === 'ensemble' ? '各折平均（測試集等）' : k} ${v} 張`)
              .join('、')}
            ；找不到腎臟 {detail.data.no_kidney_count} 張。
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[...detail.data.no_kidney.slice(0, 4), ...detail.data.sample].slice(0, 12).map((id) => (
              <figure key={id} className="rounded border border-line">
                <img src={`/api/mask-sets/${detail.data!.id}/overlay/${id}`} alt={`${id} 的預測遮罩`} className="w-full rounded-t bg-viewer" loading="lazy" />
                <figcaption className="px-2 py-1 text-[12px]">
                  {id}
                  {detail.data!.no_kidney.includes(id) && <span className="ml-1 text-alert">找不到腎臟</span>}
                </figcaption>
              </figure>
            ))}
          </div>
          <div className="mt-3">
            <OpenFolderButton kind="relpath" id={detail.data.relpath} label="開啟這個遮罩組的資料夾" />
          </div>
        </Panel>
      )}
    </>
  )
}
