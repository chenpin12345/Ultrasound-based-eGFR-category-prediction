import { WorkflowSource, HandoffActions } from '../components/Workflow'
import { useWorkflowJob } from '../lib/workflow'
import { Download, FileSpreadsheet, Microscope, Play } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Dropzone } from '../components/Dropzone'
import { Card, InlineNotice, PageHeader, ProgressBar, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, humanApiError } from '../lib/api'
import { jobIdOf, normalizeProgress } from '../lib/format'
import type { JobResults } from '../types/api'

const outputFields = ['image_name', 'age', 'gender', 'Length_px', 'Entropy', 'Contrast_Ratio', 'has_diabetes']

export function FeaturesPage() {
  const [images, setImages] = useState<File[]>([])
  const [masks, setMasks] = useState<File[]>([])
  const [metadata, setMetadata] = useState<File>()
  const workflow = useWorkflowJob('features')
  const { job, setJob } = workflow
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stream = useJobEvents(job ? api.jobEventsUrl(jobIdOf(job)) : undefined, Boolean(job) && !['completed','failed','stopped','interrupted','cancelled'].includes(job?.status || ''))
  const currentStatus = stream.latest?.status || job?.status
  const running = ['queued', 'running', 'stopping'].includes(currentStatus || '')
  const resultsLoader = useCallback(() => api.getJobResults(job ? jobIdOf(job) : ''), [job])
  const results = useAsyncResource<JobResults>(resultsLoader, Boolean(job) && currentStatus === 'completed')
  const refreshResults = results.refresh
  useEffect(() => { if (currentStatus === 'completed') void refreshResults() }, [currentStatus, refreshResults])

  const run = async () => {
    if ((!images.length && !workflow.ready)) return
    setBusy(true); setError(null)
    try {
      const form = new FormData(); form.append('kind', 'features'); form.append('name', `特徵擷取 ${new Date().toLocaleString('zh-TW')}`)
      images.forEach((file) => form.append('files', file)); masks.forEach((file) => form.append('mask_files', file)); if (metadata) form.append('metadata_file', metadata)
      form.append('config', JSON.stringify({ fields: outputFields, encoding: 'utf-8-sig', use_train_stats: true, match_by_file_name: true }))
      const created = await workflow.create(form)
      setJob(created)
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="特徵擷取" description="依圖片與 mask 計算 Length_px、Entropy、Contrast_Ratio，合併 metadata 並匯出欄位順序固定的 UTF-8 BOM CSV。" />
      <WorkflowSource {...workflow} />
      {!workflow.active && <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <Card className="p-5"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-clinical-50 text-sm font-bold text-clinical-700">1</span><h2 className="section-title">來源圖片</h2></div><div className="mt-4"><Dropzone files={images} onFiles={setImages} disabled={busy || workflow.active} title="拖放待分析圖片" description="圖片為必要輸入，可選擇多張或 ZIP。" /></div></Card>
        <Card className="p-5"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-clinical-50 text-sm font-bold text-clinical-700">2</span><h2 className="section-title">Mask</h2></div><div className="mt-4"><Dropzone files={masks} onFiles={setMasks} disabled={busy || workflow.active} title="拖放 IMG_Mask" description="選填；缺少對應 mask 的圖片會列入結果提醒。" /></div></Card>
        <Card className="p-5 lg:col-span-2 xl:col-span-1"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-clinical-50 text-sm font-bold text-clinical-700">3</span><h2 className="section-title">Metadata</h2></div><label className="mt-4 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 p-5 text-center hover:border-clinical-400"><FileSpreadsheet className="h-7 w-7 text-clinical-600" /><span className="mt-3 text-sm font-semibold text-slate-700">{metadata?.name || '選擇 metadata CSV'}</span><span className="mt-1 text-xs text-slate-500">可包含 age、gender、has_diabetes</span><input className="sr-only" type="file" accept=".csv,text/csv" disabled={busy || workflow.active} onChange={(event) => setMetadata(event.target.files?.[0])} /></label></Card>
      </div>}
      <Card className="mt-6 p-5 sm:p-6">
        <div className="flex items-center gap-2"><Microscope className="h-5 w-5 text-clinical-600" /><h2 className="section-title">輸出設定與執行狀態</h2></div>
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">CSV 欄位順序</p><div className="mt-2 flex flex-wrap gap-2">{outputFields.map((field, index) => <span key={field} className="rounded-lg bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200">{index + 1}. {field}</span>)}</div><p className="mt-3 text-xs text-slate-500">正規化統計由後端使用 `features/train_stats.json` 的既有值；下載採 UTF-8 BOM。</p></div>
        {!masks.length && images.length > 0 && <div className="mt-4"><InlineNotice tone="warning">目前未附 mask。工作仍可建立，後端會檢查可沿用的 IMG_Mask，並在結果中列出缺漏。</InlineNotice></div>}
        {error && <div className="mt-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}
        {job && <div className="mt-4 space-y-3 rounded-xl border border-slate-200 p-4"><div className="flex justify-between gap-3"><div><p className="text-sm font-semibold">工作 {jobIdOf(job).slice(0, 8)}</p><p className="text-xs text-slate-500">{stream.latest?.message || '等待背景處理'}</p></div><StatusBadge status={currentStatus} /></div><ProgressBar value={normalizeProgress(stream.latest?.progress ?? job.progress)} label="特徵擷取進度" />{currentStatus === 'completed' && <SuccessMessage>CSV 已完成並保存。</SuccessMessage>}</div>}
        {results.data && <div className="mt-4 grid gap-3 md:grid-cols-3">{[['缺少 mask', results.data.missing_masks], ['缺少 metadata', results.data.missing_metadata], ['缺少特徵', results.data.missing_features]].map(([label, values]) => <div key={String(label)} className="rounded-xl bg-slate-50 p-3"><p className="text-sm font-semibold text-slate-700">{String(label)} · {Array.isArray(values) ? values.length : 0}</p>{Array.isArray(values) && values.length > 0 && <p className="mt-1 line-clamp-3 text-xs text-slate-500">{values.slice(0, 5).join('、')}</p>}</div>)}</div>}
        <div className="mt-5 flex flex-wrap justify-end gap-2">{job && <a className="btn-secondary" href={api.jobDownloadUrl(jobIdOf(job))}><Download className="h-4 w-4" />下載 CSV／結果</a>}<button className="btn-primary" disabled={(!images.length && !workflow.ready) || busy || running} onClick={() => void run()}><Play className="h-4 w-4" />{busy ? '建立工作中…' : '開始擷取特徵'}</button></div>
      </Card>
      <HandoffActions job={job} status={currentStatus} datasetId={workflow.datasetId} />
    </div>
  )
}
