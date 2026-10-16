import { useEffect, useRef, useState } from 'react'
import type { JobEvent } from '../types/api'
import { invalidateResources } from '../lib/resourceCache'

export type StreamState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed'

export interface JobEventStream {
  events: JobEvent[]
  latest: JobEvent | undefined
  state: StreamState
  cursor: string
  clear: () => void
}

function parseEvent(event: MessageEvent<string>): JobEvent {
  try {
    const parsed = JSON.parse(event.data) as JobEvent & { data?: Record<string, unknown> }
    const nested = parsed.data && typeof parsed.data === 'object' ? parsed.data : {}
    return {
      ...parsed,
      ...nested,
      id: parsed.id || event.lastEventId || undefined,
      type: event.type === 'message' ? parsed.type : event.type,
      payload: parsed.payload || (Object.keys(nested).length ? nested : (parsed as unknown as Record<string, unknown>)),
    } as JobEvent
  } catch {
    return { id: event.lastEventId || undefined, type: event.type, message: event.data }
  }
}

export function useJobEvents(url: string | undefined, enabled = true): JobEventStream {
  const [events, setEvents] = useState<JobEvent[]>([])
  const [state, setState] = useState<StreamState>('idle')
  const cursorRef = useRef('')

  useEffect(() => {
    setEvents([])
    cursorRef.current = ''
    if (!url || !enabled) {
      setState('idle')
      return
    }

    let source: EventSource | undefined
    let timer: ReturnType<typeof setTimeout> | undefined
    let disposed = false
    let attempts = 0
    let terminal = false

    const receive = (raw: Event) => {
      const event = parseEvent(raw as MessageEvent<string>)
      const cursor = event.id || (event.sequence !== undefined ? String(event.sequence) : '')
      if (cursor) cursorRef.current = cursor
      setEvents((current) => [...current, event].slice(-500))
      if (['completed', 'failed', 'stopped', 'interrupted', 'cancelled'].includes(event.status || '')) {
        invalidateResources()
        terminal = true
        source?.close()
        setState('closed')
      }
    }

    const connect = () => {
      if (disposed) return
      setState(attempts ? 'reconnecting' : 'connecting')
      const separator = url.includes('?') ? '&' : '?'
      const streamUrl = cursorRef.current ? `${url}${separator}after=${encodeURIComponent(cursorRef.current)}` : url
      source = new EventSource(streamUrl)
      source.onopen = () => {
        attempts = 0
        setState('connected')
      }
      source.onmessage = receive
      for (const eventName of ['queued', 'progress', 'status', 'training_progress', 'epoch_completed', 'resource_sample', 'log', 'result', 'completed', 'failed', 'stopping', 'stopped', 'interrupted', 'error']) {
        source.addEventListener(eventName, receive)
      }
      source.onerror = () => {
        source?.close()
        if (disposed || terminal) return
        attempts += 1
        setState('reconnecting')
        const wait = Math.min(15_000, 1_000 * 2 ** Math.min(attempts, 4))
        timer = setTimeout(connect, wait)
      }
    }

    connect()
    return () => {
      disposed = true
      source?.close()
      if (timer) clearTimeout(timer)
      setState('closed')
    }
  }, [enabled, url])

  return {
    events,
    latest: events.at(-1),
    state,
    cursor: cursorRef.current,
    clear: () => setEvents([]),
  }
}
