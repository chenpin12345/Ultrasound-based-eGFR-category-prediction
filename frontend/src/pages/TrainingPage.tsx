import { AlertTriangle, BrainCircuit, CheckCircle2, Cpu, Gauge, Play, SlidersHorizontal, Zap } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, InlineNotice, PageHeader, StatePanel } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api, humanApiError, listItems } from '../lib/api'
import { distributionItems, jobIdOf } from '../lib/format'
import { validateTrainingConfig } from '../lib/validation'
import type { Dataset, TrainingConfig } from '../types/api'

const DEFAULT_CONFIG: TrainingConfig = {
  dataset_id: '', architecture: 'resnet18', mode: 'quick', classification_mode: 'multiclass',
  batch_size: 16, epochs: 20, learning_rate: 0.0001, optimizer: 'adamw', weight_decay: 0.0001,
  scheduler: 'cosine', early_stopping: true, patience: 7, random_seed: 42,
  train_ratio: 0.7, validation_ratio: 0.15, test_ratio: 0.15, data_augmentation: true,
  class_weights: true, device: 'auto', k_folds: 1, checkpoint_interval: 1,
}

function NumberField({ label, value, onChange, min, max, step = 1, error, help }: { label: string; value: number; onChange: (value: number) => void; min?: number; max?: number; step?: number; error?: string; help?: string }) {
  return <label><span className="label">{label}</span><input className={`field ${error ? 'border-rose-400' : ''}`} type="number" value={value} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} />{help && <span className="help block">{help}</span>}{error && <span className="error-text block">{error}</span>}</label>
}

