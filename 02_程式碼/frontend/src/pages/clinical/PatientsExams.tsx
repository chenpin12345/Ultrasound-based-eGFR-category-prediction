import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Users } from 'lucide-react'
import { EmptyState, PageHeader, Panel, Table, inputClass } from '../../components/ui'
import { useApi } from '../../api/hooks'
import { when } from '../../api/clinical'

interface PatientRow {
  id: string
  case_code: string
  mode: string
  name?: string | null
  mrn?: string | null
  exams: number
  last_exam_at: string | null
  last_exam_id: string | null
}

export default function PatientsExams() {
  const [query, setQuery] = useState('')
  const { data, error } = useApi<{ items: PatientRow[] }>('/clinical/patients')
  const q = query.trim().toUpperCase()
  const rows = (data?.items ?? []).filter((p) => !q || p.case_code.toUpperCase().includes(q) || (p.mrn ?? '').includes(q))
  return (
    <>
      <PageHeader title="病人與檢查" description="雙機展示只記病例代碼；每位病人的歷次檢查與腎長、eGFR 趨勢。" />
      <label className="mb-4 block max-w-xs">
        <span className="sr-only">搜尋病例代碼</span>
        <input className={inputClass} placeholder="搜尋病例代碼" value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>
      {error && <p className="mb-3 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{error.message}</p>}
      {data && !data.items.length ? (
        <EmptyState icon={Users} title="還沒有病人" body="收到第一筆檢查後，病例代碼會出現在這裡。" />
      ) : (
        <Panel flush>
          <Table
            minWidth={600}
            head={['病例代碼', '檢查次數', '最近一次檢查', '']}
            rows={rows.map((p) => [
              <Link key="c" to={`/clinical/patients/${p.id}`} className="font-semibold text-steel hover:underline">
                {p.case_code}
                {p.name && <span className="ml-2 font-normal text-ink-soft">{p.name}・{p.mrn}</span>}
              </Link>,
              `${p.exams} 次`,
              when(p.last_exam_at),
              p.last_exam_id ? <Link key="e" to={`/clinical/exams/${p.last_exam_id}`} className="text-steel hover:underline">{p.last_exam_id}</Link> : '—',
            ])}
          />
        </Panel>
      )}
    </>
  )
}
