import { WorkflowSource, HandoffActions } from '../components/Workflow'
import { useWorkflowJob } from '../lib/workflow'
import { ArrowDown, ArrowUp, Download, FolderInput, Play, RotateCcw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Dropzone } from '../components/Dropzone'
import { FilePreviewGallery } from '../components/PreviewGallery'
import { Card, InlineNotice, PageHeader, ProgressBar, StatusBadge, SuccessMessage } from '../components/ui'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, humanApiError } from '../lib/api'
import { jobIdOf, normalizeProgress } from '../lib/format'

type StepKey = 'convert' | 'crop' | 'rb' | 'assort'
interface ProcessStep { key: StepKey; label: string; description: string; enabled: boolean; overrides: File[] }

const initialSteps: ProcessStep[] = [
  { key: 'convert', label: 'JFIF 轉 JPG', description: '轉換格式；只會刪除工作副本中的 JFIF。', enabled: true, overrides: [] },
  { key: 'crop', label: '批次裁切', description: '依既有規則產生 IMG_Cut 工作結果。', enabled: true, overrides: [] },
  { key: 'rb', label: '藍線移除／RB', description: '移除影像藍線並產生 IMG_RB。', enabled: true, overrides: [] },
  { key: 'assort', label: '圖片分類與分組', description: '依標籤分組 training、validation、test。', enabled: true, overrides: [] },
]