export function TrainingPage() {
  const navigate = useNavigate()
  const loadDatasets = useCallback(async () => listItems<Dataset>(await api.listDatasets()), [])
  const datasets = useAsyncResource(loadDatasets)
  const [config, setConfig] = useState<TrainingConfig>(DEFAULT_CONFIG)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedDataset = datasets.data?.find((item) => item.id === config.dataset_id)
  const summaryLoader = useCallback(() => api.getDatasetSummary(config.dataset_id), [config.dataset_id])
  const summary = useAsyncResource(summaryLoader, Boolean(config.dataset_id))

  useEffect(() => {
    if (!config.dataset_id && datasets.data?.length) setConfig((current) => ({ ...current, dataset_id: datasets.data![0].id }))
  }, [config.dataset_id, datasets.data])

  const update = <K extends keyof TrainingConfig>(key: K, value: TrainingConfig[K]) => setConfig((current) => ({ ...current, [key]: value }))
  const validation = useMemo(() => validateTrainingConfig(config), [config])
  const startTraining = async () => {
    const currentErrors = validateTrainingConfig(config)
    setErrors(currentErrors)
    if (Object.keys(currentErrors).length) return
    setBusy(true); setError(null)
    try {
      const created = await api.createTrainingJob({ ...config, name: config.name?.trim() || `${selectedDataset?.name || '資料集'} · ${config.architecture}` })
      navigate(`/training/${jobIdOf(created)}`)
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  const setMode = (mode: 'quick' | 'advanced') => {
    if (mode === 'quick') setConfig((current) => ({ ...DEFAULT_CONFIG, dataset_id: current.dataset_id, architecture: current.architecture, epochs: current.epochs, mode }))
    else update('mode', mode)
    setErrors({})
  }

  const distribution = distributionItems(summary.data)
  return (
    <div>
      <PageHeader title="模型訓練" description="快速模式只需選擇資料集、架構與 epochs；進階模式可完整控制分類、資源、切割及 checkpoint。送出後立即返回工作 ID。" />
      <div className="mb-6 grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm sm:max-w-lg">
        <button className={`flex min-h-12 items-center justify-center gap-2 rounded-xl text-sm font-semibold transition ${config.mode === 'quick' ? 'bg-clinical-700 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-50'}`} onClick={() => setMode('quick')}><Zap className="h-4 w-4" />快速模式</button>
        <button className={`flex min-h-12 items-center justify-center gap-2 rounded-xl text-sm font-semibold transition ${config.mode === 'advanced' ? 'bg-clinical-700 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-50'}`} onClick={() => setMode('advanced')}><SlidersHorizontal className="h-4 w-4" />進階模式</button>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.2fr_.8fr]">
        <Card className="p-5 sm:p-6">
          <div className="flex items-center gap-2"><BrainCircuit className="h-5 w-5 text-clinical-600" /><h2 className="section-title">訓練設定</h2></div>
          <StatePanel loading={datasets.loading} error={datasets.error} onRetry={() => void datasets.refresh()} empty={!datasets.data?.length} emptyTitle="目前沒有可訓練的資料集" emptyDescription="請先到資料集管理匯入並完成驗證。">
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="sm:col-span-2"><span className="label">資料集</span><select className={`field ${errors.dataset_id ? 'border-rose-400' : ''}`} value={config.dataset_id} onChange={(event) => update('dataset_id', event.target.value)}>{datasets.data?.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.image_count ?? dataset.sample_count ?? 0} 張</option>)}</select>{errors.dataset_id && <span className="error-text block">{errors.dataset_id}</span>}</label>
              <label><span className="label">模型架構</span><select className="field" value={config.architecture} onChange={(event) => update('architecture', event.target.value as TrainingConfig['architecture'])}><option value="resnet18">ResNet18</option><option value="mobilenet_v2">MobileNetV2</option><option value="efficientnet_b3">EfficientNetB3</option><option value="mlp_resnet18">MLP-ResNet18</option></select></label>
              <NumberField label="Epochs" value={config.epochs} min={1} max={1000} onChange={(value) => update('epochs', value)} error={errors.epochs} />
              <label className="sm:col-span-2"><span className="label">工作名稱（選填）</span><input className="field" value={config.name || ''} onChange={(event) => update('name', event.target.value)} placeholder={`${selectedDataset?.name || '資料集'} · ${config.architecture}`} /></label>
            </div>
            {config.architecture === 'mlp_resnet18' && <div className="mt-4"><InlineNotice tone="warning">MLP-ResNet18 需要完整 metadata 與既有欄位順序；送出前後端會再次驗證缺漏。</InlineNotice></div>}

            {config.mode === 'advanced' && <div className="mt-6 space-y-6 border-t border-slate-200 pt-6">
              <div><h3 className="text-sm font-bold text-slate-800">模型與最佳化</h3><div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <label><span className="label">分類模式</span><select className="field" value={config.classification_mode} onChange={(event) => update('classification_mode', event.target.value as TrainingConfig['classification_mode'])}><option value="multiclass">一般多類別</option><option value="coral">CORAL／序位分類</option></select></label>
                <NumberField label="Batch size" value={config.batch_size} min={1} max={512} onChange={(value) => update('batch_size', value)} error={errors.batch_size} />
                <NumberField label="Learning rate" value={config.learning_rate} min={0.0000001} max={1} step={0.00001} onChange={(value) => update('learning_rate', value)} error={errors.learning_rate} />
                <label><span className="label">Optimizer</span><select className="field" value={config.optimizer} onChange={(event) => update('optimizer', event.target.value as TrainingConfig['optimizer'])}><option value="adamw">AdamW</option><option value="adam">Adam</option><option value="sgd">SGD</option></select></label>
                <NumberField label="Weight decay" value={config.weight_decay} min={0} max={1} step={0.0001} onChange={(value) => update('weight_decay', value)} error={errors.weight_decay} />
                <label><span className="label">Scheduler</span><select className="field" value={config.scheduler} onChange={(event) => update('scheduler', event.target.value as TrainingConfig['scheduler'])}><option value="cosine">Cosine annealing</option><option value="plateau">Reduce on plateau</option><option value="step">Step LR</option><option value="none">不使用</option></select></label>
              </div></div>
              <div><h3 className="text-sm font-bold text-slate-800">資料切割與重現性</h3><div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <NumberField label="Training %" value={Math.round(config.train_ratio * 100)} min={0} max={100} onChange={(value) => update('train_ratio', value / 100)} error={errors.ratios} />
                <NumberField label="Validation %" value={Math.round(config.validation_ratio * 100)} min={0} max={100} onChange={(value) => update('validation_ratio', value / 100)} />
                <NumberField label="Test %" value={Math.round(config.test_ratio * 100)} min={0} max={100} onChange={(value) => update('test_ratio', value / 100)} />
                <NumberField label="Random seed" value={config.random_seed} min={0} onChange={(value) => update('random_seed', value)} error={errors.random_seed} />
                <NumberField label="K-fold" value={config.k_folds} min={1} max={20} onChange={(value) => update('k_folds', value)} error={errors.k_folds} help="1 表示一般 train/validation/test 切割。" />
                <NumberField label="Checkpoint 間隔" value={config.checkpoint_interval} min={1} onChange={(value) => update('checkpoint_interval', value)} error={errors.checkpoint_interval} help="每幾個 epoch 保存一次。" />
              </div></div>
              <div><h3 className="text-sm font-bold text-slate-800">可靠性與資源</h3><div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <label><span className="label">運算裝置</span><select className="field" value={config.device} onChange={(event) => update('device', event.target.value as TrainingConfig['device'])}><option value="auto">自動選擇</option><option value="cpu">CPU</option><option value="cuda">CUDA</option></select></label>
                <NumberField label="Early stopping patience" value={config.patience} min={1} max={100} onChange={(value) => update('patience', value)} error={errors.patience} />
              </div><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="flex items-start gap-3 rounded-xl border border-slate-200 p-3"><input className="mt-0.5 h-5 w-5 rounded text-clinical-600" type="checkbox" checked={config.early_stopping} onChange={(event) => update('early_stopping', event.target.checked)} /><span><span className="block text-sm font-semibold">Early stopping</span><span className="text-xs text-slate-500">驗證指標未改善時安全停止。</span></span></label><label className="flex items-start gap-3 rounded-xl border border-slate-200 p-3"><input className="mt-0.5 h-5 w-5 rounded text-clinical-600" type="checkbox" checked={config.data_augmentation} onChange={(event) => update('data_augmentation', event.target.checked)} /><span><span className="block text-sm font-semibold">Data augmentation</span><span className="text-xs text-slate-500">啟用經驗證的影像增強。</span></span></label><label className="flex items-start gap-3 rounded-xl border border-slate-200 p-3"><input className="mt-0.5 h-5 w-5 rounded text-clinical-600" type="checkbox" checked={config.class_weights} onChange={(event) => update('class_weights', event.target.checked)} /><span><span className="block text-sm font-semibold">Class weights</span><span className="text-xs text-slate-500">降低類別不平衡影響。</span></span></label></div></div>
            </div>}
          </StatePanel>
        </Card>

        <div className="space-y-6">
          <Card className="p-5 sm:p-6"><h2 className="section-title">訓練前摘要</h2><StatePanel loading={summary.loading} error={summary.error} onRetry={() => void summary.refresh()} empty={!config.dataset_id} emptyTitle="請選擇資料集" emptyDescription="選擇後會顯示可訓練性摘要。"><div className="mt-4 space-y-3"><div className="grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">資料集</p><p className="mt-1 truncate font-semibold">{selectedDataset?.name || '—'}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">圖片總數</p><p className="mt-1 font-semibold">{summary.data?.image_count ?? summary.data?.total_samples ?? 0}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">架構／模式</p><p className="mt-1 text-sm font-semibold">{config.architecture} · {config.classification_mode}</p></div><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">裝置</p><p className="mt-1 flex items-center gap-1.5 text-sm font-semibold"><Cpu className="h-4 w-4" />{config.device.toUpperCase()}</p></div></div>
              <div className="rounded-xl border border-slate-200 p-3"><p className="text-xs font-semibold text-slate-500">分類筆數</p><div className="mt-2 space-y-2">{distribution.map((item) => <div key={item.class_name} className="flex items-center justify-between text-sm"><span>{item.class_name}</span><span className="font-semibold">{item.count}</span></div>)}</div></div>
              {summary.data?.warnings?.length ? <InlineNotice tone="warning" title="訓練前提醒"><ul className="list-disc pl-5">{summary.data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></InlineNotice> : <InlineNotice tone="success"><span className="inline-flex items-center gap-2"><CheckCircle2 className="h-4 w-4" />未發現資料摘要警告；後端仍會執行完整驗證。</span></InlineNotice>}
              {summary.data?.is_imbalanced && <InlineNotice tone="warning"><span className="inline-flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />資料類別不平衡，建議保留 class weights。</span></InlineNotice>}
            </div></StatePanel></Card>
          <Card className="p-5 sm:p-6"><div className="flex items-center gap-2"><Gauge className="h-5 w-5 text-clinical-600" /><h2 className="section-title">送出訓練</h2></div><p className="mt-2 text-sm leading-6 text-slate-500">送出後 HTTP 請求會立即返回，訓練留在背景執行。請勿重複點擊；後端亦應以設定指紋避免重複工作。</p>{Object.keys(validation).length > 0 && <div className="mt-4"><InlineNotice tone="warning">尚有 {Object.keys(validation).length} 項設定需要修正。</InlineNotice></div>}{error && <div className="mt-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}<button className="btn-primary mt-5 w-full" disabled={!datasets.data?.length || busy || Object.keys(validation).length > 0} onClick={() => void startTraining()}><Play className="h-4 w-4" />{busy ? '建立訓練工作中…' : '開始訓練'}</button></Card>
        </div>
      </div>
    </div>
  )
}
