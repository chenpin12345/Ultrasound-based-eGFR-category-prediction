import { invalidateResources } from './resourceCache'
import type {
  ApiEnvelope,
  ApiErrorBody,
  Artifact,
  Dataset,
  DatasetImportIssue,
  DatasetSample,
  DatasetSummary,
  EpochMetric,
  HealthInfo,
  InferenceResult,
  Job,
  JobResults,
  ModelInfo,
  PageResult,
  SystemInfo,
  SystemSettings,
  TrainingConfig,
  TrainingJob,
  TrainingMetrics,
} from '../types/api'

const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api'
export const API_BASE = configuredBase.replace(/\/$/, '')

export class ApiClientError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: ApiErrorBody['details']
  readonly requestId?: string

  constructor(message: string, status = 0, body?: ApiErrorBody) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = body?.code || 'REQUEST_FAILED'
    this.details = body?.details
    this.requestId = body?.request_id
  }
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  if (path.startsWith('/api/')) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export function unwrapPayload<T>(body: T | ApiEnvelope<T>): T {
  if (body && typeof body === 'object' && 'data' in body) {
    return (body as ApiEnvelope<T>).data
  }
  return body as T
}

export function listItems<T>(payload: T[] | PageResult<T> | Record<string, unknown> | null | undefined): T[] {
  if (!payload) return []
  if (Array.isArray(payload)) return payload
  if ('items' in payload && Array.isArray(payload.items)) return payload.items as T[]
  const record = payload as Record<string, unknown>
  for (const key of ['datasets', 'jobs', 'models', 'training_jobs', 'samples']) {
    const value = record[key]
    if (Array.isArray(value)) return value as T[]
  }
  return []
}

function mapCollection<T, U>(payload: T[] | PageResult<T>, mapper: (item: T) => U): U[] | PageResult<U> {
  if (Array.isArray(payload)) return payload.map(mapper)
  return { ...payload, items: payload.items.map(mapper) }
}

function normalizeDataset(item: Dataset): Dataset {
  return {
    ...item,
    image_count: item.image_count ?? item.sample_count,
    size_bytes: item.size_bytes ?? item.total_bytes,
  }
}

function normalizeDatasetSummary(item: DatasetSummary): DatasetSummary {
  return {
    ...item,
    image_count: item.image_count ?? item.sample_count,
    total_samples: item.total_samples ?? item.sample_count,
    total_size_bytes: item.total_size_bytes ?? item.total_bytes,
    class_distribution: item.class_distribution ?? item.classes,
    split_counts: item.split_counts ?? item.splits,
    missing_label_count: item.missing_label_count ?? item.unlabeled,
    duplicate_count: item.duplicate_count ?? item.duplicates,
  }
}

function normalizeDatasetSample(item: DatasetSample & { metadata_json?: Record<string, unknown>; duplicate_of_id?: string; file_url?: string }): DatasetSample {
  return {
    ...item,
    class_name: item.class_index !== undefined && item.class_index !== null ? EGFR_CLASS_NAMES[item.class_index] || item.class_name : item.class_name,
    metadata: item.metadata ?? item.metadata_json,
    is_duplicate: item.is_duplicate ?? Boolean(item.duplicate_of_id),
    preview_url: item.preview_url ?? item.file_url,
  }
}

function normalizeJob(item: Job & { config_json?: Record<string, unknown>; result_json?: Record<string, unknown>; completed_at?: string }): Job {
  return {
    ...item,
    name: item.name ?? (typeof item.config_json?.name === 'string' ? item.config_json.name : undefined),
    config: item.config ?? item.config_json,
    finished_at: item.finished_at ?? item.completed_at,
    result_count: item.result_count ?? (Array.isArray(item.result_json?.items) ? item.result_json.items.length : Array.isArray((item.result_json?.inference as Record<string, unknown>)?.items) ? ((item.result_json!.inference as Record<string, unknown>).items as unknown[]).length : undefined),
  }
}

function normalizeModel(item: ModelInfo): ModelInfo {
  return {
    ...item,
    is_active: item.is_active ?? item.active,
    is_default: item.is_default ?? item.active,
    source: item.source ?? (item.source_training_job_id ? 'training' : 'external'),
  }
}

function normalizeTraining(item: TrainingJob & { model_name?: string; best_metric?: number }): TrainingJob {
  return {
    ...item,
    training_job_id: item.training_job_id ?? item.id,
    name: item.name ?? item.model_name,
    best_validation_loss: item.best_validation_loss ?? item.best_metric,
  }
}

const EGFR_CLASS_NAMES = ['eGFR < 15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥ 90']

