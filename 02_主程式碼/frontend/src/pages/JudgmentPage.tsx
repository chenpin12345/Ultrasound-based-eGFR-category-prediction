import { ModelSelector } from '../components/ModelSelector'
import { useModelChoice } from '../hooks/useModelChoice'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BrainCircuit, Download, Play } from 'lucide-react'
import { Dropzone } from '../components/Dropzone'
import { FilePreviewGallery, PreviewGallery, type PreviewItem } from '../components/PreviewGallery'
import { Card, InlineNotice, PageHeader, ProgressBar, StatePanel, StatusBadge } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { useJobEvents } from '../hooks/useJobEvents'
import { api, apiUrl, humanApiError, listItems, requestJson } from '../lib/api'
import { useWorkflowJob } from '../lib/workflow'
import { normalizeProgress } from '../lib/format'
import type { Dataset } from '../types/api'

import { validBasic, type Basic } from '../lib/judgment'
type SourceItem = { id: string; name: string; age?: string | number; has_diabetes?: string | number }
const keyOf = (file: File) => `${file.name}-${file.size}-${file.lastModified}`

export function JudgmentPage() {
  const [params, setParams] = useSearchParams()
  const [sourceMode, setSourceMode] = useState(params.get('use_source') === '1')
  const [datasetId, setDatasetId] = useState(params.get('dataset_id') || '')
  const [sourceJob, setSourceJob] = useState(params.get('source_job') || '')
  const [mode, setMode] = useState<'mlp' | 'image_only'>('mlp')
  const [scheme, setScheme] = useState(5)
  const [modelId, setModelId] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [basic, setBasic] = useState<Record<string, Basic>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const guard = useRef(false)
  const [page, setPage] = useState(0)
  const [inputPage, setInputPage] = useState(0)
  const [view, setView] = useState('original')
  const loadDatasets = useCallback(async (signal?: AbortSignal) => listItems<Dataset>(await api.listDatasets(signal)), [])
  const datasets = useAsyncResource(loadDatasets, true, 'datasets')
  const loadSource = useCallback((signal?: AbortSignal) => requestJson<{name: string; items: SourceItem[]}>(`/workflow/judgment-source?kind=${sourceJob ? 'job' : 'dataset'}&id=${encodeURIComponent(sourceJob || datasetId)}`, {signal}), [sourceJob, datasetId])
  const source = useAsyncResource(loadSource, sourceMode && Boolean(sourceJob || datasetId), `judgment-source:${sourceJob ? 'job' : 'dataset'}:${sourceJob || datasetId}`)
  const models=useModelChoice(modelId,setModelId,'classification',scheme,`c${scheme}_f1_${mode==='mlp'?'MLPw4':'OnlyIMG'}`,mode)
  const [segmenterId,setSegmenterId]=useState('')
  const segmentation=useModelChoice(segmenterId,setSegmenterId,'segmentation',undefined,'unet_model')
  useEffect(() => {
    if (sourceMode && source.data) setBasic(current => Object.fromEntries(source.data!.items.map(item => [item.id, current[item.id] || {age: String(item.age ?? ''), has_diabetes: item.has_diabetes == null || String(item.has_diabetes).trim() === '' ? '' : String(Number(item.has_diabetes))}])))
  }, [source.data, sourceMode])
  const segmenter = segmentation.selected
  const selected = models.selected
  const {job, setJob} = useWorkflowJob('quick_analysis')
  const events = useJobEvents(job ? api.jobEventsUrl(job.id) : undefined, Boolean(job) && !['completed','failed','stopped','interrupted','cancelled'].includes(job?.status || ''))
  const status = events.latest?.status || job?.status
  const running = ['queued', 'running', 'stopping'].includes(status || '')
  const finished = ['completed', 'failed', 'stopped', 'interrupted', 'cancelled'].includes(status || '')
  useEffect(() => setPage(0), [job?.id, scheme])
  const loadResults = useCallback((signal?: AbortSignal) => api.getJobResults(job?.id || '', page, signal), [job?.id, page])
  const results = useAsyncResource(loadResults, Boolean(job) && finished, `results:${job?.id}:${page}`)
  const inputs = sourceMode ? (datasetId || sourceJob ? source.data?.items || [] : []).map(item => ({id: item.id, name: item.name})) : files.map(file => ({id: keyOf(file), name: file.name}))
  const missing = mode === 'mlp' ? inputs.filter(item => !validBasic(basic[item.id])) : []
  useEffect(() => { setInputPage(p => Math.min(p, Math.max(0, Math.ceil(inputs.length / 60) - 1))) }, [inputs.length])
  const reason = !selected ? '請選擇有效的分類模型；不會自動替換缺少的預設權重。' : mode === 'mlp' && !segmenter ? '尚未安裝 unet_model 分割模型。' : sourceMode && (source.loading || source.error) ? (source.error || '正在確認來源…') : !inputs.length ? '請先上傳圖片或選擇既有資料。' : missing.length ? `有 ${missing.length} 張圖片尚未填妥年齡與糖尿病狀態。` : ''
  const update = (id: string, key: keyof Basic, value: string) => setBasic(current => ({...current, [id]: {...(current[id] || {age: '', has_diabetes: ''}), [key]: value}}))
  const chooseSource = (value: boolean) => { setSourceMode(value); setFiles([]); setBasic({}); setInputPage(0); setParams(current => {const next = new URLSearchParams(current); if (value) next.set('use_source', '1'); else next.delete('use_source'); next.delete('job_id'); return next}, {replace: true}) }
  const run = async () => {
    if (reason || guard.current || running) return
    guard.current = true; setBusy(true); setError(''); setPage(0)
    try {
      const config = {analysis_mode: mode, classifier_model_id: modelId, ...(mode === 'mlp' ? {unet_model_id: segmenter?.id, basic_metadata: sourceMode ? Object.fromEntries(inputs.map(i => [i.id, basic[i.id]])) : inputs.map(i => basic[i.id])} : {})}
      const name = `AI判斷 · ${scheme} 分類 · ${mode === 'mlp' ? 'MLP' : 'OnlyIMG'}`
      if (sourceMode) {
        setJob(await api.createJob({kind: 'quick_analysis', name, config, input_sources: {images: {kind: sourceJob ? 'job' : 'dataset', id: sourceJob || datasetId}}}))
      } else {
        const form = new FormData(); form.append('kind', 'quick_analysis'); form.append('name', name); form.append('config', JSON.stringify(config)); files.forEach(file => form.append('files', file)); setJob(await api.createJob(form))
      }
    } catch (e) { setError(humanApiError(e)) } finally { setBusy(false); guard.current = false }
  }
  const items = results.data?.items || []
  const total = results.data?.total ?? items.length
  const visible = items
  const previews: PreviewItem[] = visible.map((item, index) => ({id: `${page}-${index}`, name: item.file_name,
    url: apiUrl((view === 'original' ? item.thumbnail_url : view === 'overlay' ? item.overlay_url : item.processed_url) || ''),
    maskUrl: ['mask', 'overlay'].includes(view) && item.mask_url ? apiUrl(item.mask_url) : undefined,
    maskOnly: view === 'mask', badge: view === 'original' ? '原圖' : view === 'processed' ? '處理圖' : view === 'mask' ? '純 Mask' : '特徵疊圖',
    unavailable: (view === 'original' && !item.thumbnail_url) || (view === 'processed' && !item.processed_url) ? '此歷史工作沒有對應預覽' : ['mask', 'overlay'].includes(view) && !item.mask_url ? '此模式未產生 Mask' : view === 'overlay' && !item.overlay_url ? '缺少同尺寸配對，無法安全疊圖' : undefined,
    featureValues: view === 'overlay' ? Object.fromEntries(['Length_px', 'Entropy', 'Contrast_Ratio'].map(k => [k, item.metadata?.[k] == null ? null : Number(item.metadata[k])])) : undefined,
  }))
  return <div className="space-y-6">
    <PageHeader title="AI判斷" description="上傳圖片，由系統準備所需資料並完成分類。原有第六步「AI 推論」仍獨立保留。" />
    <fieldset disabled={busy || running} className="space-y-5 disabled:opacity-70">
      <Card className="p-5"><h2 className="section-title">分析模式</h2><div className="mt-4 grid gap-3 md:grid-cols-2">{(['mlp', 'image_only'] as const).map(value => <button type="button" key={value} aria-pressed={mode === value} className={`rounded-xl border p-4 text-left ${mode === value ? 'border-clinical-500 bg-clinical-50' : 'border-slate-200'}`} onClick={() => {if(mode!==value){setMode(value);setModelId('')}}}><p className="font-semibold">{value === 'mlp' ? '圖片＋基本資料 MLP（預設）' : '僅圖片 OnlyIMG'}</p><p className="mt-1 text-sm text-slate-600">{value === 'mlp' ? '需要年齡、糖尿病狀態；自動完成分割與特徵計算。' : '只需圖片，不執行分割；使用獨立的 OnlyIMG 模型。'}</p></button>)}</div>
      <div className="mt-4 grid gap-4 md:grid-cols-2"><label><span className="label">分類方案</span><select className="field" value={scheme} onChange={e => {setScheme(Number(e.target.value));setModelId('')}}><option value={2}>二分類：&lt;60／≥60</option><option value={3}>三分類：&lt;30／30–59／≥60</option><option value={5}>五分類：&lt;15／15–29／30–59／60–89／≥90</option></select></label><ModelSelector label="分類模型" task="classification" value={modelId} onChange={setModelId} classCount={scheme} analysisMode={mode} required disabled={busy||running}/></div>{models.error && <InlineNotice tone="danger">{models.error}</InlineNotice>}</Card>
      <Card className="p-5"><div className="mb-4 flex flex-wrap gap-3"><button className="btn-secondary" aria-pressed={!sourceMode} onClick={() => chooseSource(false)}>上傳新圖片</button><button className="btn-secondary" aria-pressed={sourceMode} onClick={() => chooseSource(true)}>使用既有資料</button></div>
        {sourceMode ? <><label><span className="label">資料集</span><select className="field" value={datasetId} onChange={e => {setDatasetId(e.target.value); setSourceJob(''); setBasic({}); setInputPage(0); setParams(current => { const next = new URLSearchParams(current); next.set('dataset_id', e.target.value); next.set('use_source', '1'); next.delete('source_job'); next.delete('job_id'); return next }, {replace: true})}}><option value="">選擇資料集</option>{datasets.data?.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label><StatePanel loading={source.loading} error={source.error} onRetry={() => void source.refresh()}>{source.data && <p className="mt-3 text-sm">來源：{source.data.name} · {inputs.length} 張{sourceJob ? '（使用指定工作產物，避免重複處理）' : '（原始資料集）'}</p>}</StatePanel></> : <><Dropzone files={files} onFiles={next => {if (next.some(f => !/\.(jpe?g|png|jfif)$/i.test(f.name))) {setError('僅接受 JPEG、PNG、JFIF 圖片。'); return} setFiles(next); setInputPage(0); setError('')}} accept=".jpg,.jpeg,.png,.jfif" title="拖放圖片或點擊選擇" description="支援單張或多張 JPEG、PNG、JFIF；資料只在本機處理。" /><div className="mt-4"><FilePreviewGallery files={files.slice(inputPage * 60, (inputPage + 1) * 60)} /></div></>}
        {mode === 'mlp' && inputs.length > 0 && <div className="mt-5"><h3 className="font-semibold">每張圖片的基本資料</h3><p className="my-2 text-sm text-slate-600">不會自動猜測或補值。多張圖片不預設屬於同一位受試者。</p><button className="btn-secondary mb-3" disabled={!validBasic(basic[inputs[0]?.id])} onClick={() => setBasic(Object.fromEntries(inputs.map(i => [i.id, {...basic[inputs[0].id]}])))}>將第一張的基本資料套用全部圖片</button><div className="space-y-3">{inputs.slice(inputPage * 60, (inputPage + 1) * 60).map(item => <div key={item.id} className="grid items-end gap-3 rounded-xl border border-slate-200 p-3 md:grid-cols-[1fr_10rem_12rem_auto]"><p className="break-all text-sm">{item.name}</p><label><span className="label">年齡</span><input aria-label={`${item.name} 年齡`} className="field" type="number" min="0" step="any" value={basic[item.id]?.age || ''} onChange={e => update(item.id, 'age', e.target.value)} /></label><label><span className="label">糖尿病狀態</span><select aria-label={`${item.name} 糖尿病狀態`} className="field" value={basic[item.id]?.has_diabetes ?? ''} onChange={e => update(item.id, 'has_diabetes', e.target.value)}><option value="">請選擇</option><option value="0">否</option><option value="1">是</option></select></label>{!sourceMode && <button className="btn-secondary" aria-label={`移除圖片 ${item.name}`} onClick={() => setFiles(current => current.filter(f => keyOf(f) !== item.id))}>移除</button>}{!validBasic(basic[item.id]) && <p className="text-xs text-amber-800 md:col-span-4">請填妥有效年齡並選擇糖尿病狀態。</p>}</div>)}</div></div>}
        {mode === 'image_only' && !sourceMode && files.length > 0 && <div className="mt-3 space-y-2">{files.slice(inputPage * 60, (inputPage + 1) * 60).map(file => <div key={keyOf(file)} className="flex items-center justify-between gap-3 text-sm"><span className="min-w-0 break-all">{file.name}</span><button className="btn-secondary shrink-0" aria-label={`移除圖片 ${file.name}`} onClick={() => setFiles(current => current.filter(f => f !== file))}>移除</button></div>)}</div>}
        {inputs.length > 60 && <div className="mt-3 flex items-center gap-3"><button className="btn-secondary" disabled={inputPage === 0} onClick={() => setInputPage(p => p-1)}>上一頁圖片</button><span>{inputPage+1} / {Math.ceil(inputs.length/60)}</span><button className="btn-secondary" disabled={(inputPage+1)*60 >= inputs.length} onClick={() => setInputPage(p => p+1)}>下一頁圖片</button></div>}
      </Card>
      <Card className="p-5"><h2 className="section-title">確認本次分析</h2><p className="my-3 text-sm">{sourceMode ? '既有資料' : '新上傳圖片'} · {inputs.length} 張 · {mode === 'mlp' ? 'MLP' : 'OnlyIMG'} · {scheme} 分類 · {selected?.name || '尚未選擇模型'}</p>{reason && <InlineNotice tone="warning">{reason}</InlineNotice>}{error && <InlineNotice tone="danger">{error}</InlineNotice>}<button className="btn-primary mt-4 w-full" disabled={Boolean(reason) || busy || running} onClick={() => void run()}><Play className="h-4 w-4" />{busy ? '建立工作中…' : '開始 AI判斷'}</button></Card>
    </fieldset>
    {job && <Card className="p-5"><div className="flex items-center justify-between"><h2 className="section-title"><BrainCircuit className="mr-2 inline h-5 w-5" />判斷工作與結果</h2><StatusBadge status={status} /></div><p className="my-3 text-sm">{job.name} · {status === 'completed' ? '分析完成，結果已保存' : events.latest?.message || job.error_message || '等待背景工作'}</p><ProgressBar value={status === 'completed' ? 100 : normalizeProgress(events.latest?.progress ?? job.progress)} label="AI判斷進度" />{['failed','interrupted','stopped'].includes(status || '') && <InlineNotice tone="danger">工作未完成：{events.latest?.message || job.error_message || status}。已完成產物保留，可重新建立工作。</InlineNotice>}
      <StatePanel loading={running || results.loading} error={results.error} onRetry={() => void results.refresh()}>
        {items.length > 0 && <><div className="my-4 flex flex-wrap items-center gap-3"><p className="text-sm">實際結果：{results.data?.analysis_mode === 'image_only' ? '僅圖片 OnlyIMG' : 'MLP'} · {results.data?.class_count} 分類 · {total} 張</p><a className="btn-secondary" href={`${api.jobDownloadUrl(job.id)}?format=csv`}><Download className="h-4 w-4" />CSV</a><a className="btn-secondary" href={api.jobDownloadUrl(job.id)}>完整 ZIP</a></div><p className="mb-2 break-all text-xs text-slate-600">實際模型：{results.data?.model?.name || String((job.config?.selected_model as { id?: string } | undefined)?.id || '歷史工作')} · 權重 SHA256：{results.data?.model?.sha256 || '請查閱工作記錄'}</p><p className="mb-4 text-sm text-slate-600">機率為模型輸出，不是準確率或醫療診斷。海報成績尚未驗證重現。</p><label><span className="label">展示方式</span><select className="field mb-4" value={view} onChange={e => setView(e.target.value)}><option value="original">原圖</option><option value="processed">此次處理圖</option><option value="mask">純 Mask</option><option value="overlay">特徵疊圖</option></select></label><PreviewGallery items={previews} /><div className="mt-4 grid gap-3 md:grid-cols-2">{visible.map((item, i) => <article key={i} className="rounded-xl border border-slate-200 p-4"><p className="break-all font-semibold">{item.file_name}</p><p className="my-2 font-bold text-clinical-700">{item.predicted_class}</p>{Array.isArray(item.probabilities) && item.probabilities.map(p => <div className="flex justify-between text-sm" key={p.class_name}><span>{p.class_name}</span><span>{(p.probability*100).toFixed(2)}%</span></div>)}{results.data?.analysis_mode === 'mlp' && <p className="mt-2 text-xs text-slate-600">年齡 {item.metadata?.age} · 糖尿病 {String(item.metadata?.has_diabetes) === '1' ? '是' : '否'}</p>}</article>)}</div><div className="mt-4 flex items-center gap-3"><button className="btn-secondary" disabled={page === 0} onClick={() => setPage(p => p-1)}>上一頁結果</button><span>{page+1} / {Math.ceil(total/60)}</span><button className="btn-secondary" disabled={(page+1)*60 >= total} onClick={() => setPage(p => p+1)}>下一頁結果</button></div></>}
      </StatePanel>
    </Card>}
  </div>
}
