export interface Person {
  id: number
  name: string
  kind: 'physician' | 'operator'
  active: boolean
}

export interface Overview {
  images: { total: number; usable?: number; pending_review?: number; excluded?: number }
  patients: number
  unmatched_images: number
  batches: number
  pending_feedback: number
  clinical?: Partial<import('./clinical').ClinicalCounts>
  failed_jobs: number
  running_jobs: number
}

export interface Job {
  id: string
  kind: string
  kind_label: string
  target: string
  status: 'queued' | 'running' | 'stopping' | 'stopped' | 'completed' | 'failed' | 'interrupted'
  progress: number
  message: string
  error_code: string | null
  error_message: string | null
  created_by: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  retry_of: string | null
  resumable: boolean
  result: Record<string, unknown>
  events?: { id: number; type: string; data: Record<string, unknown>; created_at: string }[]
}

export interface ImageInfo {
  id: string
  batch_id: string
  patient_id: string | null
  machine: string
  template_id: string | null
  width: number
  height: number
  side: 'right' | 'left' | null
  side_source: string
  view: 'long' | 'short' | 'oblique' | null
  pixel_spacing_mm: number | null
  spacing_check: string
  sonographer_length_mm: number | null
  sonographer_width_mm: number | null
  gain: number | null
  caliper_pixels: number
  status: 'usable' | 'pending_review' | 'excluded'
  review_reasons: string[]
  exclude_reason: string | null
  deid_check: 'pass' | 'residual' | 'unchecked'
  created_at: string
  egfr_group: string | null
  mask_versions?: number
}

export interface Rect {
  name?: string
  x: number
  y: number
  w: number
  h: number
}

export interface Template {
  id: string
  machine: string
  width: number
  height: number
  version: number
  regions: Rect[]
  readers: Record<'header' | 'params' | 'measure' | 'side' | 'ruler' | 'bodymark', Rect>
  updated_at: string
  updated_by: string
  images?: number
}

export interface Batch {
  id: string
  source_kind: 'original' | 'inbox' | 'clinical'
  source_label: string
  status: string
  created_by: string
  created_at: string
  finished_at: string | null
  counts: Record<string, number>
}

export interface SplitGroup {
  group: string
  patients: number
  images: number
  toshiba_ratio: number | null
  strata: Record<string, number>
}

export interface SplitInfo {
  id: string
  parent_id: string | null
  method: string
  seed: number
  folds: number
  test_ratio: number
  sha256: string
  note: string
  created_by: string
  created_at: string
  counts: Record<string, number>
}

export interface TaskSummary {
  id: 'mask' | 'grade' | 'side'
  name: string
  done: number
  total: number
  double?: number
}

export const statusLabel: Record<ImageInfo['status'], string> = { usable: '可用', pending_review: '待人工確認', excluded: '已排除' }
export const sideLabel = { right: '右', left: '左' } as const
export const viewLabel = { long: '長軸', short: '短軸', oblique: '斜切' } as const
export const jobStatusLabel: Record<Job['status'], string> = {
  queued: '排隊中',
  running: '執行中',
  stopping: '停止中',
  stopped: '已停止',
  completed: '完成',
  failed: '失敗',
  interrupted: '中斷',
}
