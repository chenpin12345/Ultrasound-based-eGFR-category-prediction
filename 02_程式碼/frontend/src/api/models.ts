import { useEffect, useState } from 'react'
import { api, ApiError } from './client'
import type { ModelInfo } from './ml'

/** 三區的模型一起讀（一鍵流程、AI 分析需要分割＋分類模型；清單頁依任務分開）。 */
export function useAllModels() {
  const [data, setData] = useState<{ models: ModelInfo[] } | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  useEffect(() => {
    let alive = true
    Promise.all(['segmentation', 'egfr', 'grade'].map((t) => api.get<{ models: ModelInfo[] }>(`/models?task=${t}`)))
      .then((parts) => alive && setData({ models: parts.flatMap((p) => p.models) }))
      .catch((e) => alive && setError(e as ApiError))
    return () => {
      alive = false
    }
  }, [])
  return { data, error, loading: !data && !error }
}
