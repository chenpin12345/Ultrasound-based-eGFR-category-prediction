import { Cpu, Database, HardDrive, Save, Server, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, InlineNotice, PageHeader, StatePanel, StatCard, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api, humanApiError } from '../lib/api'
import { formatBytes } from '../lib/format'
import { validateSettings } from '../lib/validation'
import { DEFAULT_SETTINGS, type SystemSettings } from '../types/api'

function SettingNumber({ label, value, onChange, min, max, error, help }: { label: string; value: number; onChange: (value: number) => void; min: number; max: number; error?: string; help?: string }) {
  return <label><span className="label">{label}</span><input className={`field ${error ? 'border-rose-400' : ''}`} type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} />{help && <span className="help block">{help}</span>}{error && <span className="error-text block">{error}</span>}</label>
}

export function SettingsPage() {
  const loadSettings = useCallback(() => api.getSettings(), [])
  const loadInfo = useCallback(() => api.systemInfo(), [])
  const loadHealth = useCallback(() => api.health(), [])
  const remote = useAsyncResource(loadSettings)
  const info = useAsyncResource(loadInfo)
  const health = useAsyncResource(loadHealth)
  const [settings, setSettings] = useState<SystemSettings>(DEFAULT_SETTINGS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [dirty, setDirty] = useState(false)
  useEffect(() => { if (remote.data && !dirty) setSettings({ ...DEFAULT_SETTINGS, ...remote.data }) }, [remote.data, dirty])
  const errors = useMemo(() => validateSettings(settings), [settings])
  const update = <K extends keyof SystemSettings>(key: K, value: SystemSettings[K]) => { setSettings((current) => ({ ...current, [key]: value })); setDirty(true); setSaved(false) }

  const save = async () => {
    if (Object.keys(errors).length) return
    setBusy(true); setError(null); setSaved(false)
    try {
      const updated = await api.updateSettings(settings)
      setSettings({ ...DEFAULT_SETTINGS, ...updated })
      remote.setData(updated)
      setDirty(false)
      setSaved(true)
    } catch (reason) { setError(humanApiError(reason)) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="系統設定" description="設定本機背景工作、GPU 使用、重現性與縮圖大小。所有設定只保存在本機 SQLite，不啟用雲端或追蹤服務。" />
      <StatePanel loading={remote.loading || info.loading} error={remote.error || info.error} onRetry={() => { void remote.refresh(); void info.refresh() }} empty={false}>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="API 服務" value={health.data?.status || '—'} hint={health.data?.database ? `SQLite ${health.data.database}` : '本機服務'} icon={<Server className="h-5 w-5" />} />
          <StatCard label="Python" value={info.data?.python_version || '—'} hint={info.data?.platform || '本機執行環境'} icon={<Cpu className="h-5 w-5" />} />
          <StatCard label="CUDA" value={info.data?.cuda_available ? '可使用' : '不可使用'} hint={info.data?.gpu_name || '預設仍可使用 CPU'} icon={<HardDrive className="h-5 w-5" />} />
          <StatCard label="系統記憶體" value={formatBytes(info.data?.memory_total_bytes)} hint={`${info.data?.cpu_count || '—'} 個 CPU 核心`} icon={<Database className="h-5 w-5" />} />
        </div>
        {saved && <div className="mt-4"><SuccessMessage>系統設定已保存。</SuccessMessage></div>}
        {error && <div className="mt-4"><InlineNotice tone="danger">{error}</InlineNotice></div>}
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <Card className="p-5 sm:p-6"><h2 className="section-title">介面與背景工作</h2><div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label><span className="label">介面語言</span><select className="field" value={settings.language} onChange={(event) => update('language', event.target.value as SystemSettings['language'])}><option value="zh-TW">繁體中文</option><option value="en">English</option></select><span className="help block">目前主要研究流程以繁體中文呈現。</span></label>
            <SettingNumber label="CPU 同時工作數" value={settings.cpu_workers} onChange={(value) => update('cpu_workers', value)} min={1} max={32} error={errors.cpu_workers} help="建議 1–2，避免耗盡記憶體。" />
            <SettingNumber label="預設 random seed" value={settings.default_seed} onChange={(value) => update('default_seed', value)} min={-2147483648} max={2147483647} error={errors.default_seed} help="新資料切割與訓練表單的重現性基準。" />
            <SettingNumber label="縮圖尺寸（px）" value={settings.thumbnail_size} onChange={(value) => update('thumbnail_size', value)} min={64} max={1024} error={errors.thumbnail_size} help="較大縮圖會使用更多磁碟與記憶體。" />
          </div></Card>
          <Card className="p-5 sm:p-6"><h2 className="section-title">GPU 與本機隱私</h2><label className="mt-4 flex items-start gap-3 rounded-xl border border-slate-200 p-4"><input className="mt-0.5 h-5 w-5 rounded text-clinical-600" type="checkbox" checked={settings.gpu_enabled} disabled={!info.data?.cuda_available} onChange={(event) => update('gpu_enabled', event.target.checked)} /><span><span className="block text-sm font-semibold">允許使用 CUDA GPU</span><span className="mt-1 block text-xs leading-5 text-slate-500">{info.data?.cuda_available ? `已偵測 ${info.data.gpu_name || 'CUDA 裝置'}；GPU 工作仍由後端限制為單一佇列。` : '目前環境未偵測到 CUDA，因此此設定保持停用；CPU 功能不受影響。'}</span></span></label><div className="mt-4 rounded-xl bg-clinical-50 p-4 text-sm leading-6 text-clinical-900"><p className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4" />固定隱私原則</p><ul className="mt-2 list-disc pl-5"><li>資料、模型與結果不自動上傳。</li><li>不使用第三方分析或追蹤。</li><li>介面不顯示伺服器絕對路徑或 traceback。</li></ul></div></Card>
          <Card className="p-5 sm:p-6 xl:col-span-2"><h2 className="section-title">安全限制由安裝環境管理</h2><p className="mt-2 text-sm leading-6 text-slate-600">單檔大小、ZIP 解壓縮大小、檔案數量與工作目錄根路徑屬於服務啟動前的安全邊界，由 `.env` 與後端設定管理，因此不提供瀏覽器內變更。這可避免一般頁面意外放寬醫療資料保護限制。</p><div className="mt-3"><InlineNotice tone="info">後端會驗證真實圖片格式、路徑穿越、ZIP Slip、符號連結、壓縮比與總大小；前端檢查不取代伺服器安全驗證。</InlineNotice></div></Card>
        </div>
        <div className="mt-6 flex justify-end"><button className="btn-primary min-w-40" disabled={busy || Object.keys(errors).length > 0} onClick={() => void save()}><Save className="h-4 w-4" />{busy ? '儲存中…' : '儲存設定'}</button></div>
      </StatePanel>
    </div>
  )
}
