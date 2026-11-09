import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { EmptyState, PageHeader, Panel, Pill, Table, Tabs } from '../../components/ui'
import { useApi } from '../../api/hooks'
import { reportTone, when, type ReportRow, type ReportStatus } from '../../api/clinical'

const FILTERS: { id: ReportStatus; label: string }[] = [
  { id: 'pending', label: '待簽核' },
  { id: 'draft', label: '草稿' },
  { id: 'signed', label: '已簽核' },
  { id: 'void', label: '已作廢' },
]

export default function Reports() {
  const [filter, setFilter] = useState<ReportStatus>('pending')
  const { data, error } = useApi<{ items: ReportRow[] }>('/clinical/reports')
  const all = data?.items ?? []
  const rows = all.filter((r) => r.status === filter)

  return (
    <>
      <PageHeader
        title="報告中心"
        description="報告由醫師確認 AI 建議後簽核。每次儲存都是新的版本；已簽核只能修訂或作廢。PDF 每份報告只保留最新一個檔案，記錄使用的模型與階段。"
      />
      <Tabs label="報告狀態" value={filter} onChange={setFilter} tabs={FILTERS.map((f) => ({ id: f.id, label: `${f.label}（${all.filter((r) => r.status === f.id).length}）` }))} />
      {error && <p className="mb-3 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{error.message}</p>}
      {data && !all.length ? (
        <EmptyState icon={FileText} title="還沒有報告" body="在檢查工作區按「建立報告」，AI 會預填腎長與 eGFR，其他欄位由醫師填寫。" />
      ) : (
        <Panel flush>
          {rows.length ? (
            <Table
              minWidth={780}
              head={['報告', '病例代碼', '檢查', '狀態', '版本', '判讀醫師', '更新時間', 'PDF']}
              rows={rows.map((r) => [
                <Link key="id" to={`/clinical/exams/${r.exam_id}/report?id=${r.id}`} className="font-semibold text-steel hover:underline">{r.id}</Link>,
                r.case_code,
                <Link key="e" to={`/clinical/exams/${r.exam_id}`} className="text-steel hover:underline">{r.exam_id}</Link>,
                <span key="s" className="flex flex-col gap-0.5">
                  <Pill tone={reportTone[r.status]}>{r.status_label}</Pill>
                  {r.void_reason && <span className="text-[12px] text-ink-faint">{r.void_reason}</span>}
                </span>,
                `第 ${r.version} 版`,
                r.signed_by ? `${r.signed_by}（${when(r.signed_at)}）` : '—',
                when(r.updated_at),
                r.pdf ? <a key="p" href={`/api/clinical/reports/${r.id}/pdf`} target="_blank" rel="noreferrer" className="text-steel hover:underline">開啟</a> : '—',
              ])}
            />
          ) : (
            <p className="px-5 py-8 text-ink-soft">這個狀態沒有報告。</p>
          )}
        </Panel>
      )}
    </>
  )
}
