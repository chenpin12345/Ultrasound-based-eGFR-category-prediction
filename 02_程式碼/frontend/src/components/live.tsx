import { useEffect, useState } from 'react'
import { AlertTriangle, Square } from 'lucide-react'
import { api, type ApiError } from '../api/client'
import { jobStatusLabel, type Job } from '../api/types'
import { Button, Pill, ProgressBar, type Tone } from './ui'

export const jobTone: Record<Job['status'], Tone> = {
  queued: 'neutral',
  running: 'steel',
  stopping: 'amber',
  stopped: 'neutral',
  completed: 'ok',
  failed: 'alert',
  interrupted: 'amber',
}

const ACTIVE = new Set(['queued', 'running', 'stopping'])

/** 顯示一個背景工作的即時進度；結束時呼叫 onDone。 */
export function JobProgress({ jobId, onDone }: { jobId: string; onDone?: (job: Job) => void }) {
  const [job, setJob] = useState<Job | null>(null)

  useEffect(() => {
    let alive = true
    let timer = 0
    const tick = async () => {
      try {
        const j = await api.get<Job>(`/jobs/${jobId}`)
        if (!alive) return
        setJob(j)
        if (ACTIVE.has(j.status)) timer = window.setTimeout(tick, 1000)
        else onDone?.(j)
      } catch {
        if (alive) timer = window.setTimeout(tick, 3000)
      }
    }
    void tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  if (!job) return <p className="text-[14px] text-ink-soft">讀取工作狀態…</p>
  return (
    <div className="space-y-2 rounded-md border border-line bg-paper/50 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-medium">{job.kind_label}</span>
        <Pill tone={jobTone[job.status]}>{jobStatusLabel[job.status]}</Pill>
        <span className="text-[13px] text-ink-faint">{job.id}</span>
        {ACTIVE.has(job.status) && (
          <span className="ml-auto">
            <Button icon={Square} onClick={() => void api.post(`/jobs/${job.id}/stop`)}>
              停止
            </Button>
          </span>
        )}
      </div>
      <ProgressBar value={job.progress} label="工作進度" />
      {job.message && <p className="text-[13px] text-ink-soft">{job.message}</p>}
      {job.error_message && <ErrorNote message={job.error_message} />}
    </div>
  )
}

export function ErrorNote({ message, error }: { message?: string; error?: ApiError | null }) {
  const text = message ?? error?.message
  if (!text) return null
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      {text}
    </p>
  )
}

export function Loading({ text = '讀取中…' }: { text?: string }) {
  return <p className="px-5 py-6 text-[14px] text-ink-faint">{text}</p>
}
