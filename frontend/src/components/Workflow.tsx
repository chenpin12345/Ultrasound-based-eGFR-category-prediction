import { ArrowRight, CheckCircle2, Database, Upload, Workflow as WorkflowIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api, humanApiError, listItems } from '../lib/api'
import { workflowApi, workflowLink, workflowSteps, type SourceSummary } from '../lib/workflow'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { Card, InlineNotice, StatePanel } from './ui'
import type { Dataset, Job } from '../types/api'

export function WorkflowBar() {
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const loader = useCallback(async (signal?: AbortSignal) => listItems<Dataset>(await api.listDatasets(signal)), [])
  const datasets = useAsyncResource(loader, true, 'datasets')
  const refreshDatasets = datasets.refresh
  useEffect(() => { void refreshDatasets() }, [location.search, refreshDatasets])
  const datasetId = params.get('dataset_id') || ''
  const selected = datasets.data?.find(item => item.id === datasetId)
  const [remembered] = useState(() => { try { return localStorage.getItem('isu-workspace-dataset') || '' } catch { return '' } })
  useEffect(() => { if (datasetId && selected) { try { localStorage.setItem('isu-workspace-dataset', datasetId) } catch { /* Storage may be unavailable. */ } } }, [datasetId, selected])
  const select = (id: string) => setParams(current => {
    const next = new URLSearchParams(current)
    for (const key of ['source_job', 'job_id', 'input']) next.delete(key)
    if (id) next.set('dataset_id', id); else next.delete('dataset_id')
    return next
  })
  return <Card className="mb-6 overflow-hidden">
    <div className="flex flex-col gap-4 p-4 sm:p-5 xl:flex-row xl:items-center xl:justify-between">
      <div className="flex items-center gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-clinical-50 text-clinical-700"><WorkflowIcon className="h-5 w-5" /></span><div><p className="text-sm font-bold text-ink">研究流程工作區</p><p className="mt-1 text-xs text-slate-500">選擇資料 → 確認設定 → 執行 → 沿用結果</p></div></div>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <label className="min-w-0 sm:w-64"><span className="sr-only">目前資料集</span><select aria-label="目前資料集" className="field" value={datasetId} onChange={event => select(event.target.value)}>
          <option value="">選擇資料集</option>{datasetId && !selected && <option value={datasetId}>資料集不存在或載入中</option>}
          {datasets.data?.map(item => <option key={item.id} value={item.id}>{item.name} · {item.image_count ?? item.sample_count ?? 0} 張</option>)}
        </select></label>
        {['/processing', '/masks', '/features', '/inference'].includes(location.pathname) && <button className="btn-secondary" onClick={() => setParams(current => { const next = new URLSearchParams(current); next.delete('source_job'); next.delete('job_id'); if (next.get('input') === 'upload') next.delete('input'); else next.set('input', 'upload'); return next })}><Upload className="h-4 w-4" />{params.get('input') === 'upload' ? '使用資料集' : '獨立上傳'}</button>}
      </div>
    </div>
    {datasets.error && <div className="px-5 pb-3"><InlineNotice tone="danger">{datasets.error}<button className="btn-ghost ml-2" onClick={() => void datasets.refresh()}>重試</button></InlineNotice></div>}
    {datasetId && !datasets.loading && datasets.data && !selected && <div className="px-5 pb-3"><InlineNotice tone="warning">原資料集已不存在，請重新選擇資料集。</InlineNotice></div>}
    {!datasetId && remembered && datasets.data?.some(item => item.id === remembered) && <div className="px-5 pb-3"><button className="btn-ghost" onClick={() => select(remembered)}><Database className="h-4 w-4" />恢復上次資料集</button></div>}
    <nav className="grid grid-cols-2 border-t border-slate-200 bg-slate-50/70 sm:grid-cols-3 xl:grid-cols-6" aria-label="研究流程步驟">{workflowSteps.map(([path, title], index) => <Link key={path} to={workflowLink(path, datasetId)} aria-current={location.pathname === path ? 'step' : undefined} className={`flex min-h-12 items-center gap-2 px-4 py-3 text-xs font-semibold transition hover:bg-clinical-50 ${location.pathname === path ? 'bg-clinical-50 text-clinical-800 ring-1 ring-inset ring-clinical-200' : 'text-slate-500'}`}><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-current/20 bg-white">{index + 1}</span>{title}</Link>)}</nav>
  </Card>
}

export function WorkflowSource({ active, loading, sourceError, summary }: { active: boolean; loading: boolean; sourceError: string; summary?: SourceSummary }) {
  if (!active && !sourceError) return null
  return <Card className="mb-6 border-clinical-200 p-5"><StatePanel loading={loading} error={sourceError}>
    {summary && <><div className="flex items-center gap-2 text-sm font-bold text-clinical-800"><CheckCircle2 className="h-5 w-5" />已選擇沿用來源：{summary.name}</div><div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600"><span>影像 {summary.image_count} 張</span><span>遮罩 {summary.mask_count} 張</span><span>Metadata {summary.metadata_count} 筆</span><span>特徵 CSV {summary.has_features ? '已備妥' : '尚未產生'}</span></div><p className="mt-3 text-xs text-slate-500">確認本頁設定後點擊執行。若要使用其他上傳檔案，請切換至上方「獨立上傳」。</p></>}
  </StatePanel></Card>
}

export function HandoffActions({ job, status, datasetId }: { job?: Job; status?: string; datasetId?: string }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  if (!job || status !== 'completed') return null
  const next = job.kind === 'process' ? ['/masks', '遮罩準備'] : job.kind === 'masks' ? ['/features', '特徵擷取'] : job.kind === 'features' ? ['/inference', 'AI 推論'] : null
  if (!next) return null
  const derive = async () => {
    setBusy(true); setError('')
    try { const result = await workflowApi.derive({ kind: 'job', id: job.id }, name.trim()); navigate(workflowLink('/training', result.id)) }
    catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }
  return <Card className="mt-6 border-clinical-200 bg-clinical-50/40 p-5"><h2 className="section-title">此步驟已完成</h2><p className="mt-2 text-sm text-slate-600">沿用這次的影像與產物，下一頁確認後才會啟動工作。</p><div className="mt-4 flex flex-wrap items-center gap-3"><Link className="btn-primary" to={workflowLink(next[0], datasetId, job.id)}>使用此結果進入{next[1]}<ArrowRight className="h-4 w-4" /></Link><Link className="btn-secondary" to="/jobs">查看歷史工作</Link></div>
    {job.kind === 'features' && <div className="mt-5 border-t border-clinical-200 pt-4"><label className="label" htmlFor="derived-name">建立獨立訓練資料集</label><p className="mb-3 text-xs text-slate-500">保留原標籤與分割，使用此次影像及特徵，不覆寫原資料集。</p><div className="flex flex-col gap-3 sm:flex-row"><input id="derived-name" className="field sm:max-w-sm" placeholder="新資料集名稱" value={name} onChange={event => setName(event.target.value)} /><button className="btn-secondary" disabled={busy || !name.trim()} onClick={() => void derive()}>{busy ? '建立中…' : '建立並前往模型訓練'}</button></div></div>}
    {error && <div className="mt-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}
  </Card>
}