function normalizeInferenceResult(item: Record<string, any>, labels: string[] = EGFR_CLASS_NAMES): InferenceResult {
  const predictedIndex = Number(item.predicted_index ?? item.class_index)
  const rawProbabilities = item.probabilities
  const probabilities = Array.isArray(rawProbabilities) && rawProbabilities.every((value) => typeof value === 'number')
    ? rawProbabilities.map((probability, classIndex) => ({ class_index: classIndex, class_name: labels[classIndex] || `Class ${classIndex}`, probability }))
    : rawProbabilities
  return {
    ...item,
    file_name: item.file_name ?? item.file ?? item.filename ?? '未命名影像',
    predicted_index: Number.isFinite(predictedIndex) ? predictedIndex : undefined,
    predicted_class: item.predicted_class ?? (Number.isFinite(predictedIndex) ? labels[predictedIndex] : undefined) ?? '未分類',
    confidence: Number(item.confidence ?? 0),
    probabilities: probabilities ?? [],
  }
}

function normalizeSystemInfo(raw: Record<string, any>): SystemInfo {
  const runtime = raw.runtime || {}
  const resources = raw.resources || {}
  const cuda = resources.cuda || {}
  return {
    app_name: raw.app_name ?? raw.application?.name,
    version: raw.version ?? raw.application?.version,
    python_version: raw.python_version ?? runtime.python,
    torch_version: raw.torch_version,
    platform: raw.platform ?? [runtime.platform, runtime.platform_release].filter(Boolean).join(' '),
    cpu_count: raw.cpu_count ?? resources.cpu_count,
    memory_total_bytes: raw.memory_total_bytes ?? resources.memory?.total,
    cuda_available: raw.cuda_available ?? cuda.available,
    gpu_name: raw.gpu_name ?? cuda.devices?.[0],
    model_count: raw.model_count,
  }
}

function normalizeTrainingMetrics(raw: Record<string, any>): TrainingMetrics {
  if (raw.history || raw.latest || raw.resources) return raw as TrainingMetrics
  const grouped = new Map<number, EpochMetric>()
  for (const source of listItems<Record<string, any>>(raw)) {
    const epoch = Number(source.epoch)
    const current = grouped.get(epoch) || { epoch }
    const split = String(source.split || '').toLowerCase()
    if (split === 'train' || split === 'training') {
      current.train_loss = source.loss
      current.train_accuracy = source.accuracy
    } else if (split === 'validation' || split === 'val') {
      current.validation_loss = source.loss
      current.validation_accuracy = source.accuracy
      current.precision = source.precision
      current.recall = source.recall
      current.f1_score = source.f1 ?? source.f1_score
      current.confusion_matrix = source.confusion_matrix
    } else if (split === 'test') {
      current.test_accuracy = source.accuracy
    }
    current.learning_rate = source.learning_rate ?? current.learning_rate
    grouped.set(epoch, current)
  }
  const history = [...grouped.values()].sort((a, b) => a.epoch - b.epoch)
  return { history, items: history, latest: history.at(-1), confusion_matrix: history.at(-1)?.confusion_matrix }
}

function errorBody(value: unknown): ApiErrorBody | undefined {
  if (!value || typeof value !== 'object') return undefined
  const body = value as Record<string, unknown>
  if (body.error && typeof body.error === 'object') return body.error as ApiErrorBody
  if (typeof body.detail === 'string') return { message: body.detail }
  if (Array.isArray(body.detail)) return { message: '輸入資料驗證失敗', details: body.detail as ApiErrorBody['details'] }
  if (typeof body.message === 'string') return body as unknown as ApiErrorBody
  return undefined
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  headers.set('Accept', 'application/json')
  const readonly = !init.method || init.method.toUpperCase() === 'GET'
  const controller = new AbortController()
  const cancel = () => controller.abort()
  init.signal?.addEventListener('abort', cancel, {once: true})
  if (init.signal?.aborted) controller.abort()
  const timer = readonly ? setTimeout(cancel, 15_000) : undefined
  try {
  const response = await fetch(apiUrl(path), { ...init, headers, signal: controller.signal })
  const contentType = response.headers.get('content-type') || ''
  const body: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => undefined)
    : await response.text().catch(() => undefined)
  if (controller.signal.aborted) throw new DOMException('Request aborted', 'AbortError')
  if (!response.ok) {
    const parsed = errorBody(body)
    throw new ApiClientError(parsed?.message || `伺服器回應錯誤（${response.status}）`, response.status, parsed)
  }
  if (!readonly) invalidateResources()
  if (response.status === 204) return undefined as T
  return unwrapPayload(body as T | ApiEnvelope<T>)
  } catch (error) {
    if (readonly && controller.signal.aborted && !init.signal?.aborted) throw new Error('讀取資料超過 15 秒，請重試；已提交的 AI 工作不受影響。')
    throw error
  } finally { clearTimeout(timer); init.signal?.removeEventListener('abort', cancel) }
}

