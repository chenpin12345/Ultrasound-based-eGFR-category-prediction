/** 醫師端（M3）的 API 型別與小工具。 */
import type { Tone } from '../components/ui'

export type ExamStatus = 'receiving' | 'analyzing' | 'needs_data' | 'layout_mismatch' | 'ready' | 'partial' | 'failed' | 'signed'
export type ReportStatus = 'draft' | 'pending' | 'signed' | 'void'
export type Side = 'right' | 'left'

export const SIDE_LABEL: Record<Side, string> = { right: '右腎', left: '左腎' }
export const CANDIDATE_LABEL = '尚未臨床核准・僅供研究展示'

export const examTone: Record<ExamStatus, Tone> = {
  receiving: 'neutral',
  analyzing: 'steel',
  needs_data: 'amber',
  layout_mismatch: 'amber',
  ready: 'ok',
  partial: 'amber',
  failed: 'alert',
  signed: 'neutral',
}
export const reportTone: Record<ReportStatus, Tone> = { draft: 'neutral', pending: 'amber', signed: 'ok', void: 'alert' }

export interface ExamRow {
  id: string
  case_code: string
  title: string
  received_at: string
  status: ExamStatus
  status_label: string
  images: number
  candidate: boolean
  p_lt60: number | null
  right_length_mm: number | null
  left_length_mm: number | null
  missing_clinical: string[]
  report_status: ReportStatus | null
  report_id: string | null
}

export interface ExamImage {
  id: string
  seq: number
  side: Side | null
  side_source: string
  pixel_spacing_mm: number | null
  spacing_source: string
  status: 'ok' | 'layout_mismatch' | 'residual' | 'excluded'
  exclude_reason: string
  width: number
  height: number
  deid: { missing?: string[]; residual?: string[]; sonographer_length_mm?: number | null }
}

export interface StepResult {
  status: 'done' | 'failed' | 'skipped' | 'not_configured'
  message: string
  missing?: string[]
}

export interface ImageResult {
  image_id: string
  side: Side | null
  pixel_spacing_mm: number | null
  missing: string[]
  sonographer_length_mm?: number | null
  length_mm?: number | null
  width_mm?: number | null
  ratio_mean?: number | null
  p_index?: number | null
  ref_organ?: string | null
  reliable?: boolean
  reasons?: string[]
  mask?: string
  egfr_probs?: number[]
}

export interface SideResult {
  images: number
  length_mm: number | null
  longest_image_id: string | null
  ratio_mean: number | null
  p_index: number | null
  sonographer_length_mm: number | null
  grade: { probs: number[]; predicted: string; classes: string[] } | null
  missing: string[]
}

export interface EgfrResult {
  k: number
  classes: string[]
  probs: number[]
  p_lt60: number
  p_lt30: number | null
  predicted: string
  images: number
}

export interface ModelUse {
  model_id: string
  stage: string
  run_id: string
  contract_version: number
  hashes?: unknown
}

export interface Analysis {
  id: string
  status: 'queued' | 'running' | 'completed' | 'partial' | 'failed'
  models: Record<string, ModelUse>
  inputs: { clinical?: Record<string, unknown>; missing_clinical?: string[]; device_note?: string }
  steps: Record<'segmentation' | 'egfr' | 'grade', StepResult>
  results: { images?: ImageResult[]; sides?: Partial<Record<Side, SideResult>>; unassigned?: string[]; egfr?: EgfrResult | null }
  candidate: boolean
  candidate_label: string
  device: string
  retry_of: string | null
  job_id: string | null
  created_by: string
  created_at: string
  finished_at: string | null
}

export interface ExamEdit {
  id: number
  image_id: string | null
  kind: string
  before: unknown
  after: unknown
  reason: string
  actor: string
  created_at: string
}

export interface ExamDetail {
  id: string
  patient: { id: string; case_code: string; mode: string; name?: string | null; mrn?: string | null }
  title: string
  mode: string
  source: string
  status: ExamStatus
  status_label: string
  received_at: string
  clinical: { age: number | null; sex: 'M' | 'F' | null; diabetes: 'yes' | 'no' | 'unknown'; source: string }
  missing_clinical: string[]
  overrides: Partial<Record<Side, { length_mm?: number; grade?: string }>>
  images: ExamImage[]
  analysis: Analysis | null
  analyses: { id: string; status: string; created_at: string; candidate: boolean }[]
  analysis_running: boolean
  edits: ExamEdit[]
  report: { id: string; status: ReportStatus; version: number } | null
  previous: { exam_id: string; received_at: string; sides: Partial<Record<Side, { length_mm: number | null; grade: string | null }>>; p_lt60: number | null; age: number | null } | null
}

export interface ReportSide {
  length_mm: number | null
  length_ai: number | null
  grade: string | null
  grade_ai: string | null
  ratio_mean: number | null
  images: number
  corticomedullary: string
  hydronephrosis: string
  stones: string
  cysts: string
}

export interface ReportPayload {
  sides: Partial<Record<Side, ReportSide>>
  egfr: EgfrResult | null
  ai_confirmed: boolean
  findings: string
  impression: string
  advice: string
  notes: string
}

export interface Report {
  id: string
  exam_id: string
  status: ReportStatus
  status_label: string
  version: number
  payload: ReportPayload
  signed_by: string | null
  signed_at: string | null
  void_reason: string
  analysis_id: string | null
  candidate: boolean
  candidate_label: string
  models: Record<string, ModelUse>
  pdf: { version: number; exists: boolean }
  case_code: string
  patient_mode: string
  exam_title: string
  received_at: string
  versions: { version: number; status: ReportStatus; actor: string; created_at: string; acknowledged: string[] }[]
  checklist: { key: string; text: string }[]
}

export interface ReportRow {
  id: string
  exam_id: string
  case_code: string
  status: ReportStatus
  status_label: string
  version: number
  signed_by: string | null
  signed_at: string | null
  updated_at: string
  void_reason: string
  pdf: boolean
}

export interface ReceiverStatus {
  session: { id: string; address: string; port: number; url: string; code: string | null; code_expires_at: string; fingerprint: string; started_at: string } | null
  interfaces: { address: string; name: string; label?: string }[]
  suggested: string | null
  port: number
  batches: { id: string; exam_id: string | null; status: string; created_at: string; finished_at: string | null; items: number; counts: Record<string, number> }[]
  firewall_hint: string
}

export interface ClinicalCounts {
  needs_data: number
  layout_mismatch: number
  failed: number
  ready: number
  analyzing: number
  pending_sign: number
  drafts: number
  today: number
  receiver_active: boolean
}

export interface ClinicalOverview {
  checks: { key: string; label: string; ok: boolean; detail: string; to: string }[]
  counts: ClinicalCounts
  candidate: boolean
  candidate_label: string
  recent_analyses: { id: string; exam_id: string; status: string; created_at: string; candidate: boolean }[]
  receiver: ReceiverStatus['session']
}

export const clinicalImageUrl = (id: string, kind: 'model' | 'thumb' = 'model') => `/api/clinical/images/${id}/${kind}`
export const overlayUrl = (analysisId: string, imageId: string) => `/api/clinical/analyses/${analysisId}/overlay/${imageId}`

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`)
export const mm = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v.toFixed(1)} mm`)
export const when = (iso: string | null | undefined) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—')
export const SEX_LABEL: Record<string, string> = { M: '男', F: '女' }
export const DM_LABEL: Record<string, string> = { yes: '有', no: '無', unknown: '不明' }
