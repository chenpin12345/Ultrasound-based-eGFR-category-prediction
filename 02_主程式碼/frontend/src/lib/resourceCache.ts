// Bounded, memory-only display cache. Execution inputs are always revalidated by the server.
export const FRESH_MS = 30_000
export type Snapshot<T> = { data?: T; error: string | null; refreshing: boolean; updatedAt: number; lastSuccessAt: number }
type Entry = { snapshot: Snapshot<any>; listeners: Set<() => void>; loader?: (signal: AbortSignal) => Promise<any>; controller?: AbortController; promise?: Promise<void>; timer?: ReturnType<typeof setTimeout>; version: number }
const entries = new Map<string, Entry>()
const activityListeners = new Set<() => void>()
const emit = (entry: Entry) => { entry.listeners.forEach(fn => fn()); activityListeners.forEach(fn => fn()) }
export const subscribeActivity = (fn: () => void) => { activityListeners.add(fn); return () => { activityListeners.delete(fn) } }
export const activitySnapshot = () => {
  const active = [...entries.values()].filter(e => e.listeners.size)
  const visible = active.filter(e => e.snapshot.data !== undefined)
  const timestamps = visible.map(e => e.snapshot.lastSuccessAt).filter(Boolean)
  return JSON.stringify({updating: visible.some(e => e.snapshot.refreshing),
    error: visible.find(e => e.snapshot.error)?.snapshot.error || '',
    oldestReadAt: timestamps.length ? Math.min(...timestamps) : null})
}
function entryFor(key: string): Entry {
  let entry = entries.get(key)
  if (!entry) {
    if (entries.size >= 128) {
      const oldest = [...entries].find(([,value]) => !value.listeners.size && !value.promise)
      if (oldest) { clearTimeout(oldest[1].timer); entries.delete(oldest[0]) }
    }
    entry = { snapshot: {error: null, refreshing: false, updatedAt: 0, lastSuccessAt: 0}, listeners: new Set(), version: 0 }
    entries.set(key, entry)
  }
  return entry
}
export const resourceSnapshot = <T>(key: string): Snapshot<T> => entryFor(key).snapshot
export function subscribeResource(key: string, listener: () => void) {
  const entry = entryFor(key); entry.listeners.add(listener)
  activityListeners.forEach(fn => fn())
  return () => {
    entry.listeners.delete(listener)
    if (!entry.listeners.size) {
      clearTimeout(entry.timer); entry.controller?.abort(); entry.version++; entry.promise = undefined
      entry.snapshot = {...entry.snapshot, refreshing: false}
    }
    activityListeners.forEach(fn => fn())
  }
}
export async function loadResource(key: string, loader: (signal: AbortSignal) => Promise<any>, force = false): Promise<void> {
  const entry = entryFor(key); entry.loader = loader
  if (entry.promise) return entry.promise
  if (!force && entry.snapshot.updatedAt && Date.now() - entry.snapshot.updatedAt < FRESH_MS) { schedule(key, entry); return }
  const version = ++entry.version
  const controller = new AbortController(); entry.controller = controller
  entry.snapshot = {...entry.snapshot, refreshing: true, error: null}; emit(entry)
  entry.promise = (async () => {
    try {
      const data = await loader(controller.signal)
      if (entry.version === version) {
        const readAt = Date.now()
        entry.snapshot = {data: JSON.stringify(data) === JSON.stringify(entry.snapshot.data) ? entry.snapshot.data : data, error: null, refreshing: false, updatedAt: readAt, lastSuccessAt: readAt}
      }
    } catch (error) {
      if (entry.version === version && !controller.signal.aborted) entry.snapshot = {...entry.snapshot, refreshing: false, error: error instanceof Error ? error.message : '無法取得資料'}
    } finally {
      if (entry.version === version) { entry.promise = undefined; emit(entry); schedule(key, entry) }
    }
  })()
  return entry.promise
}
function schedule(key: string, entry: Entry) {
  clearTimeout(entry.timer)
  if (!entry.listeners.size || !entry.loader) return
  const wait = entry.snapshot.error ? FRESH_MS : Math.max(1, FRESH_MS - (Date.now() - entry.snapshot.updatedAt))
  entry.timer = setTimeout(() => {
    if (typeof document !== 'undefined' && document.hidden) {
      entry.timer = setTimeout(() => schedule(key, entry), FRESH_MS); return
    }
    if (entry.loader) void loadResource(key, entry.loader, true)
  }, wait)
}
export function setResourceData<T>(key: string, value: T | undefined | ((previous: T | undefined) => T | undefined)) {
  const entry = entryFor(key)
  const data = typeof value === 'function' ? (value as (p: T | undefined) => T | undefined)(entry.snapshot.data) : value
  entry.snapshot = {...entry.snapshot, data}; emit(entry)
}
const channel = typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('isu-display-cache') : undefined
export function invalidateResources(broadcast = true) {
  for (const [key, entry] of entries) {
    entry.controller?.abort(); entry.version++; entry.promise = undefined
    entry.snapshot = {...entry.snapshot, updatedAt: 0, refreshing: false}
    if (entry.listeners.size && entry.loader) void loadResource(key, entry.loader, true)
    else emit(entry)
  }
  if (broadcast) channel?.postMessage('invalidate')
}
if (channel) channel.onmessage = event => { if (event.data === 'invalidate') invalidateResources(false) }
export function clearResourceCache() {
  for (const entry of entries.values()) { clearTimeout(entry.timer); entry.controller?.abort(); entry.version++ }
  entries.clear()
}
