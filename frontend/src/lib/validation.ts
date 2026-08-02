import type { SystemSettings, TrainingConfig } from '../types/api'

export interface ValidationErrors {
  [field: string]: string
}

export function validateTrainingConfig(config: TrainingConfig): ValidationErrors {
  const errors: ValidationErrors = {}
  if (!config.dataset_id) errors.dataset_id = '請先選擇資料集。'
  if (!Number.isInteger(config.epochs) || config.epochs < 1 || config.epochs > 1000) errors.epochs = 'Epochs 必須為 1 到 1000 的整數。'
  if (!Number.isInteger(config.batch_size) || config.batch_size < 1 || config.batch_size > 512) errors.batch_size = 'Batch size 必須為 1 到 512 的整數。'
  if (!(config.learning_rate > 0 && config.learning_rate <= 1)) errors.learning_rate = 'Learning rate 必須大於 0 且不超過 1。'
  if (config.weight_decay < 0 || config.weight_decay > 1) errors.weight_decay = 'Weight decay 必須介於 0 與 1。'
  if (!Number.isInteger(config.random_seed) || config.random_seed < 0) errors.random_seed = 'Random seed 必須為非負整數。'
  if (config.early_stopping && (!Number.isInteger(config.patience) || config.patience < 1)) errors.patience = '啟用 Early stopping 時，patience 至少為 1。'
  const ratio = config.train_ratio + config.validation_ratio + config.test_ratio
  if (Math.abs(ratio - 1) > 0.001) errors.ratios = '訓練、驗證與測試比例總和必須為 100%。'
  if ([config.train_ratio, config.validation_ratio, config.test_ratio].some((value) => value < 0 || value > 1)) errors.ratios = '各資料切割比例必須介於 0% 與 100%。'
  if (!Number.isInteger(config.k_folds) || config.k_folds < 1 || config.k_folds > 20) errors.k_folds = 'K-fold 必須為 1 到 20。'
  if (!Number.isInteger(config.checkpoint_interval) || config.checkpoint_interval < 1) errors.checkpoint_interval = 'Checkpoint 間隔至少為 1 個 epoch。'
  return errors
}

export function validateSettings(settings: SystemSettings): ValidationErrors {
  const errors: ValidationErrors = {}
  if (!Number.isInteger(settings.cpu_workers) || settings.cpu_workers < 1 || settings.cpu_workers > 32) errors.cpu_workers = 'CPU 同時工作數必須為 1 到 32。'
  if (!Number.isInteger(settings.default_seed)) errors.default_seed = 'Random seed 必須為整數。'
  if (!Number.isInteger(settings.thumbnail_size) || settings.thumbnail_size < 64 || settings.thumbnail_size > 1024) errors.thumbnail_size = '縮圖尺寸必須介於 64 與 1024 px。'
  return errors
}
