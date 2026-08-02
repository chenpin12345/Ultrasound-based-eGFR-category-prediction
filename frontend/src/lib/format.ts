import type { ClassDistributionItem, DatasetSummary, JobStatus } from '../types/api'

export const CLASS_NAMES = ['eGFR < 15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥ 90']

export function formatBytes(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return '—'
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`
}

export function formatDate(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date)
}

export function formatDuration(totalSeconds?: number): string {
  if (totalSeconds === undefined || totalSeconds < 0) return '—'
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = Math.floor(totalSeconds % 60)
  if (hours) return `${hours} 小時 ${minutes} 分`
  if (minutes) return `${minutes} 分 ${seconds} 秒`
  return `${seconds} 秒`
}

export function formatPercent(value?: number, fraction = false): string {
  if (value === undefined || Number.isNaN(value)) return '—'
  const normalized = fraction ? value * 100 : value
  return `${normalized.toFixed(normalized >= 10 ? 1 : 2)}%`
}

export const STATUS_LABELS: Record<string, string> = {
  queued: '排隊中', pending: '待處理', running: '執行中', stopping: '停止中',
  stopped: '已停止', completed: '已完成', failed: '失敗', interrupted: '已中斷', cancelled: '已取消',
  importing: '匯入中', ready: '可使用', active: '使用中', inactive: '未啟用', training: '訓練中',
  duplicate: '重複圖片', missing_label: '缺少標籤', missing_metadata: '缺少 metadata', missing_mask: '缺少 mask',
  corrupt: '損壞影像', corrupt_mask: '損壞 mask', unmatched_mask: '無法配對 mask', ambiguous_mask: 'mask 配對不明', duplicate_mask: '重複 mask',
}

export function statusLabel(status?: JobStatus | string): string {
  if (!status) return '未知'
  return STATUS_LABELS[status] || status
}

export function normalizeProgress(value?: number): number {
  if (value === undefined || Number.isNaN(value)) return 0
  return Math.max(0, Math.min(100, value <= 1 ? value * 100 : value))
}

export function distributionItems(summary?: DatasetSummary): ClassDistributionItem[] {
  const source = summary?.class_distribution
  if (!source) return []
  if (Array.isArray(source)) return source.map((item, index) => ({
    ...item,
    class_name: CLASS_NAMES[item.class_index ?? index] || item.class_name,
  }))
  const total = Object.values(source).reduce((sum, count) => sum + Number(count || 0), 0)
  return Object.entries(source).map(([class_name, count], index) => ({
    class_index: index,
    class_name,
    count: Number(count),
    percentage: total ? (Number(count) / total) * 100 : 0,
  }))
}

export function jobIdOf(value: { id?: string; job_id?: string; training_job_id?: string }): string {
  return value.training_job_id || value.job_id || value.id || ''
}
