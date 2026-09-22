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
  const state = JSON.parse(useSyncExternalStore(subscribeActivity, activitySnapshot)) as {updating: boolean; error: string}
  if (!state.updating && !state.error) return null
  return <div role="status" aria-live="polite" className="mb-3 flex flex-wrap items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
    {state.error ? <><span>更新失敗，暫時顯示上次資料：{state.error}</span><button className="btn-secondary" onClick={() => invalidateResources()}>重新整理</button></> : '更新中，先顯示上次取得的資料…'}
  </div>
}
