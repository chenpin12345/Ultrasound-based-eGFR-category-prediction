import { Link, useParams } from 'react-router-dom'
import { BackLink, Panel, Pill, Table } from '../../components/ui'
import { useApi } from '../../api/hooks'
import { examTone, mm, pct, reportTone, when, type ExamStatus, type ReportStatus, type Side } from '../../api/clinical'

interface Trend {
  patient: { id: string; case_code: string; mode: string; name?: string | null; mrn?: string | null }
  exams: {
    id: string
    received_at: string
    status: ExamStatus
    status_label: string
    age: number | null
    p_lt60: number | null
    sides: Record<Side, { length_mm: number | null; grade: string | null }>
    candidate: boolean
    report: { id: string; status: ReportStatus } | null
  }[]
}

const REPORT_NAME = { draft: '草稿', pending: '待簽核', signed: '已簽核', void: '已作廢' } as const

/** 很小的折線：每次檢查一個點，看腎長或 eGFR 機率的走勢。 */
function Spark({ values, label, format }: { values: (number | null)[]; label: string; format: (v: number) => string }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] !== null)
  if (pts.length < 2) return <p className="text-[13px] text-ink-faint">{label}：至少兩次檢查才有趨勢。</p>
  const ys = pts.map((p) => p[1])
  const lo = Math.min(...ys)
  const hi = Math.max(...ys)
  const w = 240
  const h = 56
  const x = (i: number) => 8 + (i / Math.max(1, values.length - 1)) * (w - 16)
  const y = (v: number) => (hi === lo ? h / 2 : h - 8 - ((v - lo) / (hi - lo)) * (h - 16))
  return (
    <figure>
      <figcaption className="text-[13px] text-ink-soft">{label}（{format(ys[0])} → {format(ys[ys.length - 1])}）</figcaption>
      <svg width={w} height={h} role="img" aria-label={`${label}趨勢`} className="mt-1">
        <polyline fill="none" stroke="currentColor" className="text-steel" strokeWidth={2} points={pts.map(([i, v]) => `${x(i)},${y(v)}`).join(' ')} />
        {pts.map(([i, v]) => <circle key={i} cx={x(i)} cy={y(v)} r={3} className="fill-steel" />)}
      </svg>
    </figure>
  )
}

export default function PatientDetail() {
  const { patientId } = useParams()
  const { data, error } = useApi<Trend>(`/clinical/patients/${patientId}`, [patientId])
  if (error && !data) return <p className="rounded-md bg-alert-wash px-3 py-2 text-alert">{error.message}</p>
  if (!data) return <p className="text-ink-soft">讀取中…</p>
  return (
    <>
      <BackLink to="/clinical/patients">回病人與檢查</BackLink>
      <h1 className="mb-5 text-[24px] font-bold">
        {data.patient.case_code}
        {data.patient.name && <span className="ml-3 text-[16px] font-normal text-ink-soft">{data.patient.name}・{data.patient.mrn}</span>}
      </h1>
      <Panel title="趨勢" className="mb-5">
        <div className="flex flex-wrap gap-8">
          <Spark values={data.exams.map((e) => e.sides.right.length_mm)} label="右腎長" format={(v) => `${v.toFixed(0)} mm`} />
          <Spark values={data.exams.map((e) => e.sides.left.length_mm)} label="左腎長" format={(v) => `${v.toFixed(0)} mm`} />
          <Spark values={data.exams.map((e) => e.p_lt60)} label="eGFR<60 機率" format={(v) => `${Math.round(v * 100)}%`} />
        </div>
      </Panel>
      <Panel title="歷次檢查" flush>
        <Table
          minWidth={820}
          head={['檢查', '日期', '狀態', '右腎長', '左腎長', '分級（右／左）', 'eGFR<60', '報告']}
          rows={[...data.exams].reverse().map((e) => [
            <Link key="i" to={`/clinical/exams/${e.id}`} className="font-semibold text-steel hover:underline">{e.id}</Link>,
            when(e.received_at).slice(0, 10),
            <Pill key="s" tone={examTone[e.status]}>{e.status_label}</Pill>,
            mm(e.sides.right.length_mm),
            mm(e.sides.left.length_mm),
            `${e.sides.right.grade ?? '—'}／${e.sides.left.grade ?? '—'}`,
            pct(e.p_lt60),
            e.report ? <Pill key="r" tone={reportTone[e.report.status]}>{REPORT_NAME[e.report.status]}</Pill> : '—',
          ])}
        />
      </Panel>
    </>
  )
}
