import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { humanApiError } from '../lib/api'

export interface AsyncResource<T> {
  data: T | undefined
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  setData: Dispatch<SetStateAction<T | undefined>>
}

export function useAsyncResource<T>(loader: () => Promise<T>, enabled = true): AsyncResource<T> {
  const [data, setData] = useState<T>()
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(0)

  const refresh = useCallback(async () => {
    if (!enabled) return
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const result = await loader()
      if (requestId.current === id) setData(result)
    } catch (reason) {
      if (requestId.current === id) setError(humanApiError(reason))
    } finally {
      if (requestId.current === id) setLoading(false)
    }
  }, [enabled, loader])

  useEffect(() => {
    void refresh()
    return () => { requestId.current += 1 }
  }, [refresh])

  return { data, loading, error, refresh, setData }
}
