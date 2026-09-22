import { WorkflowSource, HandoffActions } from '../components/Workflow'
import { useWorkflowJob } from '../lib/workflow'
import { Download, Play, ScanLine } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Dropzone } from '../components/Dropzone'
import { FilePreviewGallery } from '../components/PreviewGallery'
import { Card, InlineNotice, PageHeader, ProgressBar, StatePanel, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, apiUrl, humanApiError, listItems } from '../lib/api'
import { jobIdOf, normalizeProgress } from '../lib/format'
import type { JobResults, ModelInfo } from '../types/api'

export function MasksPage() {
  const loadModels = useCallback(async (signal?: AbortSignal) => listItems<ModelInfo>(await api.listModels(signal)), [])
  const models = useAsyncResource(loadModels, true, 'models')
  const unetModels = useMemo(() => (models.data || []).filter((model) => model.task === 'segmentation' || `${model.architecture} ${model.name}`.toLowerCase().includes('unet')), [models.data])
  const [files, setFiles] = useState<File[]>([])
  const [searchParams] = useSearchParams()
  const [modelId, setModelId] = useState(searchParams.get('model_id') || '')
  const [refine, setRefine] = useState(true)
  const workflow = useWorkflowJob('masks')
  const { job, setJob } = workflow
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<JobResults>()
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [job?.id])
  const [resultsLoading, setResultsLoading] = useState(false)
  const stream = useJobEvents(job ? api.jobEventsUrl(jobIdOf(job)) : undefined, Boolean(job) && !['completed','failed','stopped','interrupted','cancelled'].includes(job?.status || ''))
  const currentStatus = stream.latest?.status || job?.status
  const running = ['queued', 'running', 'stopping'].includes(currentStatus || '')
  useEffect(() => { if (!modelId && unetModels.length) setModelId(unetModels.find((model) => model.is_active || model.is_default)?.id || unetModels[0].id) }, [modelId, unetModels])
  useEffect(() => {
    if (!job || currentStatus !== 'completed') return
    let cancelled = false
    setResultsLoading(true)
    api.getJobResults(jobIdOf(job), page)
      .then((value) => { if (!cancelled) setResults(value) })
      .catch((reason) => { if (!cancelled) setError(humanApiError(reason)) })
      .finally(() => { if (!cancelled) setResultsLoading(false) })
    return () => { cancelled = true }
  }, [currentStatus, job, page])

  const run = async () => {
    if ((!files.length && !workflow.ready) || !modelId) return
    setBusy(true); setError(null)
    setResults(undefined)
    try {
      const form = new FormData(); form.append('kind', 'masks'); form.append('name', `UNet 遮罩 ${new Date().toLocaleString('zh-TW')}`); files.forEach((file) => form.append('files', file)); form.append('model_id', modelId); form.append('config', JSON.stringify({ model_id: modelId, refine, output_folder: 'IMG_Mask' }))
      const created = await workflow.create(form)
      setJob(created)
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="UNet 遮罩產生" description="使用本機 `.pth` 模型為單張或批次影像產生 IMG_Mask，並追蹤逐張處理進度。" />
      <WorkflowSource {...workflow} />
      <div className={workflow.active ? 'grid gap-6' : 'grid gap-6 xl:grid-cols-[1.15fr_.85fr]'}>
        {!workflow.active && <Card className="p-5 sm:p-6"><h2 className="section-title">1. 選擇圖片</h2><p className="mt-1 text-sm text-slate-500">遮罩輸出保存在獨立工作目錄。</p><div className="mt-4"><Dropzone files={files} onFiles={setFiles} disabled={busy || workflow.active} accept="image/*,.jfif,.zip" /></div>{files.length > 0 && <div className="mt-5"><FilePreviewGallery files={files} /></div>}</Card>}
        <Card className="p-5 sm:p-6"><div className="flex items-center gap-2"><ScanLine className="h-5 w-5 text-clinical-600" /><h2 className="section-title">2. 選擇 UNet 模型</h2></div><StatePanel loading={models.loading} error={models.error} onRetry={() => void models.refresh()} empty={!unetModels.length} emptyTitle="尚未安裝 UNet 模型" emptyDescription="請先到模型管理匯入 UNet `.pth` 並補充架構資訊；服務仍可正常使用其他功能。"><label className="mt-4 block"><span className="label">模型</span><select className="field" value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={busy || running}>{modelId && !unetModels.some(model => model.id === modelId) && <option value={modelId}>指定模型不存在，請重新選擇</option>}{unetModels.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.architecture || 'UNet'}{model.is_active || model.is_default ? '（預設）' : ''}</option>)}</select></label><label className="mt-4 flex items-start gap-3 rounded-xl border border-slate-200 p-3"><input type="checkbox" checked={refine} onChange={(event) => setRefine(event.target.checked)} className="mt-0.5 h-5 w-5 rounded border-slate-300 text-clinical-600" /><span><span className="block text-sm font-semibold text-slate-700">清理遮罩雜訊</span><span className="mt-1 block text-xs leading-5 text-slate-500">沿用既有最大連通區域與填洞處理。</span></span></label></StatePanel>
          {error && <div className="mt-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}
          {job && <div className="mt-4 space-y-3 rounded-xl bg-slate-50 p-4"><div className="flex justify-between gap-3"><div><p className="text-sm font-semibold">{jobIdOf(job).slice(0, 8)}</p><p className="text-xs text-slate-500">{stream.latest?.message || '等待更新'}</p></div><StatusBadge status={currentStatus} /></div><ProgressBar value={normalizeProgress(stream.latest?.progress ?? job.progress)} label="遮罩進度" detail={stream.latest?.payload?.processed !== undefined ? `${stream.latest.payload.processed} / ${stream.latest.payload.total ?? '?'}` : undefined} />{currentStatus === 'completed' && <SuccessMessage>遮罩已完成，可下載 IMG_Mask 結果。</SuccessMessage>}</div>}
          <div className="mt-5 flex flex-wrap justify-end gap-2">{job && <a className="btn-secondary" href={api.jobDownloadUrl(jobIdOf(job))}><Download className="h-4 w-4" />下載遮罩</a>}<button className="btn-primary" disabled={(!files.length && !workflow.ready) || !unetModels.some(model => model.id === modelId) || busy || running || !unetModels.length} onClick={() => void run()} title={!unetModels.length ? '需先安裝 UNet 模型' : undefined}><Play className="h-4 w-4" />{busy ? '建立工作中…' : '產生遮罩'}</button></div>
          {job && <p className="mt-3 text-xs text-slate-500">模型檔不會送往外部服務；工作輸出下載大小由後端安全限制管理。{job.result_count ? ` 已完成 ${job.result_count} 張。` : ''}</p>}
        </Card>
      </div>
      {job && currentStatus === 'completed' && <Card className="mt-6 p-5 sm:p-6">
        <div><h2 className="section-title">原圖／遮罩成對預覽</h2><p className="mt-1 text-sm text-slate-500">預覽僅由此工作的受管目錄提供，不會公開本機檔案路徑。</p></div>
        <div className="mt-5"><StatePanel loading={resultsLoading} empty={!results?.mask_previews?.length} emptyTitle="沒有可顯示的遮罩預覽" emptyDescription="仍可下載工作壓縮檔查看完整輸出。">
          <div className="grid gap-5 md:grid-cols-2">{results?.mask_previews?.map((preview, index) => <article key={`${preview.name}-${index}`} className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50"><p className="truncate border-b border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700">{preview.name}</p><div className="grid grid-cols-2 gap-px bg-slate-200"><figure className="bg-white p-3"><img className="aspect-square w-full rounded-lg object-contain" src={apiUrl(preview.source_url)} alt={`${preview.name} 原圖`} loading="lazy" /><figcaption className="mt-2 text-center text-xs font-medium text-slate-500">原圖</figcaption></figure><figure className="bg-white p-3"><img className="aspect-square w-full rounded-lg object-contain" src={apiUrl(preview.mask_url)} alt={`${preview.name} 遮罩`} loading="lazy" /><figcaption className="mt-2 text-center text-xs font-medium text-slate-500">Mask</figcaption></figure></div></article>)}</div>
        </StatePanel></div>
      </Card>}
      {results && <div className="mt-4 flex items-center gap-3"><button className="btn-secondary" disabled={page === 0} onClick={() => setPage(p => p-1)}>上一頁結果</button><span>{page+1} / {Math.max(1, Math.ceil((results.total || 0)/60))}</span><button className="btn-secondary" disabled={(page+1)*60 >= (results.total || 0)} onClick={() => setPage(p => p+1)}>下一頁結果</button></div>}
      <HandoffActions job={job} status={currentStatus} datasetId={workflow.datasetId} />
    </div>
  )
}
