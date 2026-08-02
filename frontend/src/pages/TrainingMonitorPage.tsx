import { Activity, Cpu, Download, Gauge, MemoryStick, Pause, Play, Radio, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Card, InlineNotice, PageHeader, ProgressBar, StatePanel, StatCard, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, apiUrl, humanApiError, listItems } from '../lib/api'
import { formatDuration, formatPercent, jobIdOf, normalizeProgress } from '../lib/format'
import type { EpochMetric, ResourceSnapshot, TrainingJob, TrainingLogEntry } from '../types/api'

function metricFromPayload(payload?: Record<string, unknown>): EpochMetric | undefined {
  if (!payload) return undefined
  const source = (payload.metric && typeof payload.metric === 'object' ? payload.metric : payload) as Record<string, unknown>
  if (typeof source.epoch !== 'number') return undefined
  return source as unknown as EpochMetric
}

export function TrainingMonitorPage() {
  const { jobId: routeJobId } = useParams()
  const navigate = useNavigate()
  const loadJobs = useCallback(async () => listItems<TrainingJob>(await api.listTrainingJobs()), [])
  const jobs = useAsyncResource(loadJobs)
  const [selectedId, setSelectedId] = useState(routeJobId || '')
  const activeId = routeJobId || selectedId
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmStop, setConfirmStop] = useState(false)

  useEffect(() => {
    if (routeJobId) setSelectedId(routeJobId)
    else if (!selectedId && jobs.data?.length) {
      const id = jobIdOf(jobs.data[0]); setSelectedId(id)
      navigate(`/training/${id}`, { replace: true })
    }
  }, [jobs.data, navigate, routeJobId, selectedId])

  const detailLoader = useCallback(() => api.getTrainingJob(activeId), [activeId])
  const metricsLoader = useCallback(() => api.getTrainingMetrics(activeId), [activeId])
  const artifactsLoader = useCallback(() => api.getTrainingArtifacts(activeId), [activeId])
  const detail = useAsyncResource(detailLoader, Boolean(activeId))
  const metrics = useAsyncResource(metricsLoader, Boolean(activeId))
  const artifacts = useAsyncResource(artifactsLoader, Boolean(activeId))
  const stream = useJobEvents(activeId ? api.trainingEventsUrl(activeId) : undefined, Boolean(activeId))
  const status = stream.latest?.status || detail.data?.status
  const running = ['queued', 'running', 'stopping'].includes(status || '')
  const refreshDetail = detail.refresh
  const refreshMetrics = metrics.refresh

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => { void refreshDetail(); void refreshMetrics() }, 10_000)
    return () => window.clearInterval(timer)
  }, [refreshDetail, refreshMetrics, running])

  useEffect(() => {
    if (['metric', 'metrics', 'epoch_completed', 'result', 'completed'].includes(stream.latest?.type || '')) void refreshMetrics()
    if (stream.latest?.status) void refreshDetail()
  }, [refreshDetail, refreshMetrics, stream.latest])

  const history = useMemo(() => {
    const saved = metrics.data?.history || metrics.data?.items || []
    const merged = new Map(saved.map((item) => [item.epoch, item]))
    for (const event of stream.events) {
      const item = metricFromPayload(event.payload)
      if (item) merged.set(item.epoch, { ...merged.get(item.epoch), ...item })
    }
    return [...merged.values()].sort((a, b) => a.epoch - b.epoch)
  }, [metrics.data, stream.events])
  const latestMetric = history.at(-1) || metrics.data?.latest
  const eventResources = [...stream.events].reverse().map((event) => event.payload?.resources || (event.type === 'resource_sample' ? event.payload : undefined)).find((value) => value && typeof value === 'object') as ResourceSnapshot | undefined
  const resources = eventResources || metrics.data?.resources || {}
  const logs: TrainingLogEntry[] = useMemo(() => {
    const saved = metrics.data?.logs || []
    const live = stream.events.filter((event) => event.type === 'log' || event.payload?.log).map((event) => ({ id: event.id, timestamp: event.timestamp || event.created_at, level: String(event.payload?.level || 'INFO'), message: String(event.payload?.log || event.message || '') }))
    return [...saved, ...live].slice(-500)
  }, [metrics.data?.logs, stream.events])
  const progress = detail.data?.total_epochs ? ((detail.data.current_epoch || 0) / detail.data.total_epochs) * 100 : normalizeProgress(stream.latest?.progress ?? detail.data?.progress)

  const stop = async () => {
    if (!activeId) return
    setActionBusy(true); setActionError(null)
    try { await api.stopTrainingJob(activeId); setConfirmStop(false); await detail.refresh() } catch (error) { setActionError(humanApiError(error)) } finally { setActionBusy(false) }
  }
  const resume = async () => {
    if (!activeId) return
    setActionBusy(true); setActionError(null)
    try { const resumed = await api.resumeTrainingJob(activeId); const id = jobIdOf(resumed) || activeId; await jobs.refresh(); navigate(`/training/${id}`); await detail.refresh() } catch (error) { setActionError(humanApiError(error)) } finally { setActionBusy(false) }
  }

  return (
    <div>
      <PageHeader title="訓練監控" description="即時查看 epoch、loss、accuracy、資源與日誌；離開此頁或重新整理不會停止背景訓練。" actions={<><button className="btn-secondary" onClick={() => { void detail.refresh(); void metrics.refresh(); void artifacts.refresh() }} disabled={!activeId}><RefreshCw className="h-4 w-4" />更新</button>{running && status !== 'stopping' && <button className="btn-danger" onClick={() => setConfirmStop(true)} disabled={actionBusy}><Pause className="h-4 w-4" />安全停止</button>}{['stopped', 'interrupted', 'failed'].includes(status || '') && <button className="btn-primary" onClick={() => void resume()} disabled={actionBusy}><Play className="h-4 w-4" />從 checkpoint 恢復</button>}</>} />
      <Card className="mb-6 p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center"><label className="min-w-0 flex-1"><span className="label">訓練工作</span><select className="field" value={activeId} onChange={(event) => navigate(`/training/${event.target.value}`)} disabled={jobs.loading || !jobs.data?.length}><option value="">選擇訓練工作</option>{jobs.data?.map((job) => <option key={jobIdOf(job)} value={jobIdOf(job)}>{job.name || job.architecture || '訓練工作'} · {jobIdOf(job).slice(0, 8)} · {job.status}</option>)}</select></label><div className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600"><Radio className={`h-4 w-4 ${stream.state === 'connected' ? 'text-emerald-600' : 'text-amber-600'}`} /><span>SSE：{stream.state === 'connected' ? '已連線' : stream.state === 'reconnecting' ? '重新連線中' : '等待連線'}</span></div></div></Card>
      {actionError && <div className="mb-4"><InlineNotice tone="danger">{actionError}</InlineNotice></div>}
      <StatePanel loading={jobs.loading || (Boolean(activeId) && detail.loading)} error={jobs.error || detail.error} onRetry={() => { void jobs.refresh(); void detail.refresh() }} empty={!activeId} emptyTitle="尚無訓練工作" emptyDescription="先到模型訓練頁建立工作，便可在此查看即時狀態。">
        {detail.data && <div className="space-y-6">
          <Card className="p-5 sm:p-6"><div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-bold text-ink">{detail.data.name || '模型訓練'}</h2><StatusBadge status={status} /></div><p className="mt-1 text-sm text-slate-500">ID {activeId} · {detail.data.architecture || '—'} · {detail.data.dataset_name || detail.data.dataset_id || '—'}</p></div><div className="text-left md:text-right"><p className="text-sm font-semibold text-slate-700">Epoch {detail.data.current_epoch || latestMetric?.epoch || 0} / {detail.data.total_epochs || '—'}</p><p className="mt-1 text-xs text-slate-500">Batch {detail.data.current_batch || 0} / {detail.data.total_batches || '—'}</p></div></div><div className="mt-5"><ProgressBar value={progress} label={stream.latest?.message || '訓練進度'} detail={`${progress.toFixed(1)}%`} /></div>{status === 'stopping' && <div className="mt-4"><InlineNotice tone="warning">正在等待安全停止點並保存 checkpoint，請勿強制關閉服務。</InlineNotice></div>}{status === 'completed' && <div className="mt-4"><SuccessMessage>訓練完成，最佳模型已加入模型管理。</SuccessMessage></div>}</Card>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="Training loss" value={latestMetric?.train_loss?.toFixed(4) ?? '—'} hint={`Validation ${String(latestMetric?.validation_loss ?? latestMetric?.val_loss ?? '—')}`} icon={<Activity className="h-5 w-5" />} /><StatCard label="Training accuracy" value={latestMetric?.train_accuracy !== undefined ? formatPercent(latestMetric.train_accuracy, latestMetric.train_accuracy <= 1) : '—'} hint={`Validation ${latestMetric?.validation_accuracy !== undefined || latestMetric?.val_accuracy !== undefined ? formatPercent(latestMetric.validation_accuracy ?? latestMetric.val_accuracy, (latestMetric.validation_accuracy ?? latestMetric.val_accuracy ?? 0) <= 1) : '—'}`} icon={<Gauge className="h-5 w-5" />} /><StatCard label="已訓練時間" value={formatDuration(detail.data.elapsed_seconds)} hint={`預估剩餘 ${formatDuration(detail.data.estimated_remaining_seconds)}`} icon={<Cpu className="h-5 w-5" />} /><StatCard label="Learning rate" value={latestMetric?.learning_rate?.toExponential(2) ?? '—'} hint={`最佳 epoch ${detail.data.best_epoch ?? '—'}`} icon={<MemoryStick className="h-5 w-5" />} /></div>
          <div className="grid gap-6 xl:grid-cols-2"><Card className="p-5"><h2 className="section-title">Loss 曲線</h2><div className="mt-4 h-72"><ResponsiveContainer width="100%" height="100%"><LineChart data={history}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="epoch" /><YAxis width={48} /><Tooltip /><Legend /><Line type="monotone" dataKey="train_loss" name="Training" stroke="#2d9184" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="validation_loss" name="Validation" stroke="#ef7d79" strokeWidth={2} dot={false} connectNulls /><Line type="monotone" dataKey="val_loss" name="Validation" stroke="#ef7d79" strokeWidth={2} dot={false} connectNulls /></LineChart></ResponsiveContainer></div></Card><Card className="p-5"><h2 className="section-title">Accuracy 與 learning rate</h2><div className="mt-4 h-72"><ResponsiveContainer width="100%" height="100%"><LineChart data={history}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="epoch" /><YAxis yAxisId="left" width={48} /><YAxis yAxisId="right" orientation="right" width={56} /><Tooltip /><Legend /><Line yAxisId="left" type="monotone" dataKey="train_accuracy" name="Train accuracy" stroke="#2d9184" strokeWidth={2} dot={false} /><Line yAxisId="left" type="monotone" dataKey="validation_accuracy" name="Val accuracy" stroke="#4085b6" strokeWidth={2} dot={false} connectNulls /><Line yAxisId="left" type="monotone" dataKey="val_accuracy" name="Val accuracy" stroke="#4085b6" strokeWidth={2} dot={false} connectNulls /><Line yAxisId="right" type="monotone" dataKey="learning_rate" name="Learning rate" stroke="#d99a30" strokeDasharray="4 3" dot={false} /></LineChart></ResponsiveContainer></div></Card></div>
          <div className="grid gap-6 xl:grid-cols-[.75fr_1.25fr]"><Card className="p-5"><h2 className="section-title">系統資源</h2><div className="mt-4 space-y-4"><ProgressBar value={resources.cpu_percent || 0} label="CPU 使用量" /><ProgressBar value={resources.memory_percent || 0} label="記憶體使用量" />{resources.gpu_name ? <><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">GPU</p><p className="mt-1 text-sm font-semibold">{resources.gpu_name}</p></div><ProgressBar value={resources.gpu_percent || 0} label="GPU 使用量" /><ProgressBar value={resources.gpu_memory_percent || 0} label="GPU 記憶體" detail={resources.gpu_memory_used_mb !== undefined ? `${resources.gpu_memory_used_mb} / ${resources.gpu_memory_total_mb || '?'} MB` : undefined} /></> : <InlineNotice tone="info">目前未回報 GPU；CPU 訓練仍可正常執行。</InlineNotice>}</div></Card><Card className="p-5"><div className="flex items-center justify-between"><h2 className="section-title">即時訓練日誌</h2><span className="text-xs text-slate-500">僅追加最新 {logs.length} 筆</span></div><div className="mt-4 h-[22rem] overflow-auto rounded-xl bg-[#102c33] p-4 font-mono text-xs leading-6 text-slate-200" aria-live="polite">{logs.length ? logs.map((log, index) => <div key={String(log.id ?? index)} className="border-b border-white/5 py-0.5"><span className="mr-2 text-slate-500">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString('zh-TW') : '--:--:--'}</span><span className={log.level === 'ERROR' ? 'text-rose-300' : log.level === 'WARNING' ? 'text-amber-300' : 'text-clinical-200'}>{log.level || 'INFO'}</span><span className="ml-2 break-words">{log.message}</span></div>) : <p className="text-slate-400">等待日誌事件；敏感檔名與本機路徑不應出現在此處。</p>}</div></Card></div>
          {(metrics.data?.confusion_matrix || latestMetric?.confusion_matrix) && <Card className="p-5"><h2 className="section-title">混淆矩陣</h2><div className="mt-4 overflow-x-auto"><div className="grid min-w-[22rem] gap-1" style={{ gridTemplateColumns: `repeat(${(metrics.data?.confusion_matrix || latestMetric?.confusion_matrix || []).length}, minmax(3.5rem, 1fr))` }}>{(metrics.data?.confusion_matrix || latestMetric?.confusion_matrix || []).flatMap((row, rowIndex) => row.map((value, columnIndex) => <div key={`${rowIndex}-${columnIndex}`} className="grid aspect-square place-items-center rounded-lg bg-clinical-50 text-sm font-bold text-clinical-900" style={{ opacity: 0.35 + Math.min(0.65, value / Math.max(...row, 1)) }}>{value}</div>))}</div></div></Card>}
          <Card className="p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="section-title">訓練產出</h2><p className="mt-1 text-sm text-slate-500">Checkpoint、最佳模型、指標、設定與歷史 CSV。</p></div><a className="btn-secondary" href={apiUrl(`/training/jobs/${encodeURIComponent(activeId)}/metrics?download=1`)}><Download className="h-4 w-4" />下載指標</a></div><StatePanel loading={artifacts.loading} error={artifacts.error} onRetry={() => void artifacts.refresh()} empty={!artifacts.data?.length} emptyTitle="尚無可下載產出" emptyDescription={running ? '訓練進行中，產出會在 checkpoint 或完成後出現。' : '後端尚未登錄產出檔案。'}><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{artifacts.data?.map((artifact) => <div key={artifact.id || artifact.name} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3"><Download className="h-4 w-4 text-clinical-600" /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{artifact.name}</p><p className="text-xs text-slate-500">{artifact.kind || '訓練產出'}</p></div>{artifact.download_url ? <a className="text-xs font-semibold text-clinical-700" href={apiUrl(artifact.download_url)}>下載</a> : <span className="text-xs text-slate-400" title="後端未提供下載連結">未就緒</span>}</div>)}</div></StatePanel></Card>
        </div>}
      </StatePanel>
      <ConfirmDialog open={confirmStop} title="安全停止訓練？" description="系統會等待安全時機、保存可恢復 checkpoint，再將狀態標示為 stopped。請勿直接關閉服務。" confirmLabel="停止並保存" busy={actionBusy} onCancel={() => setConfirmStop(false)} onConfirm={() => void stop()} />
    </div>
  )
}
