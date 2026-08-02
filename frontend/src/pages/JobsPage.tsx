import { Download, Eye, History, RefreshCw, Search, Trash2 } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Card, InlineNotice, PageHeader, ProgressBar, StatePanel, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api, humanApiError, listItems } from '../lib/api'
import { formatDate, jobIdOf, normalizeProgress } from '../lib/format'
import type { Job, JobResults, TrainingJob } from '../types/api'

interface HistoryItem { record: Job | TrainingJob; isTraining: boolean }

export function JobsPage() {
  const loadJobs = useCallback(async () => listItems<Job>(await api.listJobs()), [])
  const loadTraining = useCallback(async () => listItems<TrainingJob>(await api.listTrainingJobs()), [])
  const jobs = useAsyncResource(loadJobs)
  const training = useAsyncResource(loadTraining)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [kindFilter, setKindFilter] = useState('')
  const [selected, setSelected] = useState<HistoryItem>()
  const [deleteTarget, setDeleteTarget] = useState<HistoryItem>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const resultLoader = useCallback(() => selected && !selected.isTraining ? api.getJobResults(jobIdOf(selected.record)) : Promise.resolve({} as JobResults), [selected])
  const result = useAsyncResource(resultLoader, Boolean(selected && !selected.isTraining))

  const items = useMemo(() => {
    const all: HistoryItem[] = [...(jobs.data || []).map((record) => ({ record, isTraining: false })), ...(training.data || []).map((record) => ({ record, isTraining: true }))]
    return all.filter(({ record, isTraining }) => {
      const id = jobIdOf(record)
      const text = `${record.name || ''} ${record.kind || ''} ${id}`.toLowerCase()
      return (!search || text.includes(search.toLowerCase())) && (!statusFilter || record.status === statusFilter) && (!kindFilter || (kindFilter === 'training' ? isTraining : record.kind === kindFilter))
    }).sort((a, b) => String(b.record.created_at || '').localeCompare(String(a.record.created_at || '')))
  }, [jobs.data, kindFilter, search, statusFilter, training.data])

  const refresh = () => { void jobs.refresh(); void training.refresh() }
  const remove = async () => {
    if (!deleteTarget) return
    setBusy(true); setError(null)
    try {
      const id = jobIdOf(deleteTarget.record)
      if (deleteTarget.isTraining) await api.deleteTrainingJob(id); else await api.deleteJob(id)
      setDeleteTarget(undefined); if (selected && jobIdOf(selected.record) === id) setSelected(undefined)
      setMessage('工作紀錄與獨立輸出已安全刪除。'); await Promise.all([jobs.refresh(), training.refresh()])
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="歷史工作" description="所有影像處理、遮罩、特徵、推論與訓練工作均由資料庫保存；可在重新啟動後繼續查閱。" actions={<button className="btn-secondary" onClick={refresh}><RefreshCw className="h-4 w-4" />重新整理</button>} />
      {message && <div className="mb-4"><SuccessMessage>{message}</SuccessMessage></div>}{error && <div className="mb-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}
      <Card className="p-4 sm:p-5"><div className="grid gap-3 md:grid-cols-[1fr_12rem_12rem]"><label className="relative"><span className="sr-only">搜尋工作</span><Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" /><input className="field pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜尋工作名稱或 ID" /></label><select className="field" value={kindFilter} onChange={(event) => setKindFilter(event.target.value)} aria-label="工作類型"><option value="">所有工作類型</option><option value="process">影像處理</option><option value="mask">遮罩</option><option value="features">特徵</option><option value="inference">推論</option><option value="quick_analysis">快速分析</option><option value="training">模型訓練</option></select><select className="field" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="工作狀態"><option value="">所有狀態</option>{['queued', 'running', 'stopping', 'stopped', 'completed', 'failed', 'interrupted', 'cancelled'].map((status) => <option key={status} value={status}>{status}</option>)}</select></div></Card>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.3fr_.7fr]">
        <Card className="min-w-0 p-4 sm:p-5"><div className="mb-4 flex items-center justify-between"><div className="flex items-center gap-2"><History className="h-5 w-5 text-clinical-600" /><h2 className="section-title">工作紀錄</h2></div><span className="text-xs text-slate-500">{items.length} 筆</span></div><StatePanel loading={jobs.loading || training.loading} error={jobs.error || training.error} onRetry={refresh} empty={!items.length} emptyTitle="沒有符合條件的工作" emptyDescription="調整篩選，或建立新的影像／訓練工作。"><div className="hidden table-wrap md:block"><table className="data-table"><thead><tr><th>工作</th><th>類型</th><th>狀態</th><th>建立時間</th><th>操作</th></tr></thead><tbody>{items.map((item) => { const id = jobIdOf(item.record); return <tr key={`${item.isTraining}-${id}`}><td><p className="max-w-[14rem] truncate font-semibold">{item.record.name || '未命名工作'}</p><p className="text-xs text-slate-400">{id.slice(0, 12)}</p></td><td>{item.isTraining ? '模型訓練' : item.record.kind || '背景工作'}</td><td><StatusBadge status={item.record.status} /></td><td>{formatDate(item.record.created_at)}</td><td><div className="flex gap-1">{item.isTraining ? <Link className="btn-ghost" to={`/training/${id}`}><Eye className="h-4 w-4" /></Link> : <button className="btn-ghost" onClick={() => setSelected(item)} aria-label="查看工作結果"><Eye className="h-4 w-4" /></button>}{!item.isTraining && item.record.status === 'completed' && <a className="btn-ghost" href={api.jobDownloadUrl(id)} aria-label="下載工作結果"><Download className="h-4 w-4" /></a>}<button className="btn-ghost text-rose-600" disabled={['running', 'stopping'].includes(item.record.status)} onClick={() => setDeleteTarget(item)} aria-label="刪除工作"><Trash2 className="h-4 w-4" /></button></div></td></tr>})}</tbody></table></div><div className="space-y-3 md:hidden">{items.map((item) => { const id = jobIdOf(item.record); return <div key={`${item.isTraining}-${id}`} className="rounded-xl border border-slate-200 p-4"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate font-semibold">{item.record.name || '未命名工作'}</p><p className="mt-1 text-xs text-slate-500">{item.isTraining ? '模型訓練' : item.record.kind} · {formatDate(item.record.created_at)}</p></div><StatusBadge status={item.record.status} /></div><ProgressBar value={normalizeProgress(item.record.progress)} label="進度" /><div className="mt-3 flex justify-end gap-2">{item.isTraining ? <Link className="btn-secondary" to={`/training/${id}`}>查看監控</Link> : <button className="btn-secondary" onClick={() => setSelected(item)}>查看結果</button>}<button className="btn-ghost text-rose-600" disabled={['running', 'stopping'].includes(item.record.status)} onClick={() => setDeleteTarget(item)}><Trash2 className="h-4 w-4" /></button></div></div>})}</div></StatePanel></Card>
        <Card className="h-fit p-5"><h2 className="section-title">工作詳情</h2><StatePanel loading={result.loading} error={result.error} onRetry={() => void result.refresh()} empty={!selected} emptyTitle="選擇工作查看" emptyDescription="影像類工作可查看輸出摘要；訓練工作會開啟即時監控頁。">{selected && <div className="mt-4 space-y-4"><div><p className="text-sm font-semibold">{selected.record.name || '未命名工作'}</p><p className="mt-1 break-all text-xs text-slate-500">{jobIdOf(selected.record)}</p></div><div className="grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">狀態</p><div className="mt-1"><StatusBadge status={selected.record.status} /></div></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">結果數</p><p className="mt-1 font-semibold">{selected.record.result_count ?? result.data?.results?.length ?? result.data?.items?.length ?? '—'}</p></div></div>{selected.record.error_message && <InlineNotice tone="danger">{selected.record.error_message}</InlineNotice>}{result.data?.statistics && <div><p className="text-xs font-semibold text-slate-500">結果統計</p><div className="mt-2 space-y-2">{Object.entries(result.data.statistics).map(([key, value]) => <div key={key} className="flex justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm"><span>{key}</span><span className="font-semibold">{value}</span></div>)}</div></div>}{selected.record.status === 'completed' && <a className="btn-primary w-full" href={api.jobDownloadUrl(jobIdOf(selected.record))}><Download className="h-4 w-4" />下載完整結果</a>}</div>}</StatePanel></Card>
      </div>
      <ConfirmDialog open={Boolean(deleteTarget)} title="刪除工作？" description={`將刪除「${deleteTarget?.record.name || '此工作'}」的狀態、設定與本機輸出。執行中工作需先安全停止。`} busy={busy} onCancel={() => setDeleteTarget(undefined)} onConfirm={() => void remove()} />
    </div>
  )
}
