import { useCallback, useState } from 'react'
import { Play, RotateCcw, Square, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import { jobStatusLabel, type Job } from '../../api/types'
import { Button, EmptyState, KeyValue, PageHeader, Panel, Pill, ProgressBar, Table, Tabs, Timeline, inputClass } from '../../components/ui'
import { ConfirmDialog, Drawer } from '../../components/overlays'
import { ErrorNote, jobTone } from '../../components/live'
import { History } from 'lucide-react'

const ACTIVE = ['queued', 'running', 'stopping']

// 三區分開（決策 D28）：訓練與評估依任務分區，其他工作（匯入、圈選…）在「其他」
const ZONES = [
  { id: '', label: '全部' },
  { id: 'egfr', label: 'eGFR' },
  { id: 'segmentation', label: '分割' },
  { id: 'grade', label: '回音分級' },
  { id: 'clinical', label: '醫師端' },
  { id: 'other', label: '其他' },
]

const eventTitle: Record<string, string> = {
  queued: '排入佇列',
  started: '開始執行',
  stop_requested: '要求停止',
  stopped: '已停止',
  resumed: '恢復',
  completed: '完成',
  failed: '失敗',
  interrupted: '服務重啟，工作中斷',
}

export default function Jobs() {
  const [status, setStatus] = useState('')
  const [zone, setZone] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const query = new URLSearchParams({ ...(status ? { status } : {}), ...(zone ? { zone } : {}) }).toString()
  const list = useApi<{ jobs: Job[] }>(`/jobs${query ? `?${query}` : ''}`, [status, zone])
  const detail = useApi<Job>(openId ? `/jobs/${openId}` : null, [openId])
  const anyActive = Boolean(list.data?.jobs.some((j) => ['queued', 'running', 'stopping'].includes(j.status)))
  const refresh = useCallback(() => {
    void list.reload()
    if (openId) void detail.reload()
  }, [list, detail, openId])
  usePolling(refresh, 2000, anyActive)
  const act = useAction((id: string, action: 'stop' | 'resume' | 'retry') => api.post(`/jobs/${id}/${action}`))
  // 勾選刪除：只能選已結束的工作（排隊中、執行中的不能刪）
  const [picked, setPicked] = useState<string[]>([])
  const [deleteOpen, setDeleteOpen] = useState(false)
  const remove = useAction((ids: string[]) => api.post<{ deleted: number; skipped: number }>('/jobs/delete', { ids }))
  const finished = (list.data?.jobs ?? []).filter((j) => !ACTIVE.includes(j.status)).map((j) => j.id)
  const allPicked = finished.length > 0 && finished.every((id) => picked.includes(id))
  const toggle = (id: string, on: boolean) => setPicked((p) => (on ? [...p, id] : p.filter((x) => x !== id)))

  const run = async (id: string, action: 'stop' | 'resume' | 'retry') => {
    await act.run(id, action)
    refresh()
  }
  const job = detail.data

  return (
    <>
      <PageHeader title="任務紀錄" description="所有背景工作都在這裡：匯入、去識別化、醫師圈選、訓練、評估與分析。點編號查看詳細。" />
      <Tabs label="依區分類" value={zone} onChange={setZone} tabs={ZONES} />
      <label className="mb-4 block w-48 text-[13px] text-ink-soft">
        狀態
        <select className={`${inputClass} mt-1`} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部</option>
          {Object.entries(jobStatusLabel).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Button icon={Trash2} disabled={!picked.length || remove.busy} onClick={() => setDeleteOpen(true)}>
          刪除勾選的紀錄
        </Button>
        <span className="text-[13px] text-ink-faint">{picked.length ? `已選 ${picked.length} 筆` : '排隊中、執行中的工作不能刪除'}</span>
      </div>
      <ErrorNote error={list.error ?? act.error ?? remove.error} />
      <Panel flush>
        {list.data && list.data.jobs.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={History} title="沒有背景工作" body="匯入影像時會在這裡出現工作與進度。" />
          </div>
        ) : (
          <Table
            minWidth={760}
            head={[
              <input
                key="all"
                type="checkbox"
                className="h-4 w-4"
                aria-label="全選已結束的工作"
                checked={allPicked}
                disabled={!finished.length}
                onChange={(e) => setPicked(e.target.checked ? finished : [])}
              />,
              '編號',
              '類型',
              '對象',
              '建立者',
              '建立時間',
              '狀態',
            ]}
            rows={(list.data?.jobs ?? []).map((j) => [
              <input
                key="c"
                type="checkbox"
                className="h-4 w-4"
                aria-label={`選取 ${j.id}`}
                checked={picked.includes(j.id)}
                disabled={ACTIVE.includes(j.status)}
                onChange={(e) => toggle(j.id, e.target.checked)}
              />,
              <button key="i" type="button" className="font-semibold text-steel hover:underline" onClick={() => setOpenId(j.id)}>
                {j.id}
              </button>,
              j.kind_label,
              j.target || '—',
              j.created_by || '—',
              j.created_at.slice(0, 16).replace('T', ' '),
              <span key="s" className="flex items-center gap-3">
                <Pill tone={jobTone[j.status]}>{jobStatusLabel[j.status]}</Pill>
                {['running', 'stopping'].includes(j.status) && (
                  <span className="w-28">
                    <ProgressBar value={j.progress} label={`${j.id}進度`} />
                  </span>
                )}
              </span>,
            ])}
          />
        )}
      </Panel>

      <ConfirmDialog
        open={deleteOpen}
        title="刪除任務紀錄"
        confirmLabel="永久刪除紀錄"
        danger
        onClose={() => setDeleteOpen(false)}
        onConfirm={async () => {
          setDeleteOpen(false)
          const r = await remove.run(picked)
          if (r) {
            setPicked([])
            if (openId && picked.includes(openId)) setOpenId(null)
            void list.reload()
          }
        }}
      >
        <p>{picked.length} 筆任務紀錄（含事件）會永久刪除，無法還原。</p>
        <p className="mt-2 text-ink-soft">
          只刪紀錄，不影響工作產生的資料：影像、草稿、訓練結果與模型都會保留。已停止或中斷的工作刪除後，就不能在這裡「恢復」或「重試」；訓練仍可以在訓練頁從 checkpoint 恢復。
        </p>
      </ConfirmDialog>

      <Drawer open={Boolean(openId)} title={job ? `${job.id}・${job.kind_label}` : '工作詳細'} onClose={() => setOpenId(null)}>
        {job && (
          <div className="space-y-5">
            <KeyValue
              items={[
                ['對象', job.target || '—'],
                ['建立者', job.created_by || '—'],
                ['狀態', <Pill key="s" tone={jobTone[job.status]}>{jobStatusLabel[job.status]}</Pill>],
                ['進度', `${Math.round(job.progress)}%${job.message ? `（${job.message}）` : ''}`],
                ...(job.retry_of ? ([['重試自', job.retry_of]] as [string, string][]) : []),
              ]}
            />
            {job.error_message && <ErrorNote message={`${job.error_code ?? ''} ${job.error_message}`} />}
            {Object.keys(job.result).length > 0 && (
              <div>
                <p className="mb-1 font-medium">結果</p>
                <KeyValue items={Object.entries(job.result).filter(([, v]) => typeof v !== 'object').map(([k, v]) => [k, String(v)])} />
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {['queued', 'running'].includes(job.status) && (
                <Button icon={Square} onClick={() => void run(job.id, 'stop')}>
                  停止
                </Button>
              )}
              {job.resumable && ['stopped', 'interrupted', 'failed'].includes(job.status) && (
                <Button icon={Play} onClick={() => void run(job.id, 'resume')}>
                  恢復
                </Button>
              )}
              {['failed', 'interrupted', 'stopped'].includes(job.status) && (
                <Button icon={RotateCcw} onClick={() => void run(job.id, 'retry')}>
                  重試（建立新工作）
                </Button>
              )}
            </div>
            <div>
              <p className="mb-2 font-medium">事件</p>
              <Timeline
                entries={(job.events ?? []).map((e) => ({
                  title: eventTitle[e.type] ?? e.type,
                  time: e.created_at.slice(11, 19),
                  note: typeof e.data.message === 'string' ? e.data.message : undefined,
                  tone: e.type === 'failed' ? 'alert' : e.type === 'completed' ? 'ok' : e.type === 'interrupted' || e.type === 'stopped' ? 'amber' : undefined,
                }))}
              />
            </div>
          </div>
        )}
      </Drawer>
    </>
  )
}
