import { AlertTriangle, Download, FileSpreadsheet, Filter, FolderOpen, RefreshCw, Search, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Dropzone } from '../components/Dropzone'
import { DatasetGallery } from '../components/DatasetGallery'
import { Card, InlineNotice, PageHeader, StatePanel, StatusBadge, SuccessMessage } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api, humanApiError, listItems } from '../lib/api'
import { distributionItems, formatBytes, formatDate } from '../lib/format'
import type { Dataset, DatasetImportIssue, DatasetSample } from '../types/api'

const chartColors = ['#ef7d79', '#e3a740', '#53a6b5', '#4085b6', '#2d9184']

export function DatasetsPage() {
  const loadDatasets = useCallback(async (signal?: AbortSignal) => listItems<Dataset>(await api.listDatasets(signal)), [])
  const datasets = useAsyncResource(loadDatasets, true, 'datasets')
  const [workspaceParams, setWorkspaceParams] = useSearchParams()
  const selectedId = workspaceParams.get('dataset_id') || ''
  const setSelectedId = useCallback((id: string) => setWorkspaceParams(current => {
    const next = new URLSearchParams(current)
    next.set('dataset_id', id); next.delete('source_job'); next.delete('job_id'); next.delete('input')
    return next
  }), [setWorkspaceParams])
  const [files, setFiles] = useState<File[]>([])
  const [maskFiles, setMaskFiles] = useState<File[]>([])
  const [metadataFile, setMetadataFile] = useState<File>()
  const [datasetName, setDatasetName] = useState('')
  const [uploadBusy, setUploadBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Dataset>()
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const [splitFilter, setSplitFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    if (!selectedId && datasets.data?.length) setSelectedId(datasets.data[0].id)
  }, [datasets.data, selectedId, setSelectedId])

  useEffect(() => setOffset(0), [selectedId, search, classFilter, splitFilter, statusFilter])

  const summaryLoader = useCallback((signal?: AbortSignal) => api.getDatasetSummary(selectedId, signal), [selectedId])
  const summary = useAsyncResource(summaryLoader, Boolean(selectedId), `dataset-summary:${selectedId}`)
  const query = useMemo(() => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (classFilter) params.set('class_name', classFilter)
    if (splitFilter) params.set('split', splitFilter)
    if (statusFilter) params.set('status', statusFilter)
    params.set('page_size', '60')
    params.set('offset', String(offset))
    const value = params.toString()
    return value ? `?${value}` : ''
  }, [classFilter, search, splitFilter, statusFilter, offset])
  const samplesLoader = useCallback(async (signal?: AbortSignal) => {
    const payload = await api.getDatasetSamples(selectedId, query, signal)
    return { items: listItems<DatasetSample>(payload), total: Array.isArray(payload) ? payload.length : payload.total }
  }, [query, selectedId])
  const samplePage = useAsyncResource(samplesLoader, Boolean(selectedId), `samples:${selectedId}:${query}`)
  const samples = { ...samplePage, data: samplePage.data?.items }
  const sampleTotal = samplePage.data?.total || 0
  const issuesLoader = useCallback(async () => listItems<DatasetImportIssue>(await api.getDatasetIssues(selectedId, '?limit=100')), [selectedId])
  const issues = useAsyncResource(issuesLoader, Boolean(selectedId), `issues:${selectedId}`)
  const selected = datasets.data?.find((item) => item.id === selectedId)
  const distribution = distributionItems(summary.data)

  const uploadDataset = async () => {
    if (!datasetName.trim() || !files.length) return
    const archives = files.filter((file) => file.name.toLowerCase().endsWith('.zip'))
    if (archives.length > 1) {
      setActionError('每次只能匯入一個 ZIP；請移除多餘壓縮檔或分次建立資料集。')
      return
    }
    setUploadBusy(true)
    setActionError(null)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('name', datasetName.trim())
      files.filter((file) => !file.name.toLowerCase().endsWith('.zip')).forEach((file) => form.append('files', file))
      if (archives[0]) form.append('archive', archives[0])
      if (metadataFile) form.append('metadata', metadataFile)
      maskFiles.forEach((file) => form.append('masks', file))
      form.append('seed', '42')
      form.append('k_folds', '5')
      const created = await api.createDataset(form)
      setMessage(`資料集「${created.name || datasetName}」已建立，後端會持續驗證圖片與 metadata。`)
      setFiles([]); setMaskFiles([]); setMetadataFile(undefined); setDatasetName('')
      await datasets.refresh()
      if (created.id) setSelectedId(created.id)
    } catch (error) {
      setActionError(humanApiError(error))
    } finally {
      setUploadBusy(false)
    }
  }

  const deleteDataset = async () => {
    if (!deleteTarget) return
    setDeleteBusy(true)
    try {
      await api.deleteDataset(deleteTarget.id)
      setDeleteTarget(undefined)
      setMessage('資料集及其工作副本已安全刪除。')
      await datasets.refresh()
    } catch (error) {
      setActionError(humanApiError(error))
    } finally {
      setDeleteBusy(false)
    }
  }

  return (
    <div>
      <PageHeader title="資料集與品質" description="安全匯入圖片、ZIP 與 metadata，檢查類別分布、資料品質及切割狀態。瀏覽器不會取得伺服器絕對路徑。" actions={<button className="btn-secondary" onClick={() => { void datasets.refresh(); void summary.refresh(); void samples.refresh(); void issues.refresh() }}><RefreshCw className="h-4 w-4" />重新整理</button>} />
      <div className="space-y-6">
        <div className="space-y-6">
          <Card className="p-5">
            <details><summary className="cursor-pointer text-sm font-semibold text-ink">新增／補齊資料集</summary><h2 className="section-title mt-4">匯入新資料集</h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">接受多張圖片、資料夾或 ZIP；metadata CSV 可分開選擇。</p>
            <label className="mt-4 block"><span className="label">資料集名稱</span><input className="field" value={datasetName} onChange={(event) => setDatasetName(event.target.value)} placeholder="例如：腎臟超音波研究" disabled={uploadBusy} /></label>
            <div className="mt-4"><Dropzone files={files} onFiles={setFiles} disabled={uploadBusy} title="拖放圖片、資料夾內容或 ZIP" /></div>
            <label className="mt-3 flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:border-clinical-300 hover:bg-clinical-50"><FolderOpen className="h-4 w-4" />選擇整個圖片資料夾<input ref={(input) => input?.setAttribute('webkitdirectory', '')} className="sr-only" type="file" multiple disabled={uploadBusy} onChange={(event) => { const incoming = Array.from(event.target.files || []); setFiles((current) => { const keys = new Set(current.map((file) => `${file.name}-${file.size}-${file.lastModified}`)); return [...current, ...incoming.filter((file) => !keys.has(`${file.name}-${file.size}-${file.lastModified}`))] }); event.target.value = '' }} /></label>
            <label className="mt-4 flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 hover:border-clinical-400">
              <FileSpreadsheet className="h-5 w-5 text-clinical-600" /><span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-slate-700">{metadataFile?.name || '選擇 metadata CSV'}</span><span className="block truncate text-xs text-slate-500">{metadataFile ? formatBytes(metadataFile.size) : '支援 image_name、age、gender 等欄位'}</span></span>
              <input className="sr-only" type="file" accept=".csv,text/csv" disabled={uploadBusy} onChange={(event) => setMetadataFile(event.target.files?.[0])} />
            </label>
            <label className="mt-3 flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 hover:border-clinical-400">
              <FolderOpen className="h-5 w-5 text-clinical-600" /><span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-slate-700">{maskFiles.length ? `已選擇 ${maskFiles.length} 個 mask` : '選擇對應 masks（選填）'}</span><span className="block text-xs text-slate-500">以同檔名或 `_mask` 後綴自動配對；也可放在 ZIP 的 IMG_Mask 資料夾。</span></span>
              <input className="sr-only" type="file" accept="image/jpeg,image/png,.jfif" multiple disabled={uploadBusy} onChange={(event) => { setMaskFiles(Array.from(event.target.files || [])); event.target.value = '' }} />
            </label>
            <button className="btn-primary mt-4 w-full" disabled={!datasetName.trim() || !files.length || uploadBusy} onClick={uploadDataset}><Upload className="h-4 w-4" />{uploadBusy ? '正在匯入…' : '建立資料集'}</button>
            {!files.length && <p className="help text-center">加入至少一張圖片或一個 ZIP 後即可建立。</p>}</details>
          </Card>
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between"><h2 className="section-title">已匯入資料集</h2><span className="text-xs text-slate-500">{datasets.data?.length || 0} 個</span></div>
            <StatePanel loading={datasets.loading} error={datasets.error} onRetry={() => void datasets.refresh()} empty={!datasets.data?.length} emptyDescription="建立第一個資料集後即可查看摘要。">
              <div className="max-h-[28rem] space-y-2 overflow-y-auto">
                {datasets.data?.map((dataset) => <button key={dataset.id} className={`w-full rounded-xl border p-3 text-left transition ${selectedId === dataset.id ? 'border-clinical-400 bg-clinical-50 ring-1 ring-clinical-200' : 'border-slate-200 hover:bg-slate-50'}`} onClick={() => setSelectedId(dataset.id)}><div className="flex items-start justify-between gap-2"><p className="min-w-0 truncate text-sm font-semibold text-slate-800">{dataset.name}</p><StatusBadge status={dataset.status || 'ready'} /></div><p className="mt-1 text-xs text-slate-500">{dataset.image_count ?? dataset.sample_count ?? 0} 張 · {formatDate(dataset.created_at)}</p></button>)}
              </div>
            </StatePanel>
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          {message && <SuccessMessage>{message}</SuccessMessage>}
          {actionError && <InlineNotice tone="danger">{actionError}</InlineNotice>}
          <StatePanel loading={datasets.loading} error={datasets.error} empty={!selected} emptyTitle="選擇一個資料集" emptyDescription="從上方清單選擇資料集以查看品質、分布與圖片。" onRetry={() => void datasets.refresh()}>
            {selected && <>
              <Card className="p-5 sm:p-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-bold text-ink">{selected.name}</h2><StatusBadge status={selected.status || 'ready'} /></div><p className="mt-1 text-sm text-slate-500">建立於 {formatDate(selected.created_at)} · {formatBytes(selected.size_bytes)}</p></div><div className="flex flex-wrap gap-2"><a className="btn-secondary" href={api.datasetSummaryDownloadUrl(selected.id)} download><Download className="h-4 w-4" />下載摘要 JSON</a><button className="btn-danger" onClick={() => setDeleteTarget(selected)}><Trash2 className="h-4 w-4" />刪除資料集</button></div></div>
                <StatePanel loading={summary.loading} error={summary.error} onRetry={() => void summary.refresh()} empty={!summary.data}>
                  <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
                    {[['圖片總數', summary.data?.image_count ?? summary.data?.total_samples ?? 0], ['Training', summary.data?.split_counts?.train ?? selected.train_count ?? 0], ['Validation', summary.data?.split_counts?.validation ?? summary.data?.split_counts?.val ?? selected.validation_count ?? selected.val_count ?? 0], ['Test', summary.data?.split_counts?.test ?? selected.test_count ?? 0], ['損壞拒收', summary.data?.corrupt_count ?? 0], ['原圖未附 mask', summary.data?.missing_mask_count ?? 0], ['缺 metadata', summary.data?.missing_metadata_count ?? 0], ['重複圖片', summary.data?.duplicate_count ?? 0]].map(([label, value]) => <div key={String(label)} className="rounded-xl bg-slate-50 p-3"><p className="text-xs font-medium text-slate-500">{label}</p><p className="mt-1 text-xl font-bold text-slate-800">{value}</p></div>)}
                  </div>
                  {summary.data?.warnings?.length ? <div className="mt-4"><InlineNotice tone="warning" title="資料品質提醒"><ul className="list-disc pl-5">{summary.data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></InlineNotice></div> : null}
                  {summary.data?.is_imbalanced && <div className="mt-4"><InlineNotice tone="warning"><span className="inline-flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />類別分布可能不平衡，訓練前請確認 class weights 或補充資料。</span></InlineNotice></div>}
                  <div className="mt-6"><h3 className="text-sm font-bold text-slate-800">eGFR 分類分布</h3><div className="mt-3 h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={distribution} margin={{ top: 8, right: 8, left: -18, bottom: 20 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" /><XAxis dataKey="class_name" tick={{ fontSize: 11 }} angle={-10} textAnchor="end" interval={0} height={55} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip formatter={(value) => [`${value} 張`, '圖片']} /><Bar dataKey="count" radius={[7, 7, 0, 0]}>{distribution.map((item, index) => <Cell key={item.class_name} fill={chartColors[index % chartColors.length]} />)}</Bar></BarChart></ResponsiveContainer></div></div>
                </StatePanel>
              </Card>

              <Card className="p-5 sm:p-6">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"><div><h2 className="section-title">圖片與 metadata</h2><p className="mt-1 text-sm text-slate-500">可依檔名、分類、切割及品質狀態篩選。</p></div><div className="flex items-center gap-2 text-xs font-medium text-slate-500"><Filter className="h-4 w-4" />目前顯示 {sampleTotal ? offset + 1 : 0}–{Math.min(offset + (samples.data?.length || 0), sampleTotal)} / {sampleTotal} 筆</div></div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <label className="relative"><span className="sr-only">搜尋檔名</span><Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" /><input className="field pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜尋檔名" /></label>
                  <select className="field" value={classFilter} onChange={(event) => setClassFilter(event.target.value)} aria-label="分類篩選"><option value="">所有 eGFR 分類</option><option value="eGFR -15">eGFR &lt; 15</option><option value="eGFR 15-29">eGFR 15–29</option><option value="eGFR 30-59">eGFR 30–59</option><option value="eGFR 60-89">eGFR 60–89</option><option value="eGFR 90-">eGFR ≥ 90</option></select>
                  <select className="field" value={splitFilter} onChange={(event) => setSplitFilter(event.target.value)} aria-label="資料切割篩選"><option value="">所有資料切割</option><option value="train">Training</option><option value="validation">Validation</option><option value="test">Test</option></select>
                  <select className="field" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="品質狀態篩選"><option value="">所有品質狀態</option><option value="duplicate">重複圖片</option><option value="missing_label">缺少標籤</option><option value="missing_metadata">缺少 metadata</option><option value="missing_mask">缺少 mask</option></select>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">品質摘要與篩選反映匯入時的原圖，不包含後續工作產物。本批原圖未匯入舊 Mask；新產生的 Mask／特徵請於下方結果版本查看。資料切分是本次匯入建立，並非海報實驗切分。</p>
                <div className="mt-5" aria-busy={samples.loading}>{samples.loading && <p role="status" className="mb-3 text-sm text-slate-500">正在載入圖片…</p>}{samples.error && <InlineNotice tone="danger">{samples.error}<button className="btn-secondary ml-3" onClick={() => void samples.refresh()}>重試</button></InlineNotice>}<DatasetGallery key={selectedId} datasetId={selectedId} samples={samples.data || []} />{!samples.loading && !samples.error && !samples.data?.length && <p className="py-8 text-center text-slate-500">沒有符合條件的圖片，請調整搜尋或篩選條件。</p>}</div>
                <div className="mt-4 flex items-center justify-between gap-3"><button className="btn-secondary" disabled={offset === 0 || samples.loading} onClick={() => setOffset(Math.max(0, offset - 60))}>上一頁</button><span className="text-sm text-slate-600">第 {Math.floor(offset / 60) + 1} / {Math.max(1, Math.ceil(sampleTotal / 60))} 頁</span><button className="btn-secondary" disabled={offset + 60 >= sampleTotal || samples.loading} onClick={() => setOffset(offset + 60)}>下一頁</button></div>
                {samples.data?.length ? <div className="table-wrap mt-5"><table className="data-table"><thead><tr><th>檔名</th><th>分類</th><th>切割</th><th>格式／大小</th><th>資料狀態</th></tr></thead><tbody>{samples.data.map((sample) => <tr key={sample.id}><td className="max-w-[16rem] truncate font-medium">{sample.display_name || sample.file_name || sample.id}</td><td>{sample.class_name || '缺少標籤'}</td><td>{sample.split || '未切割'}{sample.fold !== undefined ? ` / fold ${sample.fold}` : ''}</td><td>{sample.mime_type || '—'} · {formatBytes(sample.size_bytes)}</td><td><div className="flex flex-wrap gap-1">{sample.is_duplicate && <span className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">重複</span>}{sample.missing_label && <span className="rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">缺標籤</span>}{sample.missing_metadata && <span className="rounded bg-violet-50 px-2 py-1 text-xs text-violet-700">缺 metadata</span>}{sample.missing_mask && <span className="rounded bg-sky-50 px-2 py-1 text-xs text-sky-700">缺 mask</span>}{!sample.is_duplicate && !sample.missing_label && !sample.missing_metadata && !sample.missing_mask && <StatusBadge status={sample.status || 'ready'} />}</div></td></tr>)}</tbody></table></div> : null}
              </Card>

              <Card className="p-5 sm:p-6">
                <div className="flex items-start justify-between gap-4"><div><h2 className="section-title">匯入拒絕紀錄</h2><p className="mt-1 text-sm text-slate-500">僅保存安全檔名、錯誤原因、大小與雜湊；不保存損壞檔案內容。</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{issues.data?.length || 0} 筆</span></div>
                <div className="mt-4"><StatePanel loading={issues.loading} error={issues.error} onRetry={() => void issues.refresh()} empty={!issues.data?.length} emptyTitle="沒有拒絕紀錄" emptyDescription="這個資料集的匯入檔案皆通過格式驗證。">
                  <div className="table-wrap"><table className="data-table"><thead><tr><th>檔名</th><th>類型</th><th>原因</th><th>大小</th><th>時間</th></tr></thead><tbody>{issues.data?.map((issue) => <tr key={issue.id}><td className="max-w-[15rem] truncate font-medium">{issue.display_name}</td><td><StatusBadge status={issue.issue_type} /></td><td><span className="font-medium text-slate-700">{issue.error_code}</span><span className="mt-0.5 block max-w-[28rem] text-xs text-slate-500">{issue.message}</span></td><td>{formatBytes(issue.size_bytes)}</td><td>{formatDate(issue.created_at)}</td></tr>)}</tbody></table></div>
                </StatePanel></div>
              </Card>
            </>}
          </StatePanel>
        </div>
      </div>
      <ConfirmDialog open={Boolean(deleteTarget)} title="刪除資料集？" description={`將刪除「${deleteTarget?.name || ''}」的本機工作副本及資料庫紀錄。此操作不會碰觸原始上傳來源，但無法由網站復原。`} busy={deleteBusy} onCancel={() => setDeleteTarget(undefined)} onConfirm={() => void deleteDataset()} />
    </div>
  )
}
