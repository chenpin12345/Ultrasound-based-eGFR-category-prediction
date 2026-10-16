export type JobStatus =
  | 'queued'
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'failed'
  | 'interrupted'
  | 'cancelled'
  | 'pending'

export type JobKind = 'process' | 'mask' | 'features' | 'inference' | 'quick_analysis' | 'training'

export interface ApiMeta {
  request_id?: string
  total?: number
  page?: number
  page_size?: number
  [key: string]: unknown
}

export interface ApiEnvelope<T> {
  data: T
  meta?: ApiMeta
}

export interface ApiErrorDetail {
  field?: string
  message?: string
  [key: string]: unknown
}

export interface ApiErrorBody {
  code?: string
  message?: string
  details?: ApiErrorDetail[] | Record<string, unknown> | string
  request_id?: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

export interface Dataset {
  id: string
  name: string
  version?: string
  status?: string
  created_at?: string
  updated_at?: string
  size_bytes?: number
  total_bytes?: number
  image_count?: number
  sample_count?: number
  train_count?: number
  validation_count?: number
  val_count?: number
  test_count?: number
  warning_count?: number
}

export interface ClassDistributionItem {
  class_index?: number
  class_name: string
  count: number
  percentage?: number
}

export interface DatasetSummary {
  dataset_id?: string
  image_count?: number
  total_samples?: number
  total_size_bytes?: number
  split_counts?: Record<string, number>
  class_distribution?: ClassDistributionItem[] | Record<string, number>
  corrupt_count?: number
  duplicate_count?: number
  missing_label_count?: number
  missing_metadata_count?: number
  missing_mask_count?: number
  is_imbalanced?: boolean
  warnings?: string[]
  sample_count?: number
  total_bytes?: number
  classes?: Record<string, number>
  splits?: Record<string, number>
  folds?: Record<string, number>
  unlabeled?: number
  duplicates?: number
}

export interface DatasetSample {
  id: string
  file_name?: string
  display_name?: string
  thumbnail_url?: string
  preview_url?: string
  size_bytes?: number
  mime_type?: string
  width?: number
  height?: number
  class_index?: number
  class_name?: string
  split?: string
  fold?: number
  status?: string
  is_corrupt?: boolean
  is_duplicate?: boolean
  missing_label?: boolean
  missing_metadata?: boolean
  has_mask?: boolean
  missing_mask?: boolean
  mask_url?: string
  metadata?: Record<string, unknown>
}

export interface DatasetImportIssue {
  id: string
  dataset_id: string
  display_name: string
  issue_type: string
  error_code: string
  message: string
  sha256?: string
  size_bytes: number
  created_at: string
}

export interface Job {
  id: string
  job_id?: string
  name?: string
  kind?: JobKind | string
  status: JobStatus
  progress?: number
  current_step?: string
  message?: string
  created_at?: string
  started_at?: string
  finished_at?: string
  updated_at?: string
  error_code?: string
  error_message?: string
  result_count?: number
  download_url?: string
  config?: Record<string, unknown>
}

export interface JobEvent {
  id?: string
  sequence?: number
  type?: string
  status?: JobStatus
  progress?: number
  message?: string
  timestamp?: string
  created_at?: string
  payload?: Record<string, unknown>
}

export interface TrainingConfig {
  dataset_id: string
  name?: string
  architecture: 'resnet18' | 'mobilenet_v2' | 'efficientnet_b3' | 'mlp_resnet18'
  mode: 'quick' | 'advanced'
  classification_mode: 'multiclass' | 'coral'
  batch_size: number
  epochs: number
  learning_rate: number
  optimizer: 'adamw' | 'adam' | 'sgd'
  weight_decay: number
  scheduler: 'cosine' | 'plateau' | 'step' | 'none'
  early_stopping: boolean
  patience: number
  random_seed: number
  train_ratio: number
  validation_ratio: number
  test_ratio: number
  data_augmentation: boolean
  class_weights: boolean
  device: 'cpu' | 'cuda' | 'auto'
  k_folds: number
  checkpoint_interval: number
  resume_from?: string
}

export interface TrainingJob extends Job {
  training_job_id?: string
  dataset_id?: string
  dataset_name?: string
  architecture?: string
  classification_mode?: string
  current_epoch?: number
  total_epochs?: number
  current_batch?: number
  total_batches?: number
  elapsed_seconds?: number
  estimated_remaining_seconds?: number
  best_epoch?: number
  best_validation_loss?: number
  latest_checkpoint?: string
  stop_requested?: boolean
  device?: string
}

export interface EpochMetric {
  epoch: number
  train_loss?: number
  validation_loss?: number
  val_loss?: number
  train_accuracy?: number
  validation_accuracy?: number
  val_accuracy?: number
  test_accuracy?: number
  learning_rate?: number
  precision?: number
  recall?: number
  f1_score?: number
  elapsed_seconds?: number
  class_metrics?: Record<string, { precision?: number; recall?: number; f1_score?: number }>
  confusion_matrix?: number[][]
}

export interface ResourceSnapshot {
  cpu_percent?: number
  memory_percent?: number
  gpu_name?: string
  gpu_percent?: number
  gpu_memory_percent?: number
  gpu_memory_used_mb?: number
  gpu_memory_total_mb?: number
}

export interface TrainingMetrics {
  items?: EpochMetric[]
  history?: EpochMetric[]
  latest?: EpochMetric
  resources?: ResourceSnapshot
  confusion_matrix?: number[][]
  logs?: TrainingLogEntry[]
}

export interface TrainingLogEntry {
  id?: string | number
  level?: string
  message: string
  timestamp?: string
}

export interface ModelEvaluationSummary {
  selection:'latest_created_not_best';evaluation_id:string|null;status:string;reason:string|null
  weight_sha256:string|null;configuration_sha256:string|null;dataset_id:string|null;dataset_name:string|null
  split:string|null;scope:string|null;sample_count:number|null;evaluated_sample_count:number|null
  completed_at:string|null;metric_version:string|null;unit:'fraction';metrics:Record<string,number|null>
}

export interface ModelInfo {
  id: string
  model_id?: string
  class_count?: number
  name: string
  architecture?: string
  source?: 'external' | 'training' | string
  status?: string
  version?: string
  created_at?: string
  size_bytes?: number
  is_active?: boolean
  is_default?: boolean
  active?: boolean
  task?: 'classification' | 'segmentation' | string
  source_training_job_id?: string
  classification_mode?: string
  class_names?: string[] | Record<string, string>
  download_url?: string
  evaluation_summary?: ModelEvaluationSummary
}

export interface CheckpointSource {
  status: 'verified_record' | 'unverified'
  reason: string
  sha256?: string
  sample_count?: number
  samples_sha256?: string
  split_counts?: Record<string, number>
  selection?: {metric: string; direction: string; best_epoch: number; value: number; selected_fold: number | null}
  best_epoch_record?: {epoch: number; metrics: Record<string, unknown>}
  last_epoch_record?: {epoch: number; metrics: Record<string, unknown>}
  cross_validation?: Record<string, unknown> | null
}

export interface ModelDetail extends ModelInfo {
  sha256: string
  metadata_columns: string[]
  preprocessing: Record<string, unknown>
  configuration: { status: 'consistent' | 'unverified'; reason: string | null; sha256: string | null; train_stats: Record<string, Record<string, number>> | null }
  class_schema: { version: string; task: string; class_count: number; class_names: string[]; sha256: string; status: string }
  source_info: { kind: 'local_training' | 'imported'; status: 'unverified' | 'verified_record'; reason: string; training_job_id: string | null }
  training_record: { job_id: string; training_job_id: string; status: string; selection_metric: 'validation_loss'; selection_direction: 'minimize'; recorded_best_validation_loss: number | null; completed_epoch: number; note: string; checkpoint_source?: CheckpointSource } | null
  references: { kind: 'default' | 'research_job' | 'clinical_plan' | 'evaluation'; id: string; name: string; status: string }[]
}

export interface InferenceProbability {
  class_index?: number
  class_name: string
  probability: number
}

export interface InferenceResult {
  processed_url?: string
  mask_url?: string
  overlay_url?: string
  metadata?: Record<string, string | number>
  id?: string
  file_name: string
  thumbnail_url?: string
  predicted_class: string
  predicted_index?: number
  confidence: number
  probabilities: InferenceProbability[] | Record<string, number>
  error?: string
}

export interface JobResults {
  total?: number
  offset?: number
  limit?: number
  analysis_mode?: 'mlp' | 'image_only'
  class_count?: number
  class_names?: string[]
  model?: { id: string; name?: string; sha256: string; class_count: number }
  evaluation?: { class_count: number; class_names: string[]; confusion_matrix: number[][]; sample_count: number; dataset_id: string | null; scope: string }
  job_id?: string
  results?: InferenceResult[]
  items?: InferenceResult[]
  statistics?: Record<string, number>
  missing_masks?: string[]
  missing_metadata?: string[]
  missing_features?: string[]
  mask_previews?: Array<{
    name: string
    source_url: string
    mask_url: string
  }>
  artifacts?: Artifact[]
}

export interface Artifact {
  id?: string
  name: string
  kind?: string
  size_bytes?: number
  download_url?: string
  created_at?: string
}

export interface SystemInfo {
  app_name?: string
  version?: string
  python_version?: string
  torch_version?: string
  platform?: string
  cpu_count?: number
  memory_total_bytes?: number
  cuda_available?: boolean
  gpu_name?: string
  model_count?: number
}

export interface HealthInfo {
  status: string
  database?: string
  version?: string
  timestamp?: string
}

export interface SystemSettings {
  language: 'zh-TW' | 'en'
  cpu_workers: number
  gpu_enabled: boolean
  default_seed: number
  thumbnail_size: number
}

export const DEFAULT_SETTINGS: SystemSettings = {
  language: 'zh-TW',
  cpu_workers: 2,
  gpu_enabled: true,
  default_seed: 42,
  thumbnail_size: 384,
}
