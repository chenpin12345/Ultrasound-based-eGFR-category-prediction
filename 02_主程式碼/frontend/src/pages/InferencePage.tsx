import { ModelSelector } from '../components/ModelSelector'
import { useModelChoice } from '../hooks/useModelChoice'
import { WorkflowSource, HandoffActions } from '../components/Workflow'
import { InferenceSourcePicker } from '../components/InferenceSourcePicker'
import { useWorkflowJob } from '../lib/workflow'
import { BarChart3, Download, FileSpreadsheet, Play, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Dropzone } from '../components/Dropzone'
import { FilePreviewGallery } from '../components/PreviewGallery'
import { Card, InlineNotice, PageHeader, ProgressBar, StatePanel, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, apiUrl, humanApiError } from '../lib/api'
import { formatPercent, jobIdOf, normalizeProgress } from '../lib/format'
import type { InferenceProbability, InferenceResult, JobResults } from '../types/api'

function probabilitiesOf(value: InferenceResult['probabilities']): InferenceProbability[] {
  if (Array.isArray(value)) return value
  return Object.entries(value || {}).map(([class_name, probability], class_index) => ({ class_name, probability, class_index }))
}

export function InferencePage() {
  const [searchParams] = useSearchParams()
  const [modelId, setModelId] = useState(searchParams.get('model_id') || '')
  const [scheme, setScheme] = useState(5)
  const chooseScheme = (value:number)=>{setScheme(value);setModelId('')}
  const models=useModelChoice(modelId,setModelId,'classification',undefined,scheme===5?undefined:`c${scheme}_f1_MLPw4`)
  useEffect(()=>{if(models.selected?.class_count)setScheme(models.selected.class_count)},[models.selected?.class_count])
  const [files, setFiles] = useState<File[]>([])
  const [featureCsv, setFeatureCsv] = useState<File>()
  const workflow = useWorkflowJob('inference')
  const { job, setJob } = workflow
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedModel = models.selected
  const needsFeatures = `${selectedModel?.architecture || ''}`.toLowerCase().includes('mlp')
  const stream = useJobEvents(job ? api.jobEventsUrl(jobIdOf(job)) : undefined, Boolean(job) && !['completed','failed','stopped','interrupted','cancelled'].includes(job?.status || ''))
  const status = stream.latest?.status || job?.status
  const running = ['queued', 'running', 'stopping'].includes(status || '')
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [job?.id, scheme])
  const resultsLoader = useCallback((signal?: AbortSignal) => api.getJobResults(job ? jobIdOf(job) : '', page, signal), [job, page])
  const results = useAsyncResource<JobResults>(resultsLoader, Boolean(job) && status === 'completed', `results:${job?.id}:${page}`)


  const run = async () => {
    if ((!files.length && !workflow.ready) || !selectedModel || (needsFeatures && !featureCsv && !workflow.summary?.has_features)) return
    setBusy(true); setError(null)
    try {
      const form = new FormData(); form.append('kind', 'inference'); form.append('name', `AI 推論 ${new Date().toLocaleString('zh-TW')}`); files.forEach((file) => form.append('files', file)); if (featureCsv) form.append('feature_csv', featureCsv); form.append('model_id', modelId); form.append('config', JSON.stringify({ model_id: modelId, architecture: selectedModel?.architecture, include_probabilities: true }))
      const created = await workflow.create(form)
      setJob(created)
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  const resultItems = useMemo(() => results.data?.results || results.data?.items || [], [results.data])
  const statistics = useMemo(() => {
    if (results.data?.statistics) return results.data.statistics
    return resultItems.reduce<Record<string, number>>((counts, item) => { counts[item.predicted_class] = (counts[item.predicted_class] || 0) + 1; return counts }, {})
  }, [resultItems, results.data?.statistics])

  return (
    <div>
      <PageHeader title="AI 推論" description="使用 ResNet18、MobileNetV2、EfficientNetB3 或 MLP-ResNet18 執行單張與批次分類，並下載完整機率報告。" />
      <WorkflowSource {...workflow} />
      <InferenceSourcePicker />
      <Card className="mb-5 p-4"><label><span className="label">分類方案</span><select className="field" value={scheme} onChange={e => chooseScheme(Number(e.target.value))}><option value={2}>二分類：&lt;60／≥60</option><option value={3}>三分類：&lt;30／30–59／≥60</option><option value={5}>五分類：&lt;15／15–29／30–59／60–89／≥90</option></select></label><p className="mt-2 text-xs text-slate-500">每個方案使用各自權重；不合併五分類預測。海報成績尚未驗證重現。</p></Card>
      <div className={workflow.active ? 'grid gap-6' : 'grid gap-6 xl:grid-cols-[1.1fr_.9fr]'}>
        {!workflow.active && <Card className="p-5 sm:p-6"><h2 className="section-title">1. 選擇圖片</h2><div className="mt-4"><Dropzone files={files} onFiles={setFiles} disabled={busy || workflow.active} /></div>{files.length > 0 && <div className="mt-5"><FilePreviewGallery files={files} /></div>}</Card>}
        <Card className="p-5 sm:p-6"><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-clinical-600" /><h2 className="section-title">2. 模型與輸入</h2></div><div className="mt-4"><ModelSelector label="分類模型" task="classification" value={modelId} onChange={setModelId} classCount={scheme} required disabled={busy||running}/>{models.error&&<InlineNotice tone="danger">{models.error}</InlineNotice>}{selectedModel && <div className="mt-3 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-sm"><div><p className="text-xs text-slate-500">架構</p><p className="mt-1 font-semibold">{selectedModel.architecture || '未標示'}</p></div><div><p className="text-xs text-slate-500">分類模式</p><p className="mt-1 font-semibold">{selectedModel.class_count || 5} 分類</p></div></div>}{needsFeatures && !workflow.active && <label className="mt-4 flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4"><FileSpreadsheet className="h-5 w-5 text-clinical-600" /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{featureCsv?.name || '選擇 Feature CSV'}</span><span className="text-xs text-slate-500">MLP-ResNet18 必要輸入</span></span><input className="sr-only" type="file" accept=".csv,text/csv" onChange={(event) => setFeatureCsv(event.target.files?.[0])} /></label>}{needsFeatures && !featureCsv && !workflow.summary?.has_features && <div className="mt-3"><InlineNotice tone="warning">此模型需要與圖片檔名對應的 Feature CSV，加入前無法開始推論。</InlineNotice></div>}</div>
          {error && <div className="mt-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}
          {job && <div className="mt-4 space-y-3 rounded-xl border border-slate-200 p-4"><div className="flex justify-between gap-3"><div><p className="text-sm font-semibold">工作 {jobIdOf(job).slice(0, 8)}</p><p className="text-xs text-slate-500">{status === 'completed' ? '推論完成，結果已保存' : stream.latest?.message || '等待推論結果'}</p></div><StatusBadge status={status} /></div><ProgressBar value={status === 'completed' ? 100 : normalizeProgress(stream.latest?.progress ?? job.progress)} label="批次推論進度" />{status === 'completed' && <SuccessMessage>推論完成，結果與所有分類機率已保存。</SuccessMessage>}</div>}
          <button className="btn-primary mt-5 w-full" disabled={(!files.length && !workflow.ready) || !selectedModel || busy || running || (needsFeatures && !featureCsv && !workflow.summary?.has_features)} onClick={() => void run()}><Play className="h-4 w-4" />{busy ? '建立推論工作中…' : '開始推論'}</button>
        </Card>
      </div>

      {results.data?.evaluation && <Card className="mt-6 p-5"><h2 className="section-title">{results.data.evaluation.class_count} 分類混淆矩陣</h2><p className="mt-2 text-sm text-slate-600">{results.data.evaluation.scope} 已配對 {results.data.evaluation.sample_count} 張；資料集 {results.data.evaluation.dataset_id || '未綁定'}。</p><div className="table-wrap mt-4"><table className="data-table"><caption className="sr-only">列為原始標籤映射，欄為模型預測</caption><thead><tr><th>真實標籤／預測</th>{results.data.evaluation.class_names.map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{results.data.evaluation.confusion_matrix.map((row,index) => <tr key={index}><th scope="row">{results.data!.evaluation!.class_names[index]}</th>{row.map((value,column) => <td key={column} className={index === column ? 'bg-clinical-50 font-bold text-clinical-700' : ''}>{value}</td>)}</tr>)}</tbody></table></div></Card>}

      {job && <Card className="mt-6 p-5 sm:p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex items-center gap-2"><BarChart3 className="h-5 w-5 text-clinical-600" /><h2 className="section-title">推論結果</h2></div><p className="mt-1 text-sm text-slate-500">信心分數僅為模型輸出，不代表醫療診斷可信度。</p></div><div className="flex gap-2"><a className="btn-secondary" href={`${api.jobDownloadUrl(jobIdOf(job))}?format=csv`}><Download className="h-4 w-4" />CSV</a><a className="btn-secondary" href={api.jobDownloadUrl(jobIdOf(job))}><Download className="h-4 w-4" />完整 ZIP</a></div></div>
        <StatePanel loading={results.loading || running} error={results.error} onRetry={() => void results.refresh()} empty={status === 'completed' && !resultItems.length} emptyTitle="沒有可顯示的推論結果" emptyDescription="請查看工作錯誤訊息或後端日誌。">
          {resultItems.length > 0 && <><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">{Object.entries(statistics).map(([name, count]) => <div key={name} className="rounded-xl border border-slate-200 bg-slate-50 p-3"><p className="truncate text-xs font-medium text-slate-500">{name}</p><p className="mt-1 text-xl font-bold text-ink">{count}</p></div>)}</div><div className="mt-5 grid gap-4 lg:grid-cols-2">{resultItems.map((result) => <div key={result.id || result.file_name} className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex gap-3 border-b border-slate-100 p-3">{result.thumbnail_url ? <img loading="lazy" className="h-16 w-16 rounded-lg object-contain" src={apiUrl(result.thumbnail_url)} alt={result.file_name} /> : <div className="grid h-16 w-16 place-items-center rounded-lg bg-slate-100 text-xs text-slate-400">無縮圖</div>}<div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{result.file_name}</p><p className="mt-1 text-sm font-bold text-clinical-700">{result.predicted_class}</p><p className="text-xs text-slate-500">信心分數 {formatPercent(result.confidence, result.confidence <= 1)}</p></div></div><div className="space-y-2 p-3">{probabilitiesOf(result.probabilities).map((probability) => { const value = probability.probability <= 1 ? probability.probability * 100 : probability.probability; return <div key={probability.class_name}><div className="mb-1 flex justify-between gap-2 text-xs"><span className="truncate text-slate-600">{probability.class_name}</span><span className="font-semibold">{value.toFixed(2)}%</span></div><div className="h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-clinical-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div></div>})}</div></div>)}</div></>}
        </StatePanel>
        {results.data && <div className="mt-4 flex items-center gap-3"><button className="btn-secondary" disabled={page === 0} onClick={() => setPage(p => p-1)}>上一頁結果</button><span>{page+1} / {Math.max(1, Math.ceil((results.data.total || 0)/60))} · 共 {results.data.total ?? resultItems.length} 筆</span><button className="btn-secondary" disabled={(page+1)*60 >= (results.data.total || 0)} onClick={() => setPage(p => p+1)}>下一頁結果</button></div>}
      </Card>}
      <HandoffActions job={job} status={status} datasetId={workflow.datasetId} />
    </div>
  )
}
