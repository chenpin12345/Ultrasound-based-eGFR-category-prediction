import { useEffect, useSyncExternalStore } from 'react'
import { apiUrl } from '../lib/api'
import { activitySnapshot, invalidateResources, subscribeActivity } from '../lib/resourceCache'

export function ResourceStatus() {
  useEffect(() => {
    let revision = ''
    const events = new EventSource(apiUrl('/workflow/events'))
    events.onmessage = event => {
      const next = (JSON.parse(event.data) as {revision: string}).revision
      if (revision && next !== revision) invalidateResources(false)
      revision = next
    }
    return () => events.close()
  }, [])
  const state = JSON.parse(useSyncExternalStore(subscribeActivity, activitySnapshot)) as {updating: boolean; error: string; oldestReadAt: number | null}
  if (!state.updating && !state.error && !state.oldestReadAt) return null
  return <div role="status" aria-label="資料更新狀態" aria-live="polite" className="mt-3 flex flex-wrap items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
    {state.oldestReadAt && <span>已顯示資料最早讀取時間：<time dateTime={new Date(state.oldestReadAt).toISOString()}>{new Date(state.oldestReadAt).toLocaleString('zh-TW')}</time></span>}
    {state.error ? <><span className="min-w-0 break-words">更新失敗，暫時顯示上次資料：{state.error}</span><button className="btn-secondary min-h-11" onClick={() => invalidateResources()}>重試資料更新</button></> : state.updating ? <span>更新中，先顯示上次取得的資料…</span> : null}
  </div>
}
