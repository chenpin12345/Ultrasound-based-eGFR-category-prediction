import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, humanApiError, requestJson } from './api'
import type { Job, Dataset } from '../types/api'
import { useAsyncResource } from '../hooks/useAsyncResource'

export interface SourceRef { kind: 'dataset' | 'job'; id: string }
export const workflowSteps = [
  ['/datasets', '資料集與品質'], ['/processing', '影像前處理'], ['/masks', '遮罩準備'],
  ['/features', '特徵擷取'], ['/training', '模型訓練'], ['/inference', 'AI 推論'],
]
export interface SourceSummary {
  source: SourceRef; dataset_id?: string; name: string; image_count: number; mask_count: number
  metadata_count: number; has_features: boolean; labeled_count: number
}
export const workflowApi = {
  summary: (source: SourceRef, signal?: AbortSignal) => requestJson<SourceSummary>(`/workflow/source?kind=${source.kind}&id=${encodeURIComponent(source.id)}`, {signal}),
  derive: (source: SourceRef, name: string) => requestJson<Dataset>('/datasets/from-results', { method: 'POST', body: JSON.stringify({ input_sources: { images: source }, name }) }),
}

export function workflowLink(path: string, datasetId = '', jobId = '') {
  const query = new URLSearchParams()
  if (datasetId) query.set('dataset_id', datasetId)
  if (jobId) query.set('source_job', jobId)
  return `${path}${query.size ? `?${query}` : ''}`
}

export function useWorkflowJob(kind: string) {
  const [params, setParams] = useSearchParams()
  const datasetId = params.get('dataset_id') || ''
  const sourceId = params.get('source_job') || ''
  const upload = params.get('input') === 'upload'
  const sourceKind = sourceId ? 'job' : 'dataset'
  const id = upload ? '' : sourceId || datasetId
  const active = Boolean(id)
  const [jobError, setSourceError] = useState('')
  const sourceLoader = useCallback((signal?: AbortSignal) => workflowApi.summary({kind: sourceKind, id}, signal), [sourceKind, id])
  const resource = useAsyncResource(sourceLoader, active, `source:${sourceKind}:${id}`)
  const summary = resource.data, loading = resource.loading
  const sourceError = resource.error || jobError
  const [job, updateJob] = useState<Job>()
  const jobId = params.get('job_id') || ''
  useEffect(() => { setSourceError('') }, [active, id, sourceKind])
  useEffect(() => {
    let live = true
    const controller = new AbortController()
    if (!jobId) { updateJob(undefined); return }
    api.getJob(jobId, controller.signal).then(value => {
      if (value.kind !== kind) throw new Error('工作類型與此頁不符，請從歷史工作開啟。')
      if (live) updateJob(value)
    }).catch(reason => { if (live) { updateJob(undefined); setSourceError(humanApiError(reason)) } })
    return () => { live = false; controller.abort() }
  }, [jobId, kind])
  const setJob = useCallback((value: Job | undefined) => {
    updateJob(value)
    setParams(current => { const next = new URLSearchParams(current); if (value) next.set('job_id', value.id); else next.delete('job_id'); return next }, { replace: true })
  }, [setParams])
  const ready = active && !loading && !sourceError && Boolean(summary)
  const submitting = useRef(false)
  const create = async (form: FormData) => {
    if (submitting.current) throw new Error('工作建立中，請勿重複送出。')
    submitting.current = true
    try {
    if (!active) return await api.createJob(form)
    if (!ready) throw new Error('請先確認有效的工作來源。')
    if ([...form.keys()].some(key => key.startsWith('override_'))) throw new Error('專用來源上傳請切換至「獨立上傳」模式。')
    if ([...form.values()].some(value => value instanceof File && value.size > 0)) throw new Error('已選擇沿用來源；如需使用上傳檔案，請切換至「獨立上傳」。')
    const config = JSON.parse(String(form.get('config') || '{}')) as Record<string, unknown>
    return await api.createJob({ kind, name: form.get('name'), config, input_sources: { images: { kind: sourceKind, id } } })
    } finally { submitting.current = false }
  }
  return { active, ready, summary, sourceError, loading, job, setJob, create, datasetId }
}
