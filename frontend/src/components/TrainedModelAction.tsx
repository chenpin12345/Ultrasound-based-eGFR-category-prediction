import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api, listItems } from '../lib/api'
import { useAsyncResource } from '../hooks/useAsyncResource'
import type { ModelInfo } from '../types/api'
import { Card, StatePanel } from './ui'

export function TrainedModelAction({ jobId, status, datasetId }: { jobId: string; status?: string; datasetId?: string }) {
  const loader = useCallback(async (signal?: AbortSignal) => listItems<ModelInfo>(await api.listModels(signal)), [])
  const models = useAsyncResource(loader, status === 'completed', 'models')
  if (status !== 'completed') return null
  const model = models.data?.find(item => item.source_training_job_id === jobId)
  return <Card className="mt-6 border-clinical-200 p-5"><h2 className="section-title">使用本次訓練模型</h2><StatePanel loading={models.loading} error={models.error} onRetry={() => void models.refresh()}><p className="my-3 text-sm text-slate-600">{model ? `已註冊：${model.name}。下一頁確認輸入後再執行推論。` : '模型尚未出現在模型庫，請重新整理確認。'}</p>{model && <Link className="btn-primary" to={`/inference?model_id=${encodeURIComponent(model.id)}&dataset_id=${encodeURIComponent(datasetId || '')}`}>使用此模型前往推論</Link>}</StatePanel></Card>
}
