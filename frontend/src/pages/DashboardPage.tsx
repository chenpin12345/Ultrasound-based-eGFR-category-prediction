import { Activity, BrainCircuit, Database, Download, HardDrive, Play, Sparkles } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Dropzone } from '../components/Dropzone'
import { FilePreviewGallery } from '../components/PreviewGallery'
import { Card, InlineNotice, PageHeader, ProgressBar, StatePanel, StatCard, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, humanApiError, listItems, requestJson } from '../lib/api'
import { formatDate, jobIdOf, normalizeProgress } from '../lib/format'
import type { Job, ModelInfo } from '../types/api'

export function DashboardPage() {
  const loadHealth = useCallback(() => api.health(), [])
  const loadJobs = useCallback(async (signal?: AbortSignal) => listItems<Job>(await api.listJobs(signal)), [])
  const loadModels = useCallback(async (signal?: AbortSignal) => listItems<ModelInfo>(await api.listModels(signal)), [])
  const loadCounts = useCallback((signal?: AbortSignal) => requestJson<{datasets: number; models: number; active_jobs: number}>('/workflow/dashboard-summary', {signal}), [])
  const counts = useAsyncResource(loadCounts, true, 'dashboard-summary')
  const health = useAsyncResource(loadHealth)
  const jobs = useAsyncResource(loadJobs, true, 'jobs')
  const models = useAsyncResource(loadModels, true, 'models')
  const [files, setFiles] = useState<File[]>([])
  const [quickJob, setQuickJob] = useState<Job>()
  const [quickBusy, setQuickBusy] = useState(false)
  const [quickError, setQuickError] = useState<string | null>(null)
  const eventStream = useJobEvents(quickJob ? api.jobEventsUrl(jobIdOf(quickJob)) : undefined, Boolean(quickJob) && !['completed','failed','stopped','interrupted','cancelled'].includes(quickJob?.status || ''))
  const latestProgress = normalizeProgress(eventStream.latest?.progress ?? quickJob?.progress)
  const recentJobs = useMemo(() => [...(jobs.data || [])].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).slice(0, 5), [jobs.data])
  const runningCount = counts.data?.active_jobs ?? '—'
  const isActive = (model: ModelInfo) => Boolean(model.is_active ?? model.is_default ?? model.active)
  const modelReady = (models.data || []).some((model) => isActive(model) && (model.task === 'segmentation' || `${model.architecture} ${model.name}`.toLowerCase().includes('unet')))
    && (models.data || []).some((model) => isActive(model) && (model.task === 'classification' || (model.task === undefined && !`${model.architecture} ${model.name}`.toLowerCase().includes('unet'))))

  const runQuickAnalysis = async () => {
    if (!files.length || !modelReady) return
    setQuickBusy(true)
    setQuickError(null)
    try {
      const form = new FormData()
      form.append('kind', 'quick_analysis')
      form.append('name', `快速分析 ${new Date().toLocaleString('zh-TW')}`)
      form.append('config', JSON.stringify({ mode: 'quick_analysis', steps: ['convert', 'crop', 'rb', 'masks', 'features', 'inference'], use_default_models: true, preserve_originals: true }))
      files.forEach((file) => form.append('files', file))
      const created = await api.createJob(form)
      setQuickJob(created)
      void jobs.refresh()
    } catch (error) {
      setQuickError(humanApiError(error))
    } finally {
      setQuickBusy(false)
    }
  }

  return (
    <div>
      <PageHeader title="研究儀表板" description="從單一工作台掌握本機資料集、模型與背景工作，或直接開始一次完整影像分析。" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="服務狀態" value={health.loading ? '檢查中' : health.data?.status === 'ok' || health.data?.status === 'healthy' ? '正常' : '需檢查'} hint={health.data?.database ? `資料庫：${health.data.database}` : '本機 FastAPI'} icon={<Activity className="h-5 w-5" />} />
        <StatCard label="資料集" value={counts.data?.datasets ?? '—'} hint="已匯入研究資料" icon={<Database className="h-5 w-5" />} />
        <StatCard label="可用模型" value={counts.data?.models ?? '—'} hint={modelReady ? '遮罩與分類模型均已就緒' : '快速分析所需模型未齊'} icon={<BrainCircuit className="h-5 w-5" />} />
        <StatCard label="進行中工作" value={runningCount} hint="包含排隊與停止中" icon={<HardDrive className="h-5 w-5" />} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <Card className="p-5 sm:p-6">
          <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-clinical-600" /><h2 className="section-title">快速影像分析</h2></div><p className="mt-1 text-sm leading-6 text-slate-500">使用預設順序完成影像處理、UNet 遮罩、特徵擷取及分類推論。</p></div>
            <span className="rounded-full bg-clinical-50 px-3 py-1 text-xs font-semibold text-clinical-700">一鍵流程</span>
          </div>
          {!modelReady && !models.loading && <InlineNotice tone="warning" title="分析模型尚未齊全">請先到「模型管理」匯入 UNet 與分類 `.pth`，或完成一次模型訓練。快速分析在兩類模型就緒前保持停用。</InlineNotice>}
          <div className="mt-4"><Dropzone files={files} onFiles={setFiles} disabled={quickBusy} /></div>
          {files.length > 0 && <div className="mt-4"><FilePreviewGallery files={files} /></div>}
          {quickError && <div className="mt-4"><InlineNotice tone="danger">{quickError}</InlineNotice></div>}
          {quickJob && (
            <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3"><div><p className="text-sm font-semibold text-slate-800">工作 {jobIdOf(quickJob).slice(0, 8)}</p><p className="text-xs text-slate-500">{eventStream.latest?.message || quickJob.message || '工作已建立，等待更新。'}</p></div><StatusBadge status={eventStream.latest?.status || quickJob.status} /></div>
              <ProgressBar value={latestProgress} label="整體進度" />
              {(eventStream.latest?.status === 'completed' || quickJob.status === 'completed') && <SuccessMessage>分析完成，可前往歷史工作查看結果或下載封裝檔。</SuccessMessage>}
            </div>
          )}
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            {quickJob && <a className="btn-secondary" href={api.jobDownloadUrl(jobIdOf(quickJob))}><Download className="h-4 w-4" />下載結果</a>}
            <button className="btn-primary" disabled={!files.length || !modelReady || quickBusy} onClick={runQuickAnalysis} title={!modelReady ? '需先安裝模型' : !files.length ? '請先選擇圖片' : undefined}><Play className="h-4 w-4" />{quickBusy ? '建立工作中…' : '開始分析'}</button>
          </div>
        </Card>

        <Card className="p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between"><div><h2 className="section-title">最近工作</h2><p className="mt-1 text-sm text-slate-500">重新整理頁面後仍可查看</p></div><Link to="/jobs" className="text-sm font-semibold text-clinical-700 hover:text-clinical-900">查看全部</Link></div>
          <StatePanel loading={jobs.loading} error={jobs.error} onRetry={() => void jobs.refresh()} empty={!recentJobs.length} emptyTitle="尚無工作紀錄" emptyDescription="上傳圖片或建立訓練工作後，狀態會顯示在這裡。">
            <div className="space-y-3">
              {recentJobs.map((job) => <div key={jobIdOf(job)} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3"><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-800">{job.name || job.kind || '背景工作'}</p><p className="mt-0.5 text-xs text-slate-500">{formatDate(job.created_at)} · {jobIdOf(job).slice(0, 8)}</p></div><StatusBadge status={job.status} /></div>)}
            </div>
          </StatePanel>
        </Card>
      </div>
    </div>
  )
}
