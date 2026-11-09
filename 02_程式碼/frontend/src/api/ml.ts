/** M2：訓練、模型庫、評估、特徵、草稿的資料型別。 */

export type TaskId = 'segmentation' | 'egfr' | 'grade'
export type RunStatus = 'draft' | 'queued' | 'running' | 'completed' | 'failed' | 'stopped' | 'interrupted'

export const taskLabel: Record<TaskId, string> = {
  segmentation: '分割',
  egfr: 'eGFR',
  grade: '回音分級',
}

export const runStatusLabel: Record<RunStatus, string> = {
  draft: '草稿',
  queued: '排隊中',
  running: '訓練中',
  completed: '完成',
  failed: '失敗',
  stopped: '已停止',
  interrupted: '中斷',
}

export const stageLabel: Record<string, string> = { research: '研究', candidate: '候選', clinical: '臨床上線', retired: '退役' }

/** 監控指標：分割是 Dice，eGFR 是 AUC(<60)（2／3／5 類共同的尺），分級是 QWK。 */
export const scoreLabel: Record<TaskId, string> = { segmentation: 'Dice', egfr: 'AUC(<60)', grade: 'QWK' }

/** 三區（決策 D28）：每個任務的清單頁與模型庫。 */
export const zoneHome: Record<TaskId, { training: string; models: string; label: string }> = {
  egfr: { training: '/research/egfr', models: '/research/egfr/models', label: 'eGFR 預測' },
  segmentation: { training: '/research/segmentation', models: '/research/segmentation/models', label: '分割' },
  grade: { training: '/research/grading', models: '/research/grading/models', label: '回音分級' },
}

export interface TaskInfo {
  id: TaskId
  label: string
  classes: string[]
  defaults: Record<string, unknown>
}

export interface RunInfo {
  id: string
  task: TaskId
  name: string
  experiment_id: string | null
  split_id: string
  dataset_version_id: string | null
  config: Record<string, unknown>
  status: RunStatus
  job_id: string | null
  mean_best_score: number | null
  oof: Record<string, unknown> | null
  created_by: string
  created_at: string
  finished_at: string | null
}

export interface FoldResult {
  fold: string
  best_epoch?: number | null
  best_score?: number
  epochs_run?: number
  train_images?: number
  val_images?: number
  skipped?: string
  metrics?: Record<string, unknown>
}

export interface RunDetail extends RunInfo {
  effective_config: Record<string, unknown>
  latest_evaluation?: { id: string; created_at: string; metrics: Record<string, unknown> } | null
  latest_test?: { id: string; created_at: string; created_by: string; metrics: Record<string, unknown> } | null
  summary: { folds?: FoldResult[]; oof?: Record<string, unknown>; temperature?: number; mean_best_score?: number; std_best_score?: number; data?: Record<string, unknown> }
  history: Record<string, { epoch: string; train_loss: string; val_score: string; val_loss: string; lr: string; seconds: string }[]>
}

export interface ModelInfo {
  id: string
  task: TaskId
  name: string
  version: string
  stage: string
  stage_label: string
  run_id: string | null
  metrics: { oof?: Record<string, unknown>; mean_best_score?: number; folds?: { fold: string; best_epoch: number; best_score: number }[] } | null
  architecture: { arch: string; head?: string | null; init: string } | null
  features: { feature_set_id?: string; columns: string[] } | null
  classes?: string[]
  egfr_classes?: number | null
  inputs?: string[] | null
  created_by: string
  created_at: string
  stage_history: { stage: string; by: string; at: string; approver?: string; note?: string }[]
}

export interface EvaluationInfo {
  id: string
  target: 'oof' | 'test'
  model_id: string | null
  run_id: string | null
  metrics: Record<string, unknown>
  created_by: string
  created_at: string
}

export interface FeatureSetInfo {
  id: string
  spec: { source: 'masks' | 'run' | 'mask_set'; run_id: string | null; mask_set_id?: string | null; cross_fitted: boolean; note: string }
  rows: number
  status: string
  job_id: string | null
  relpath: string
  created_by: string
  created_at: string
}

