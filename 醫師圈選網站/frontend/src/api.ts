export type Point = [number, number]
export type Side = 'right' | 'left' | null
export type Status = 'todo' | 'in_progress' | 'done' | 'unusable'

export interface Shape {
  id: number
  structure: string
  points: Point[]
}

export interface Structure {
  code: string
  name: string
  meaning: string
  color: string
  line: 'solid' | 'dashed'
  kind: 'core' | 'preset' | 'custom'
  active: boolean
  used: number
}

export interface Summary {
  total: number
  finished: number
  todo: number
  in_progress: number
  done: number
  unusable: number
  discuss: number
  next_id: string | null
  estimate: { seconds_per_image: number; remaining_hours: number } | null
  circler: string
}

export interface ImageRow {
  id: string
  seq: number
  side: Side
  status: Status
  discuss: boolean
}

export interface ImageDetail {
  id: string
  position: number
  total: number
  width: number
  height: number
  side: Side
  status: Status
  shapes: Shape[]
  states: Record<string, string>
  grade: number | null
  grade_unsure: boolean
  grade_reason: string
  note: string
  discuss: boolean
  unusable_reason: string
  prev_id: string | null
  next_id: string | null
}

export interface CompleteResult {
  ok: boolean
  status: Status
  errors: string[]
  warnings: string[]
}

export class ApiError extends Error {}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(data?.error?.message ?? '連不上網站程式。請確認啟動視窗還開著。')
  return data as T
}

export const imageUrl = (id: string) => `/api/images/${id}/file`
export const SIDE_LABEL: Record<string, string> = { right: '右腎', left: '左腎' }
export const STATUS_LABEL: Record<Status, string> = { todo: '未開始', in_progress: '進行中', done: '已完成', unusable: '不能用' }
