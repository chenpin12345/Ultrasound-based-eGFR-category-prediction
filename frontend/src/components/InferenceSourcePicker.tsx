import { useCallback, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { requestJson } from '../lib/api'
import { Card, StatePanel } from './ui'

export function InferenceSourcePicker() {
  const [params, setParams] = useSearchParams()
  const dataset = params.get('dataset_id') || ''
  const selected = params.get('source_job') || ''
  const active = Boolean(dataset) && params.get('input') !== 'upload'
  const load = useCallback((signal?: AbortSignal) => requestJson<{versions: {id: string; name: string; completed_at: string; image_count: number}[]}>(`/workflow/inference-sources?dataset_id=${encodeURIComponent(dataset)}`, {signal}), [dataset])
  const resource = useAsyncResource(load, active, `inference-sources:${dataset}`)
  useEffect(() => {
    if (active && !selected && !params.get('job_id') && resource.data?.versions.length) {
      setParams(current => { const next = new URLSearchParams(current); next.set('source_job', resource.data!.versions[0].id); return next }, {replace: true})
    }
  }, [active, selected, params, setParams, resource.data])
  if (!active) return null
  return <Card className="mb-5 p-4"><h2 className="section-title">可用特徵版本</h2><StatePanel loading={resource.loading} error={resource.error} onRetry={() => void resource.refresh()}>
    {!!resource.data?.versions.length && <label className="mt-3 block"><span className="label">同一資料集的完整特徵工作</span><select className="field" value={selected} onChange={e => setParams(current => { const next = new URLSearchParams(current); next.set('source_job', e.target.value); next.delete('job_id'); return next })}>
      {!resource.data.versions.some(v => v.id === selected) && <option value={selected}>{selected ? '保留指定來源（未自動替換）' : '選擇特徵版本'}</option>}
      {resource.data.versions.map(v => <option key={v.id} value={v.id}>{v.name} · {v.image_count} 張 · {new Date(v.completed_at).toLocaleString('zh-TW')}</option>)}
    </select></label>}
    {!resource.loading && !resource.data?.versions.length && <p className="mt-2 text-sm text-slate-600">沒有完整相容的特徵工作。MLP 需要先準備特徵；僅圖片模型不需要。</p>}
    <div className="mt-3 flex flex-wrap gap-3"><Link className="btn-secondary" to={`/features?dataset_id=${encodeURIComponent(dataset)}${selected ? `&source_job=${encodeURIComponent(selected)}` : ''}`}>前往特徵擷取</Link><Link className="btn-secondary" to={`/ai-judgment?dataset_id=${encodeURIComponent(dataset)}&use_source=1${selected ? `&source_job=${encodeURIComponent(selected)}` : ''}`}>前往 AI判斷自動準備</Link></div>
  </StatePanel></Card>
}
