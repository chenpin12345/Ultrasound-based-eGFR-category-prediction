import { useCallback, useMemo, useState } from 'react'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { apiUrl, requestJson } from '../lib/api'
import type { DatasetSample } from '../types/api'
import { PreviewGallery, type PreviewItem } from './PreviewGallery'
import { InlineNotice } from './ui'

interface Assets { processed_url: string | null; mask_url: string | null; overlay_source_url?: string; feature_values: Record<string, number | null> }
interface Results { job_id: string | null; versions: {id: string; name: string}[]; items: Record<string, Assets>; warning?: string }

export function DatasetGallery({ datasetId, samples }: { datasetId: string; samples: DatasetSample[] }) {
  const [mode, setMode] = useState('original')
  const [version, setVersion] = useState('')
  const ids = samples.map(s => s.id).join(',')
  const loader = useCallback((signal?: AbortSignal) => requestJson<Results>(`/datasets/${encodeURIComponent(datasetId)}/gallery-results?sample_ids=${encodeURIComponent(ids)}${version ? `&job_id=${encodeURIComponent(version)}` : ''}`, {signal}), [datasetId, ids, version])
  const results = useAsyncResource(loader, Boolean(ids), `gallery:${datasetId}:${version}:${ids}`)
  const items = useMemo<PreviewItem[]>(() => samples.map(sample => {
    const asset = results.data?.items[sample.id]
    const mask = asset?.mask_url
    const unavailable = mode !== 'original' && (!asset?.processed_url || ((mode === 'mask' || mode === 'features') && !mask))
    const titles: Record<string,string> = {original:'原圖', processed:'本次處理圖', mask:'純 Mask', features:'特徵結果'}
    return {id:sample.id, name:sample.display_name || sample.file_name || sample.id,
      url: apiUrl(mode === 'original' ? sample.preview_url || sample.thumbnail_url || '' : mode === 'features' ? asset?.overlay_source_url || asset?.processed_url || '' : asset?.processed_url || ''),
      thumbnailUrl: mode === 'original' && sample.thumbnail_url ? apiUrl(sample.thumbnail_url) : undefined,
      detail: `${sample.class_name || '未分類'} · ${sample.split || '未切分'}`, badge: titles[mode],
      unavailable: unavailable ? results.loading ? '載入結果…' : '尚未產生可配對結果' : undefined,
      maskUrl:(mode === 'mask' || mode === 'features') && mask ? apiUrl(mask) : undefined,
      maskOnly:mode === 'mask', featureValues:mode === 'features' ? asset?.feature_values : undefined}
  }), [samples, mode, results.data, results.loading])
  return <>
    <div className="mb-3 grid gap-3 sm:grid-cols-2">
      <label><span className="label">展示模式</span><select className="field" value={mode} onChange={e => setMode(e.target.value)}><option value="original">原始影像</option><option value="processed">本次處理圖</option><option value="mask">純 Mask</option><option value="features">特徵結果</option></select></label>
      <label><span className="label">結果版本</span><select className="field" value={version} onChange={e => setVersion(e.target.value)}><option value="">最新完成的特徵工作</option>{results.data?.versions.map(v => <option key={v.id} value={v.id}>{v.name} · {v.id.slice(0,8)}</option>)}</select></label>
    </div>
    <p className="mb-3 text-xs leading-5 text-slate-500">展示著色不改寫 Mask 或模型輸入。Length_px 為原特徵計算的像素值；特徵疊圖使用已驗證同一版本的 UNet 512×512 座標底圖，不拉伸 Mask。{results.data?.job_id ? ` 結果工作：${results.data.job_id.slice(0,8)}` : ' 尚無已完成結果。'}</p>
    {results.error && <InlineNotice tone="warning">{String(results.error)}</InlineNotice>}
    {results.data?.warning && <InlineNotice tone="warning">{results.data.warning}</InlineNotice>}
    <PreviewGallery items={items} />
  </>
}
