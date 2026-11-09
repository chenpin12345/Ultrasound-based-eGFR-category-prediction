import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from './client'

/** 讀取資料：先顯示上一次的資料，重新整理失敗時保留資料並顯示錯誤（沿用腎超新的作法）。 */
export function useApi<T>(url: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(Boolean(url))
  const seq = useRef(0)

  const reload = useCallback(async () => {
    if (!url) return
    const mine = ++seq.current
    setLoading(true)
    try {
      const result = await api.get<T>(url)
      if (mine === seq.current) {
        setData(result)
        setError(null)
      }
    } catch (e) {
      if (mine === seq.current) setError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e)))
    } finally {
      if (mine === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, ...deps])

  useEffect(() => {
    void reload()
  }, [reload])

  return { data, error, loading, reload, setData }
}

/** 寫入動作：記錄進行中與錯誤，不自動重送。 */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const run = useCallback(
    async (...args: A): Promise<R | undefined> => {
      setBusy(true)
      setError(null)
      try {
        return await fn(...args)
      } catch (e) {
        setError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e)))
        return undefined
      } finally {
        setBusy(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn],
  )
  return { run, busy, error, clearError: () => setError(null) }
}

/** 輪詢：每隔 ms 重新讀取一次（任務數、進度等）。 */
export function usePolling(reload: () => void, ms: number, active = true) {
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(reload, ms)
    return () => window.clearInterval(id)
  }, [reload, ms, active])
}