export interface DraftItem {
  mask_id: number
  image_id: string
  version: number
  source: 'legacy' | 'medsam' | 'rule' | 'model'
  review: 'needed' | 'ok'
  reasons: string[]
  labeled: string[]
  iou_vs_legacy: number | null
}

export const draftSourceLabel: Record<string, string> = { legacy: '舊程式草稿', medsam: 'MedSAM', rule: '規則（肝／脾）', model: '模型預測' }

export const modelHref = (id: string) => `/research/models/${encodeURIComponent(id)}`

// 整數（例如樣本數 n）不顯示小數
export const fmt = (v: unknown, digits = 3) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(digits)) : v == null ? '—' : String(v))

/** 指標的中文名稱（交叉驗證摘要、評估）；沒有列到的保留原名（M3 #116）。 */
export const metricLabel: Record<string, string> = {
  n: '影像數',
  k: '類別數',
  auc_lt60: 'AUC（eGFR<60）',
  auc_lt30: 'AUC（eGFR<30）',
  auc: 'AUC',
  accuracy: '準確率',
  sensitivity: '敏感度',
  specificity: '特異度',
  brier_lt60: 'Brier 分數（<60，越小越好）',
  ece_lt60: '校準誤差 ECE（<60，越小越好）',
  brier: 'Brier 分數（越小越好）',
  ece: '校準誤差 ECE（越小越好）',
  ece_before_calibration: '校準前的 ECE（對照用）',
  brier_before_calibration: '校準前的 Brier（對照用）',
  qwk: 'QWK（有序一致性）',
  mae: '平均差幾類',
  macro_f1: 'Macro F1',
  dice_mean: '平均 Dice',
  dice_parenchyma: 'Dice（腎實質）',
  dice_sinus: 'Dice（腎竇）',
  dice_liver: 'Dice（肝）',
  dice_spleen: 'Dice（脾）',
}

const configLabel: Record<string, string> = {
  task: '任務',
  arch: '架構',
  init: '初始化',
  head: '輸出層',
  egfr_classes: 'eGFR 類別數',
  inputs: '輸入方式',
  img_size: '影像大小（px）',
  epochs: 'Epoch 上限',
  batch_size: 'Batch size',
  accum_steps: '梯度累積步數',
  lr: '學習率',
  weight_decay: '權重衰減',
  patience: '提早停止的耐心（epoch）',
  seed: '亂數種子',
  device: '裝置',
  amp: '混合精度',
  num_workers: '讀資料的工作數',
  max_images: '最多影像數（測試用）',
  folds: '只訓練這些折',
  features: '表格特徵',
  flip: '水平翻轉',
  mask_policy: '遮罩來源',
  mask_set_id: '遮罩組',
  roi_mm: '裁切大小（mm）',
  framework: '框架',
}
const valueLabel: Record<string, string> = {
  imagenet: 'ImageNet 預訓練',
  random: '隨機',
  binary: '二元',
  corn: 'CORN（有序）',
  coral: 'CORAL（有序）',
  sord: 'SORD（軟標籤）',
  ce: '一般 CE',
  auto: '自動（有顯示卡就用）',
  verified: '只用確認過的遮罩',
  logreg: '有序邏輯迴歸（基準）',
  image: '影像',
  clinical: '臨床資料',
  measures: '遮罩量測',
  mask_channels: '遮罩通道',
  egfr: 'eGFR',
  segmentation: '分割',
  grade: '回音分級',
}

/** 訓練設定轉成給人看的「名稱、值」列；不顯示 JSON 與英文代號。 */
export function configRows(cfg: Record<string, unknown>): [string, string][] {
  const show = (v: unknown): string => {
    if (v == null) return '—'
    if (typeof v === 'boolean') return v ? '是' : '否'
    if (Array.isArray(v)) return v.map(show).join('、') || '—'
    if (typeof v === 'object') {
      const o = v as Record<string, unknown>
      return o.feature_set_id ? `特徵集 ${String(o.feature_set_id)}（${Array.isArray(o.columns) ? o.columns.length : 0} 欄）` : '有'
    }
    return valueLabel[String(v)] ?? String(v)
  }
  return Object.entries(cfg).map(([k, v]) => [configLabel[k] ?? k, show(v)])
}