export function ProcessingPage() {
  const [files, setFiles] = useState<File[]>([])
  const [steps, setSteps] = useState<ProcessStep[]>(initialSteps)
  const workflow = useWorkflowJob('process')
  const { job, setJob } = workflow
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stream = useJobEvents(job ? api.jobEventsUrl(jobIdOf(job)) : undefined, Boolean(job) && !['completed','failed','stopped','interrupted','cancelled'].includes(job?.status || ''))
  const activeSteps = steps.filter((step) => step.enabled)
  const progress = normalizeProgress(stream.latest?.progress ?? job?.progress)
  const currentStatus = stream.latest?.status || job?.status
  const running = ['queued', 'running', 'stopping'].includes(currentStatus || '')

  const warnings = useMemo(() => {
    const enabled = steps.filter((step) => step.enabled).map((step) => step.key)
    const messages: string[] = []
    if (enabled.includes('rb') && (!enabled.includes('crop') || enabled.indexOf('rb') < enabled.indexOf('crop')) && !steps.find((step) => step.key === 'rb')?.overrides.length) messages.push('RB 通常以裁切後影像為輸入；目前 Crop 不在 RB 前方，也未指定 RB 專用來源。')
    if (enabled.includes('assort') && !enabled.some((key) => key === 'crop' || key === 'rb') && !steps.find((step) => step.key === 'assort')?.overrides.length) messages.push('圖片分類通常使用 IMG_Cut 或 IMG_RB；目前沒有前置處理或專用來源。')
    if (enabled[0] === 'convert') messages.push('格式轉換只會移除獨立工作副本中的 `.jfif`；原始上傳檔不會被修改。')
    return messages
  }, [steps])

  const moveStep = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= steps.length) return
    setSteps((current) => { const next = [...current]; [next[index], next[target]] = [next[target], next[index]]; return next })
  }

  const run = async () => {
    if ((!files.length && !workflow.ready) || !activeSteps.length) return
    setBusy(true); setError(null)
    try {
      const form = new FormData()
      form.append('kind', 'process')
      form.append('name', `影像處理 ${new Date().toLocaleString('zh-TW')}`)
      files.forEach((file) => form.append('files', file))
      for (const step of steps) step.overrides.forEach((file) => form.append(`override_${step.key}`, file))
      form.append('config', JSON.stringify({
        steps: activeSteps.map((step) => step.key),
        preserve_originals: true,
      }))
      const created = await workflow.create(form)
      setJob(created)
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="影像處理" description="自訂格式轉換、裁切、藍線移除與資料分組的順序；每次執行均使用獨立工作目錄，不修改原始圖片。" actions={<button className="btn-secondary" onClick={() => { setSteps(initialSteps); setJob(undefined); setError(null) }} disabled={busy || running}><RotateCcw className="h-4 w-4" />重設</button>} />
      <WorkflowSource {...workflow} />
      <div className={workflow.active ? 'grid gap-6' : 'grid gap-6 xl:grid-cols-[1fr_1.05fr]'}>
        {!workflow.active && <Card className="p-5 sm:p-6">
          <h2 className="section-title">1. 選擇來源圖片</h2><p className="mt-1 text-sm text-slate-500">接受單張、多張、資料夾內容或 ZIP。</p>
          <div className="mt-4"><Dropzone files={files} onFiles={setFiles} disabled={busy || workflow.active} /></div>
          {files.length > 0 && <div className="mt-5"><FilePreviewGallery files={files} /></div>}
        </Card>}
        <Card className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-3"><div><h2 className="section-title">2. 設定執行順序</h2><p className="mt-1 text-sm text-slate-500">拖曳替代來源可由各步驟使用，不會覆蓋共同來源。</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{activeSteps.length} 個步驟</span></div>
          <div className="mt-4 space-y-3">
            {steps.map((step, index) => (
              <div key={step.key} className={`rounded-xl border p-4 transition ${step.enabled ? 'border-clinical-200 bg-clinical-50/40' : 'border-slate-200 bg-slate-50 opacity-70'}`}>
                <div className="flex items-start gap-3"><label className="mt-0.5 flex items-center"><input type="checkbox" aria-label={step.label} className="h-5 w-5 rounded border-slate-300 text-clinical-600 focus:ring-clinical-500" checked={step.enabled} onChange={(event) => setSteps((current) => current.map((item) => item.key === step.key ? { ...item, enabled: event.target.checked } : item))} /></label><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-white text-xs font-bold text-clinical-700 ring-1 ring-clinical-200">{index + 1}</span><p className="font-semibold text-slate-800">{step.label}</p></div><p className="mt-1 text-xs leading-5 text-slate-500">{step.description}</p></div><div className="flex gap-1"><button className="rounded-lg p-2 text-slate-500 hover:bg-white disabled:opacity-25" disabled={index === 0 || busy} onClick={() => moveStep(index, -1)} aria-label={`${step.label} 上移`}><ArrowUp className="h-4 w-4" /></button><button className="rounded-lg p-2 text-slate-500 hover:bg-white disabled:opacity-25" disabled={index === steps.length - 1 || busy} onClick={() => moveStep(index, 1)} aria-label={`${step.label} 下移`}><ArrowDown className="h-4 w-4" /></button></div></div>
                <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-white px-3 py-2 text-xs text-slate-600 hover:border-clinical-400"><FolderInput className="h-4 w-4 text-clinical-600" /><span className="min-w-0 flex-1 truncate">{step.overrides.length ? `專用來源：${step.overrides.length} 個檔案` : '選擇此步驟的專用來源（選填）'}</span><input className="sr-only" type="file" multiple accept="image/*,.jfif,.zip" disabled={!step.enabled || busy || workflow.active} onChange={(event) => setSteps((current) => current.map((item) => item.key === step.key ? { ...item, overrides: Array.from(event.target.files || []) } : item))} /></label>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <Card className="mt-6 p-5 sm:p-6">
        <h2 className="section-title">3. 檢查並執行</h2>
        {warnings.length > 0 && <div className="mt-3"><InlineNotice tone="warning" title="處理順序提醒"><ul className="list-disc pl-5">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></InlineNotice></div>}
        {error && <div className="mt-3"><InlineNotice tone="danger">{error}</InlineNotice></div>}
        {job && <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-3"><div><p className="text-sm font-semibold">{job.name || '影像處理工作'} · {jobIdOf(job).slice(0, 8)}</p><p className="mt-1 text-xs text-slate-500">{stream.latest?.message || job.message || '等待背景工作更新'}</p></div><StatusBadge status={currentStatus} /></div><ProgressBar value={progress} label={stream.latest?.payload?.step ? String(stream.latest.payload.step) : '整體進度'} />{currentStatus === 'completed' && <SuccessMessage>處理完成，結果已保存於此工作的輸出目錄。</SuccessMessage>}</div>}
        <div className="mt-5 flex flex-wrap justify-end gap-2">{job && <a className="btn-secondary" href={api.jobDownloadUrl(jobIdOf(job))}><Download className="h-4 w-4" />下載結果 ZIP</a>}<button className="btn-primary" disabled={(!files.length && !workflow.ready) || !activeSteps.length || busy || running} onClick={() => void run()}><Play className="h-4 w-4" />{busy ? '建立工作中…' : '開始處理'}</button></div>
      </Card>
      <HandoffActions job={job} status={currentStatus} datasetId={workflow.datasetId} />
    </div>
  )
}
