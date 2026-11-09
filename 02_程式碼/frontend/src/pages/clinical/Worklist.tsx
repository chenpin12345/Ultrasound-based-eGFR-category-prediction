import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, ClipboardList, RefreshCw, Trash2 } from 'lucide-react'
import { Button, EmptyState, PageHeader, Panel, Pill, Table, Tabs, inputClass } from '../../components/ui'
import { api } from '../../api/client'
import { useApi, usePolling } from '../../api/hooks'
import { CANDIDATE_LABEL, examTone, mm, pct, when, type ExamRow, type ExamStatus } from '../../api/clinical'

type Filter = 'todo' | 'sign' | 'signed' | 'all'
type Range = 'today' | 'week' | 'month' | 'all'

const TODO: ExamStatus[] = ['receiving', 'analyzing', 'needs_data', 'layout_mismatch', 'partial', 'failed']

function since(range: Range): string {
  if (range === 'all') return ''
  const d = new Date()
  d.setDate(d.getDate() - (range === 'today' ? 0 : range === 'week' ? 6 : 29))
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Worklist() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('sign')
  const [range, setRange] = useState<Range>('week')
  const [query, setQuery] = useState('')
  const [flaggedOnly, setFlaggedOnly] = useState(false)
  const [message, setMessage] = useState('')
  const from = since(range)
  const { data, error, reload } = useApi<{ items: ExamRow[] }>(`/clinical/exams${from ? `?date_from=${from}` : ''}`, [from])
  usePolling(reload, 8000)
  const items = useMemo(() => data?.items ?? [], [data])

  const isSign = (e: ExamRow) => e.status === 'ready' && e.report_status !== 'signed'
  const flagged = (e: ExamRow) => e.missing_clinical.length > 0 || ['layout_mismatch', 'partial', 'failed', 'needs_data'].includes(e.status)
  const list = items.filter((e) => {
    const byTab = filter === 'all' ? true : filter === 'signed' ? e.report_status === 'signed' : filter === 'sign' ? isSign(e) : TODO.includes(e.status)
    const q = query.trim().toUpperCase()
    return byTab && (!q || e.id.includes(q) || e.case_code.toUpperCase().includes(q)) && (!flaggedOnly || flagged(e))
  })
  const waiting = items.filter(isSign).length
  const todo = items.filter((e) => TODO.includes(e.status)).length

  const reanalyze = async (e: ExamRow) => {
    try {
      await api.post(`/clinical/exams/${e.id}/reanalyze`)
      setMessage(`${e.id} 已排入重新分析。`)
      void reload()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }
  const trash = async (e: ExamRow) => {
    const reason = window.prompt(`把 ${e.id}（${e.case_code}）移入回收桶的原因：`)
    if (!reason) return
    try {
      await api.post('/trash', { kind: 'clinical_exam', id: e.id, reason })
      setMessage(`${e.id} 已移入回收桶，可在「回收桶」還原。`)
      void reload()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  const tabs: { id: Filter; label: string }[] = [
    { id: 'sign', label: `待確認與簽核（${waiting}）` },
    { id: 'todo', label: `待處理（${todo}）` },
    { id: 'signed', label: '已簽核' },
    { id: 'all', label: '全部' },
  ]

  return (
    <>
      <PageHeader
        title="工作清單"
        description="雙機傳來的檢查會自動去識別化與分析。點檢查編號進入檢查工作區，確認 AI 建議後建立報告。"
        actions={<Button icon={RefreshCw} onClick={() => void reload()}>重新整理</Button>}
      />
      <Tabs label="篩選檢查" value={filter} onChange={setFilter} tabs={tabs} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="w-full max-w-xs">
          <span className="sr-only">搜尋病例代碼或檢查編號</span>
          <input className={inputClass} placeholder="搜尋病例代碼或檢查編號" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <label>
          <span className="sr-only">日期範圍</span>
          <select className={`${inputClass} w-auto`} value={range} onChange={(e) => setRange(e.target.value as Range)}>
            <option value="today">今天</option>
            <option value="week">最近 7 天</option>
            <option value="month">最近 30 天</option>
            <option value="all">全部日期</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-2 text-[14px]">
          <input type="checkbox" className="accent-steel" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
          只看待補資料、版面不符或失敗
        </label>
      </div>
      {message && <p className="mb-3 rounded-md bg-steel-wash px-3 py-2 text-[14px] text-steel-dark">{message}</p>}
      {error && <p className="mb-3 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{error.message}</p>}
      {data && !items.length ? (
        <EmptyState
          icon={ClipboardList}
          title="還沒有檢查"
          body="到「影像接收」按「開始接收」，用另一台電腦打開畫面上的網址並輸入配對碼，傳送影像後會出現在這裡。"
          action={<Button variant="primary" onClick={() => navigate('/clinical/acquisition')}>前往影像接收</Button>}
        />
      ) : (
        <Panel flush>
          {list.length ? (
            <Table
              minWidth={1040}
              head={['檢查', '病例代碼', '收到時間', '影像', '狀態', '右腎長', '左腎長', 'eGFR<60', '提示', '']}
              rows={list.map((e) => [
                <Link key="id" to={`/clinical/exams/${e.id}`} className="font-semibold text-steel hover:underline">
                  {e.id}
                </Link>,
                e.case_code,
                when(e.received_at),
                `${e.images} 張`,
                <span key="s" className="flex flex-wrap gap-1">
                  <Pill tone={examTone[e.status]}>{e.status_label}</Pill>
                  {e.report_status === 'pending' && <Pill tone="amber">待簽核</Pill>}
                  {e.report_status === 'signed' && <Pill tone="ok">已簽核</Pill>}
                </span>,
                mm(e.right_length_mm),
                mm(e.left_length_mm),
                pct(e.p_lt60),
                <span key="f" className="flex flex-col gap-0.5 text-[13px]">
                  {e.candidate && <span className="text-amber">{CANDIDATE_LABEL}</span>}
                  {e.missing_clinical.length > 0 && (
                    <span className="inline-flex items-center gap-1 text-amber">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />缺{e.missing_clinical.join('、')}
                    </span>
                  )}
                  {!e.candidate && !e.missing_clinical.length && <span className="text-ink-faint">—</span>}
                </span>,
                <span key="a" className="flex gap-1">
                  {e.missing_clinical.length > 0 && (
                    <Link to={`/clinical/exams/${e.id}#clinical`} className="rounded px-2 py-1 text-[13px] text-steel hover:bg-steel-wash">
                      補填資料
                    </Link>
                  )}
                  {['ready', 'partial', 'failed', 'needs_data'].includes(e.status) && e.report_status !== 'signed' && (
                    <button type="button" className="rounded px-2 py-1 text-[13px] text-steel hover:bg-steel-wash" onClick={() => void reanalyze(e)}>
                      重新分析
                    </button>
                  )}
                  {e.report_status !== 'signed' && (
                    <button type="button" className="rounded p-1 text-ink-faint hover:bg-alert-wash hover:text-alert" title="移入回收桶" aria-label={`把 ${e.id} 移入回收桶`} onClick={() => void trash(e)}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </span>,
              ])}
            />
          ) : (
            <p className="px-5 py-8 text-ink-soft">沒有符合條件的檢查。調整篩選、日期或搜尋條件試試。</p>
          )}
        </Panel>
      )}
      <p className="mt-3 text-[13px] text-ink-faint">eGFR&lt;60 是模型輸出的機率，不是 CKD 診斷；整次檢查（兩側所有影像）一起整合。已簽核的檢查不能刪除，只能在報告頁作廢。</p>
    </>
  )
}
