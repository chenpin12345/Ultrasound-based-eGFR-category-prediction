import { useCallback, useEffect, useId, useSyncExternalStore, type Dispatch, type SetStateAction } from 'react'
import { loadResource, resourceSnapshot, setResourceData, subscribeResource } from '../lib/resourceCache'

export interface AsyncResource<T> {
  data: T | undefined
  loading: boolean
  updating: boolean
  updateError: string | null
  error: string | null
  refresh: () => Promise<void>
  setData: Dispatch<SetStateAction<T | undefined>>
}

export function useAsyncResource<T>(loader: (signal?: AbortSignal) => Promise<T>, enabled = true, cacheKey?: string): AsyncResource<T> {
  const instance = useId()
  const key = cacheKey || `${instance}:${loaderKey(loader)}`
  const subscribe = useCallback((fn: () => void) => enabled ? subscribeResource(key, fn) : () => {}, [key, enabled])
  const snapshot = useSyncExternalStore(subscribe, () => resourceSnapshot<T>(key))
  const refresh = useCallback(() => enabled ? loadResource(key, loader, true) : Promise.resolve(), [key, loader, enabled])
  useEffect(() => { if (enabled) void loadResource(key, loader) }, [key, loader, enabled])
  const setData = useCallback<Dispatch<SetStateAction<T | undefined>>>(value => setResourceData(key, value), [key])
  const hasData = snapshot.data !== undefined
  return {data: enabled ? snapshot.data : undefined, loading: enabled && !hasData && !snapshot.error,
    updating: enabled && hasData && snapshot.refreshing, updateError: hasData ? snapshot.error : null,
    error: hasData ? null : snapshot.error, refresh, setData}
}
const keys = new WeakMap<Function, number>()
let next = 0
function loaderKey(loader: Function) { if (!keys.has(loader)) keys.set(loader, ++next); return keys.get(loader) }
