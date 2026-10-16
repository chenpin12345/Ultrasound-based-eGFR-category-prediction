import { Check, Download, FlaskConical, Pencil, Play, RefreshCw, Trash2, Upload, X } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Card, InlineNotice, PageHeader, StatePanel, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api, apiUrl, humanApiError } from '../lib/api'
import { formatBytes, formatDate } from '../lib/format'
import type { ModelInfo } from '../types/api'
import { ModelEvaluation } from '../components/ModelEvaluation'

export function ModelsPage() {
  const [workspaceParams] = useSearchParams()
  const [filters,setFilters]=useState({search:'',task:'',architecture:'',class_count:'',version:'',source:'',status:'',sort:'newest'})
  const [page,setPage]=useState(0)
  const query=new URLSearchParams(Object.entries(filters).filter(([,value])=>Boolean(value)))
  query.set('limit','50'); query.set('offset',String(page*50))
  const queryKey=query.toString()
  const loadModels=useCallback((signal?:AbortSignal)=>api.modelPage(new URLSearchParams(queryKey),signal),[queryKey])
  const models=useAsyncResource(loadModels,true,`models:${queryKey}`)
  const changeFilter=(key:keyof typeof filters,value:string)=>{setFilters(previous=>({...previous,[key]:value}));setPage(0)}
  const [file, setFile] = useState<File>()
  const [name, setName] = useState('')
  const [architecture, setArchitecture] = useState('resnet18')
  const [classificationMode, setClassificationMode] = useState('multiclass')
  const [classCount, setClassCount] = useState(5)
  const [statsText, setStatsText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ModelInfo>()
  const [renameTargetId, setRenameTargetId] = useState<string>()
  const [renameName, setRenameName] = useState('')

  const importModel = async () => {
    if (!file || !name.trim()) return
    setBusy(true); setError(null); setMessage(null)
    try {
      const segmentation = architecture === 'unet'
      const manifestArchitecture = !segmentation && classificationMode === 'coral' ? `coral-${architecture}` : architecture
      const classNames = segmentation ? ['background', 'foreground'] : classCount === 2 ? ['eGFR < 60', 'eGFR ≥ 60'] : classCount === 3 ? ['eGFR < 30', 'eGFR 30–59', 'eGFR ≥ 60'] : ['eGFR < 15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥ 90']
      if (architecture.includes('mlp') && !statsText.trim()) throw new Error('請提供這份權重專屬的 train_stats JSON，不能任意使用其他模型的統計值。')
      const manifest = {
        name: name.trim(), version: '1', task: segmentation ? 'segmentation' : 'classification', architecture: manifestArchitecture,
        class_count: classNames.length, class_names: classNames,
        train_stats: statsText.trim() ? JSON.parse(statsText) : undefined,
        metadata_columns: architecture.includes('mlp') ? ['age', 'Length_px', 'Contrast_Ratio', 'has_diabetes'] : [],
        preprocessing: segmentation
          ? { color_mode: 'RGB', input_size: [512, 512], normalization: 'imagenet' }
          : { color_mode: 'RGB', input_size: [224, 224], normalization: 'imagenet', classification_mode: classificationMode },
      }
      const form = new FormData(); form.append('weights', file); form.append('manifest_json', JSON.stringify(manifest))
      await api.importModel(form); setFile(undefined); setName(''); setMessage('模型已通過後端相容性檢查並完成匯入。'); await models.refresh()
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }
  const activate = async (model: ModelInfo) => {
    setBusy(true); setError(null)
    try { await api.activateModel(model.id); setMessage(`「${model.name}」已設為預設推論模型。`); await models.refresh() } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!deleteTarget) return
    setBusy(true); setError(null)
    try { await api.deleteModel(deleteTarget.id); setDeleteTarget(undefined); setMessage('模型及其登錄資訊已刪除。'); await models.refresh() } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }
  const rename = async (model: ModelInfo) => {
    const nextName = renameName.trim()
    if (!nextName) return
    if (nextName === model.name) { setRenameTargetId(undefined); return }
    setBusy(true); setError(null); setMessage(null)
    try {
      await api.renameModel(model.id, nextName)
      setRenameTargetId(undefined); setRenameName(''); setMessage(`模型已重新命名為「${nextName}」。`); await models.refresh()
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="模型管理" description="管理外部匯入與訓練產生的模型；每個模型都需保存架構、分類映射、正規化與來源資訊。" actions={<button className="btn-secondary" onClick={() => void models.refresh()}><RefreshCw className="h-4 w-4" />重新整理</button>} />
      <Card className="mb-5 p-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <label><span className="label">搜尋模型名稱</span><input className="field" value={filters.search} onChange={e=>changeFilter('search',e.target.value)}/></label>
        <label><span className="label">任務</span><select className="field" value={filters.task} onChange={e=>changeFilter('task',e.target.value)}><option value="">全部任務</option><option value="classification">分類</option><option value="segmentation">分割</option></select></label>
        <label><span className="label">架構</span><select className="field" value={filters.architecture} onChange={e=>changeFilter('architecture',e.target.value)}><option value="">全部架構</option>{['resnet18','mlp-resnet18','mobilenetv2','efficientnet_b3','coral-resnet18','coral-mlp-resnet18','unet'].map(value=><option key={value}>{value}</option>)}</select></label>
        <label><span className="label">分類數</span><select className="field" value={filters.class_count} onChange={e=>changeFilter('class_count',e.target.value)}><option value="">全部分類數</option>{[2,3,5].map(value=><option key={value}>{value}</option>)}</select></label>
        <label><span className="label">版本（完全符合）</span><input className="field" value={filters.version} onChange={e=>changeFilter('version',e.target.value)}/></label>
        <label><span className="label">登錄來源</span><select className="field" value={filters.source} onChange={e=>changeFilter('source',e.target.value)}><option value="">全部来源</option><option value="training">本機訓練登錄</option><option value="external">外部匯入</option></select></label>
        <label><span className="label">狀態</span><select className="field" value={filters.status} onChange={e=>changeFilter('status',e.target.value)}><option value="">全部狀態</option>{['ready','completed','failed'].map(value=><option key={value}>{value}</option>)}</select></label>
        <label><span className="label">排序</span><select className="field" value={filters.sort} onChange={e=>changeFilter('sort',e.target.value)}><option value="newest">最新建立</option><option value="oldest">最早建立</option><option value="name">名稱</option></select></label>
      </div><div className="mt-4 flex flex-wrap items-center gap-3" aria-label="模型分頁"><button className="btn-secondary" disabled={page===0} onClick={()=>setPage(p=>p-1)}>上一頁</button><span>第 {page+1} 頁 · 共 {models.data?.total??'…'} 個模型 · 每頁 50 筆</span><button className="btn-secondary" disabled={!models.data||(page+1)*50>=models.data.total} onClick={()=>setPage(p=>p+1)}>下一頁</button></div>{models.updating&&<p role="status" className="mt-2 text-sm">背景更新中…</p>}{models.updateError&&<InlineNotice tone="danger">更新失敗：{models.updateError}</InlineNotice>}</Card>
      <div className="grid gap-6 xl:grid-cols-[22rem_1fr]">
        <Card className="h-fit p-5"><div className="flex items-center gap-2"><Upload className="h-5 w-5 text-clinical-600" /><h2 className="section-title">匯入外部模型</h2></div><p className="mt-1 text-sm leading-6 text-slate-500">僅接受 `.pth`；後端必須以 weights-only 規則驗證，不信任任意 pickle。</p>
          <label className="mt-4 block"><span className="label">模型名稱</span><input className="field" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：ResNet18 v1" disabled={busy} /></label>
          <label className="mt-4 block"><span className="label">架構</span><select className="field" value={architecture} onChange={(event) => { const next = event.target.value; setArchitecture(next); setClassificationMode(next === 'unet' ? 'segmentation' : classificationMode === 'segmentation' || (classificationMode === 'coral' && !['resnet18', 'mlp-resnet18'].includes(next)) ? 'multiclass' : classificationMode) }} disabled={busy}><option value="resnet18">ResNet18</option><option value="mobilenetv2">MobileNetV2</option><option value="efficientnet_b3">EfficientNetB3</option><option value="mlp-resnet18">MLP-ResNet18</option><option value="unet">UNet</option></select></label>
          <label className="mt-4 block"><span className="label">分類模式</span><select className="field" value={classificationMode} onChange={(event) => setClassificationMode(event.target.value)} disabled={busy || architecture === 'unet'}><option value="multiclass">一般多類別</option><option value="coral" disabled={!['resnet18', 'mlp-resnet18'].includes(architecture)}>CORAL／序位分類</option><option value="segmentation" disabled>Segmentation</option></select></label>
          {architecture !== 'unet' && <label className="mt-4 block"><span className="label">分類方案</span><select className="field" value={classCount} onChange={e => setClassCount(Number(e.target.value))}>{[2,3,5].map(n => <option key={n} value={n}>{n} 分類</option>)}</select></label>}
          {architecture.includes('mlp') && <label className="mt-4 block"><span className="label">此權重的 train_stats JSON</span><textarea className="field min-h-32 font-mono text-xs" value={statsText} onChange={e => setStatsText(e.target.value)} placeholder='{"age":{"mean":0,"std":1},"Length_px":{"mean":0,"std":1},"Contrast_Ratio":{"mean":0,"std":1}}' /><span className="help">請貼上原始紀錄中該模型的 train_stats 物件；範例不是可用的實驗數值。</span></label>}
          <label className="mt-4 flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 p-5 text-center hover:border-clinical-400"><FlaskConical className="h-7 w-7 text-clinical-600" /><span className="mt-2 max-w-full truncate text-sm font-semibold">{file?.name || '選擇 .pth 權重'}</span><span className="mt-1 text-xs text-slate-500">{file ? formatBytes(file.size) : '檔案不會上傳到外部服務'}</span><input className="sr-only" type="file" accept=".pth,.pt" disabled={busy} onChange={(event) => { const next = event.target.files?.[0]; setFile(next); if (next && !name) setName(next.name.replace(/\.(pth|pt)$/i, '')) }} /></label>
          <button className="btn-primary mt-4 w-full" disabled={!file || !name.trim() || busy} onClick={() => void importModel()}><Upload className="h-4 w-4" />{busy ? '處理中…' : '匯入模型'}</button>
        </Card>
        <div className="min-w-0 space-y-4">{message && <SuccessMessage>{message}</SuccessMessage>}{error && <InlineNotice tone="danger">{error}</InlineNotice>}<StatePanel loading={models.loading} error={models.error} onRetry={() => void models.refresh()} empty={!models.data?.items.length} emptyTitle="尚未安裝模型" emptyDescription="服務仍可啟動；匯入外部模型或完成訓練後即可進行遮罩與推論。"><div className="grid gap-4 lg:grid-cols-2">{models.data?.items.map((model) => <Card key={model.id} className="p-5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="truncate font-bold text-ink">{model.name}</h2>{(model.is_active || model.is_default) && <span className="rounded-full bg-clinical-50 px-2.5 py-1 text-xs font-semibold text-clinical-700">預設模型</span>}</div><p className="mt-1 text-sm text-slate-500">{model.architecture || '架構未標示'} · {model.task === 'segmentation' ? '分割' : `${model.class_count || 5} 分類`} · {model.source === 'training' ? '本機訓練' : '外部匯入'}</p></div><StatusBadge status={model.status || 'ready'} /></div>{renameTargetId === model.id && <form className="mt-4 flex gap-2 rounded-xl border border-clinical-200 bg-clinical-50 p-3" onSubmit={(event) => { event.preventDefault(); void rename(model) }}><label className="min-w-0 flex-1"><span className="sr-only">新的模型名稱</span><input className="field" value={renameName} maxLength={200} autoFocus disabled={busy} onChange={(event) => setRenameName(event.target.value)} /></label><button className="btn-primary" type="submit" disabled={busy || !renameName.trim()} aria-label="儲存模型名稱"><Check className="h-4 w-4" /></button><button className="btn-ghost" type="button" disabled={busy} onClick={() => setRenameTargetId(undefined)} aria-label="取消重新命名"><X className="h-4 w-4" /></button></form>}<div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">建立時間</p><p className="mt-1 font-medium">{formatDate(model.created_at)}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">檔案大小</p><p className="mt-1 font-medium">{formatBytes(model.size_bytes)}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">版本</p><p className="mt-1 font-medium">{model.version || '—'}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">評估來源</p><Link className="mt-1 inline-block font-medium text-clinical-700 underline" to={`/model-center/models/${model.id}`}>查看設定與追溯</Link></div></div><div className="mt-4 rounded-xl bg-slate-50 p-3"><ModelEvaluation summary={model.evaluation_summary}/></div><div className="mt-4 flex flex-wrap gap-2">{!model.is_active && !model.is_default && <button className="btn-secondary flex-1" disabled={busy || model.status === 'failed'} onClick={() => void activate(model)}><Check className="h-4 w-4" />設為預設</button>}<Link className="btn-secondary flex-1" to={`/research/${model.task === 'segmentation' ? 'masks' : 'inference'}?model_id=${encodeURIComponent(model.id)}&dataset_id=${encodeURIComponent(workspaceParams.get('dataset_id') || '')}`}><Play className="h-4 w-4" />{model.task === 'segmentation' ? '產生遮罩' : '測試推論'}</Link><button className="btn-ghost" disabled={busy} onClick={() => { setRenameTargetId(model.id); setRenameName(model.name) }} aria-label={`重新命名 ${model.name}`}><Pencil className="h-4 w-4" /></button>{model.download_url && <a className="btn-ghost" href={apiUrl(model.download_url)} aria-label={`下載 ${model.name}`}><Download className="h-4 w-4" /></a>}<button className="btn-ghost text-rose-600 hover:bg-rose-50 hover:text-rose-700" onClick={() => setDeleteTarget(model)} aria-label={`刪除 ${model.name}`}><Trash2 className="h-4 w-4" /></button></div></Card>)}</div></StatePanel></div>
      </div>
      <ConfirmDialog open={Boolean(deleteTarget)} title="刪除模型？" description={`將刪除「${deleteTarget?.name || ''}」的權重與 metadata。使用中的工作不會被強制終止；若模型正被使用，後端應拒絕此操作。`} busy={busy} onCancel={() => setDeleteTarget(undefined)} onConfirm={() => void remove()} />
    </div>
  )
}
