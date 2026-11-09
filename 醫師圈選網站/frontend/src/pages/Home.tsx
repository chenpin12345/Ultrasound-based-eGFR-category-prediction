import { FolderInput, Palette, PenLine, Upload } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, SIDE_LABEL, STATUS_LABEL, type ImageRow, type Status, type Summary } from '../api'

const FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'todo', label: '未開始' },
  { value: 'in_progress', label: '進行中' },
  { value: 'done', label: '已完成' },
  { value: 'unusable', label: '不能用' },
  { value: 'discuss', label: '需要討論' },
]
const DOT: Record<Status, string> = { todo: 'bg-line', in_progress: 'bg-amber', done: 'bg-ok', unusable: 'bg-alert' }

export function Home() {
  const navigate = useNavigate()
  const [summary, setSummary] = useState<Summary | null>(null)
  const [rows, setRows] = useState<ImageRow[]>([])
  const [filter, setFilter] = useState('')
  const [folder, setFolder] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setSummary(await api<Summary>('/summary'))
      setRows(await api<ImageRow[]>(`/images${filter ? `?status=${filter}` : ''}`))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [filter])

  useEffect(() => {
    load()
  }, [load])

  const run = async (action: () => Promise<string>) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await action())
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const importImages = () => run(async () => {
    const result = await api<{ added: number; existing: number; failed: number; skipped: number }>('/import', 'POST', { folder })
    setFolder('')
    return `已匯入 ${result.added} 張${result.existing ? `，${result.existing} 張已經有了` : ''}${result.failed ? `，${result.failed} 張打不開` : ''}${result.skipped ? `，略過 ${result.skipped} 個檔名不是影像 ID 的檔案` : ''}。`
  })

  const exportResults = () => run(async () => {
    const result = await api<{ folder: string; images: number; labels: number }>('/export', 'POST')
    return `已輸出 ${result.images} 張（標籤 ${result.labels} 張）到 ${result.folder}。到主系統「上傳醫師圈選」填這個路徑。`
  })

  const saveCircler = (value: string) => {
    setSummary((s) => (s ? { ...s, circler: value } : s))
    api('/circler', 'PUT', { circler: value }).catch((e: Error) => setError(e.message))
  }

  const percent = summary?.total ? Math.round((summary.finished / summary.total) * 100) : 0
  const empty = summary?.total === 0

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">醫師圈選</h1>
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2 text-ink-soft">圈選者代號
            <input value={summary?.circler ?? ''} maxLength={40} onChange={(e) => saveCircler(e.target.value)} className="w-28 rounded border border-line bg-white px-2 py-1 text-ink" />
          </label>
          <Link to="/colors" className="flex items-center gap-1 text-steel hover:underline"><Palette size={16} />顏色設定</Link>
        </div>
      </header>

      {!empty && summary && (
        <section className="mb-4 rounded-md border border-line bg-white p-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-3xl font-medium">{summary.finished}<span className="text-lg text-ink-faint"> / {summary.total} 張</span></p>
              <p className="mt-0.5 text-sm text-ink-soft">
                進行中 {summary.in_progress} · 不能用 {summary.unusable} · 需要討論 {summary.discuss}
                {summary.estimate ? ` · 每張約 ${Math.round(summary.estimate.seconds_per_image / 6) / 10} 分鐘，還需約 ${summary.estimate.remaining_hours} 小時` : ''}
              </p>
            </div>
            {summary.next_id ? (
              <button type="button" onClick={() => navigate(`/circle/${summary.next_id}`)} className="flex items-center gap-1.5 rounded bg-steel px-4 py-2 font-medium text-white hover:bg-steel-dark"><PenLine size={16} />繼續圈選</button>
            ) : <p className="text-sm text-ok">全部影像都完成了。</p>}
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded bg-paper-deep" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="圈選進度"><div className="h-full bg-steel" style={{ width: `${percent}%` }} /></div>
        </section>
      )}

      <section className="mb-4 grid gap-4 sm:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h2 className="mb-1 flex items-center gap-1.5 font-medium"><FolderInput size={16} />匯入影像</h2>
          <p className="mb-2 text-sm text-ink-soft">{empty ? '先匯入影像才能開始。' : ''}填主系統「醫師圈選」匯出的原始影像資料夾路徑。</p>
          <div className="flex gap-2">
            <label className="min-w-0 flex-1"><span className="sr-only">資料夾路徑</span>
              <input value={folder} onChange={(e) => setFolder(e.target.value)} className="w-full rounded border border-line px-2 py-1.5 text-sm" />
            </label>
            <button type="button" disabled={busy} onClick={importImages} className="shrink-0 rounded border border-steel px-3 py-1.5 text-sm text-steel hover:bg-steel-wash disabled:opacity-50">{busy ? '處理中…' : '匯入影像'}</button>
          </div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h2 className="mb-1 flex items-center gap-1.5 font-medium"><Upload size={16} />輸出結果</h2>
          <p className="mb-2 text-sm text-ink-soft">輸出已完成的影像，隨時可以輸出。檔案不含影像內容，可以上傳到主系統。</p>
          <button type="button" disabled={busy || !summary?.finished} onClick={exportResults} className="rounded border border-steel px-3 py-1.5 text-sm text-steel hover:bg-steel-wash disabled:opacity-50">{busy ? '處理中…' : '輸出結果'}</button>
        </div>
      </section>

      {message && <p role="status" className="mb-4 break-all rounded bg-ok-wash px-3 py-2 text-sm text-ok">{message}</p>}
      {error && <p role="alert" className="mb-4 rounded bg-alert-wash px-3 py-2 text-sm text-alert">{error}</p>}

      {!empty && (
        <section className="rounded-md border border-line bg-white">
          <div className="flex flex-wrap gap-1 border-b border-line p-2 text-sm">
            {FILTERS.map((f) => (
              <button key={f.value} type="button" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)} className={`rounded px-2.5 py-1 ${filter === f.value ? 'bg-steel-wash text-steel-dark' : 'text-ink-soft hover:bg-paper'}`}>{f.label}</button>
            ))}
          </div>
          {rows.length === 0 ? <p className="p-4 text-sm text-ink-soft">這個分類沒有影像。</p> : (
            <ul className="max-h-[420px] divide-y divide-line overflow-y-auto text-sm">
              {rows.map((row) => (
                <li key={row.id}>
                  <Link to={`/circle/${row.id}`} className="flex items-center gap-3 px-3 py-1.5 hover:bg-paper">
                    <span className="w-10 text-right text-ink-faint">{row.seq}</span>
                    <span className={`h-2 w-2 rounded-full ${DOT[row.status]}`} aria-hidden />
                    <span className="flex-1">{row.id}</span>
                    <span className="text-ink-soft">{row.side ? SIDE_LABEL[row.side] : '側別未知'}</span>
                    <span className="w-14 text-right text-ink-soft">{STATUS_LABEL[row.status]}</span>
                    {row.discuss && <span className="rounded bg-amber-wash px-1.5 text-xs text-amber">討論</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