function jsonBody(value: unknown): BodyInit {
  return JSON.stringify(value)
}

export const api = {
  health: () => requestJson<HealthInfo>('/health'),
  systemInfo: async () => normalizeSystemInfo(await requestJson<Record<string, any>>('/system/info')),
  getSettings: () => requestJson<SystemSettings>('/settings'),
  updateSettings: (settings: SystemSettings) =>
    requestJson<SystemSettings>('/settings', { method: 'PUT', body: jsonBody(settings) }),

  listDatasets: async (signal?: AbortSignal) => mapCollection(await requestJson<Dataset[] | PageResult<Dataset>>('/datasets', {signal}), normalizeDataset),
  createDataset: async (form: FormData) => normalizeDataset(await requestJson<Dataset>('/datasets', { method: 'POST', body: form })),
  getDataset: async (id: string) => normalizeDataset(await requestJson<Dataset>(`/datasets/${encodeURIComponent(id)}`)),
  getDatasetSummary: async (id: string, signal?: AbortSignal) => normalizeDatasetSummary(await requestJson<DatasetSummary>(`/datasets/${encodeURIComponent(id)}/summary`, {signal})),
  datasetSummaryDownloadUrl: (id: string) => apiUrl(`/datasets/${encodeURIComponent(id)}/summary?download=1`),
  getDatasetSamples: async (id: string, query = '', signal?: AbortSignal) => mapCollection(await requestJson<DatasetSample[] | PageResult<DatasetSample>>(`/datasets/${encodeURIComponent(id)}/samples${query}`, {signal}), normalizeDatasetSample),
  getDatasetIssues: (id: string, query = '') => requestJson<DatasetImportIssue[] | PageResult<DatasetImportIssue>>(`/datasets/${encodeURIComponent(id)}/issues${query}`),
  deleteDataset: (id: string) => requestJson<void>(`/datasets/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  createJob: async (form: FormData | Record<string, unknown>) =>
    normalizeJob(await requestJson<Job>('/jobs', {
      method: 'POST',
      body: form instanceof FormData ? form : jsonBody(form),
    })),
  listJobs: async (signal?: AbortSignal) => {
    const items: Job[] = []; let offset = 0
    while (true) {
      const page = await requestJson<PageResult<Job>>(`/jobs?view=summary&limit=200&offset=${offset}`, {signal})
      items.push(...page.items.map(normalizeJob)); offset += page.items.length
      if (!page.items.length || offset >= (page.total ?? offset)) return {items, total: page.total}
    }
  },
  getJob: async (id: string, signal?: AbortSignal) => normalizeJob(await requestJson<Job>(`/jobs/${encodeURIComponent(id)}?view=summary`, {signal})),
  startProcess: (id: string, config: Record<string, unknown>) =>
    requestJson<Job>(`/jobs/${encodeURIComponent(id)}/process`, { method: 'POST', body: jsonBody({ config }) }),
  startMasks: (id: string, config: Record<string, unknown>) =>
    requestJson<Job>(`/jobs/${encodeURIComponent(id)}/masks`, { method: 'POST', body: jsonBody({ config }) }),
  startFeatures: (id: string, config: Record<string, unknown>) =>
    requestJson<Job>(`/jobs/${encodeURIComponent(id)}/features`, { method: 'POST', body: jsonBody({ config }) }),
  startInference: (id: string, config: Record<string, unknown>) =>
    requestJson<Job>(`/jobs/${encodeURIComponent(id)}/inference`, { method: 'POST', body: jsonBody({ config }) }),
  getJobResults: async (id: string, page?: number, signal?: AbortSignal) => {
    const query = page === undefined ? '' : `?offset=${page*60}&limit=60`
    const raw = await requestJson<Record<string, any>>(`/jobs/${encodeURIComponent(id)}/results${query}`, {signal})
    const nested = raw.results?.inference ? { ...raw.results, ...raw.results.inference } : raw.results
    if (Array.isArray(nested)) return { job_id: raw.job_id, results: nested.map(item => normalizeInferenceResult(item)) } as JobResults
    const result = { job_id: raw.job_id, ...(nested && typeof nested === 'object' ? nested : {}) } as JobResults
    const labels: string[] = Array.isArray(nested?.class_names) ? nested.class_names : EGFR_CLASS_NAMES
    if (Array.isArray(result.results)) result.results = result.results.map((item) => normalizeInferenceResult(item as unknown as Record<string, any>, labels))
    if (Array.isArray(result.items)) result.items = result.items.map((item) => normalizeInferenceResult(item as unknown as Record<string, any>, labels))
    const summary = nested && typeof nested === 'object' ? (nested as Record<string, any>).summary : undefined
    if (!result.statistics && summary?.counts) result.statistics = summary.counts
    return result
  },
  deleteJob: (id: string) => requestJson<void>(`/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  jobDownloadUrl: (id: string) => apiUrl(`/jobs/${encodeURIComponent(id)}/download`),
  jobEventsUrl: (id: string) => apiUrl(`/jobs/${encodeURIComponent(id)}/events`),

  createTrainingJob: async (config: TrainingConfig) => normalizeTraining(await requestJson<TrainingJob>('/training/jobs', {
    method: 'POST',
    body: jsonBody({
      dataset_id: config.dataset_id,
      model_name: config.name || config.architecture,
      architecture: config.architecture === 'mobilenet_v2' ? 'mobilenetv2' : config.architecture === 'mlp_resnet18' ? 'mlp-resnet18' : config.architecture,
      epochs: config.epochs,
      batch_size: config.batch_size,
      learning_rate: config.learning_rate,
      optimizer: config.optimizer,
      weight_decay: config.weight_decay,
      scheduler: config.scheduler === 'plateau' ? 'reduce_on_plateau' : config.scheduler,
      early_stopping: config.early_stopping,
      patience: config.patience,
      seed: config.random_seed,
      device: config.device,
      class_weights: config.class_weights,
      augmentation: config.data_augmentation,
      k_fold: config.k_folds >= 2 ? config.k_folds : null,
      classification_mode: config.classification_mode,
      train_ratio: config.train_ratio,
      validation_ratio: config.validation_ratio,
      test_ratio: config.test_ratio,
      checkpoint_interval: config.checkpoint_interval,
      resume_checkpoint: config.resume_from || null,
      extra: {
        mode: config.mode,
      },
    }),
  })),
  listTrainingJobs: async () => mapCollection(await requestJson<TrainingJob[] | PageResult<TrainingJob>>('/training/jobs'), normalizeTraining),
  getTrainingJob: async (id: string) => normalizeTraining(await requestJson<TrainingJob>(`/training/jobs/${encodeURIComponent(id)}`)),
  stopTrainingJob: async (id: string) =>
    normalizeTraining(await requestJson<TrainingJob>(`/training/jobs/${encodeURIComponent(id)}/stop`, { method: 'POST' })),
  resumeTrainingJob: async (id: string) =>
    normalizeTraining(await requestJson<TrainingJob>(`/training/jobs/${encodeURIComponent(id)}/resume`, { method: 'POST' })),
  deleteTrainingJob: (id: string) =>
    requestJson<void>(`/training/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getTrainingMetrics: async (id: string) => normalizeTrainingMetrics(await requestJson<Record<string, any>>(`/training/jobs/${encodeURIComponent(id)}/metrics`)),
  getTrainingArtifacts: async (id: string) => {
    const raw = await requestJson<Artifact[] | PageResult<Artifact> | Record<string, unknown>>(`/training/jobs/${encodeURIComponent(id)}/artifacts`)
    return listItems<Artifact>(raw as Artifact[] | PageResult<Artifact> | Record<string, unknown>).map((artifact) => ({ ...artifact, name: artifact.name || (artifact.kind === 'best' ? 'best_model.pth' : artifact.kind === 'last' ? 'last_checkpoint.pth' : '訓練產出') }))
  },
  trainingEventsUrl: (id: string) => apiUrl(`/training/jobs/${encodeURIComponent(id)}/events`),

  listModels: async (signal?: AbortSignal) => mapCollection(await requestJson<ModelInfo[] | PageResult<ModelInfo>>('/models?limit=200', {signal}), normalizeModel),
  getModel: async (id: string) => normalizeModel(await requestJson<ModelInfo>(`/models/${encodeURIComponent(id)}`)),
  importModel: async (form: FormData) => normalizeModel(await requestJson<ModelInfo>('/models', { method: 'POST', body: form })),
  renameModel: async (id: string, name: string) => normalizeModel(await requestJson<ModelInfo>(`/models/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: jsonBody({ name }),
  })),
  activateModel: (id: string) =>
    requestJson<ModelInfo>(`/models/${encodeURIComponent(id)}/activate`, { method: 'POST' }),
  deleteModel: (id: string) => requestJson<void>(`/models/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}

export function humanApiError(error: unknown): string {
  if (error instanceof ApiClientError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '發生未預期錯誤，請稍後再試。'
}
