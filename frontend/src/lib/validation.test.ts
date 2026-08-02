import { describe, expect, it } from 'vitest'
import { validateSettings, validateTrainingConfig } from './validation'
import { DEFAULT_SETTINGS, type TrainingConfig } from '../types/api'

const validTraining: TrainingConfig = {
  dataset_id: 'dataset-1', architecture: 'resnet18', mode: 'advanced', classification_mode: 'multiclass',
  batch_size: 16, epochs: 10, learning_rate: 0.0001, optimizer: 'adamw', weight_decay: 0.0001,
  scheduler: 'cosine', early_stopping: true, patience: 5, random_seed: 42,
  train_ratio: 0.7, validation_ratio: 0.15, test_ratio: 0.15,
  data_augmentation: true, class_weights: true, device: 'cpu', k_folds: 1, checkpoint_interval: 1,
}

describe('training validation', () => {
  it('accepts a complete reproducible configuration', () => {
    expect(validateTrainingConfig(validTraining)).toEqual({})
  })

  it('rejects invalid ratios and unsafe parameter ranges', () => {
    const errors = validateTrainingConfig({ ...validTraining, dataset_id: '', epochs: 0, train_ratio: 0.8, batch_size: 0 })
    expect(errors.dataset_id).toBeTruthy()
    expect(errors.epochs).toBeTruthy()
    expect(errors.batch_size).toBeTruthy()
    expect(errors.ratios).toContain('100%')
  })
})

describe('settings validation', () => {
  it('enforces backend worker and thumbnail limits', () => {
    expect(validateSettings(DEFAULT_SETTINGS)).toEqual({})
    const errors = validateSettings({ ...DEFAULT_SETTINGS, cpu_workers: 0, thumbnail_size: 20 })
    expect(errors.cpu_workers).toBeTruthy()
    expect(errors.thumbnail_size).toBeTruthy()
  })
})
