import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../api/hooks'
import { statusLabel, type ImageInfo } from '../../api/types'
import { BackLink, Figure, KeyValue, Panel, Table } from '../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../components/live'

interface Report {
  id: string
  source_kind: string
  source_label: string
  status: string
  created_by: string
  created_at: string
  finished_at: string | null
  job_id: string | null
  per_template: { template_id: string; machine: string; status: string; count: number }[]
  report: {
    total: number
    imported: number
    usable: number
    pending_review: number
    duplicates: number
    unreadable: number
    unknown_size: number
    review: { image_id?: string; file_index?: number; reason: string }[]
    patient_tables?: { name: string; rows?: number; matched_images?: number; ambiguous_groups?: number; unmatched_images?: number; error?: string }[]
  } | null
}

export default function ImportReport() {
  const { importId = '' } = useParams()
  const r = useApi<Report>(`/imports/${importId}`)
  if (r.loading && !r.data) return <Loading />
  if (!r.data) return <ErrorNote error={r.error} />
  const d = r.data
  const rep = d.report

  return (
    <>
      <BackLink to="/research/datasets?tab=batches">回匯入紀錄</BackLink>
      <h1 className="mb-1 text-[24px] font-bold">匯入報表 {d.id}</h1>
      <p className="mb-5 text-ink-soft">
        {d.source_label}・{d.created_by}・{d.created_at.slice(0, 16).replace('T', ' ')}
      </p>
      {d.status === 'running' && d.job_id && (
        <div className="mb-5">
          <JobProgress jobId={d.job_id} onDone={() => void r.reload()} />
        </div>
      )}
      {rep ? (
        <>
          <Panel className="mb-5">
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-6">
              <Figure value={rep.total} label="來源影像" />
              <Figure value={rep.imported} label="本次匯入" />
              <Figure value={rep.usable} label="可用" />
              <Figure value={rep.pending_review} label="待人工確認" />
              <Figure value={rep.duplicates} label="重複略過" />
              <Figure value={rep.unreadable + rep.unknown_size} label="無法處理" />
            </div>
          </Panel>
          <div className="grid gap-5 xl:grid-cols-2">
            <Panel title="各版面處理結果" flush>
              <Table minWidth={420} head={['範本', '機型', '狀態', '張數']} rows={d.per_template.map((t) => [t.template_id, t.machine, statusLabel[t.status as ImageInfo['status']] ?? t.status, t.count])} />
            </Panel>
            <Panel title={`需要人工確認（${rep.review.length}）`} flush>
              {rep.review.length ? (
                <Table
                  minWidth={460}
                  head={['影像', '原因']}
                  rows={rep.review.slice(0, 300).map((x) => [
                    x.image_id ? (
                      <Link key="i" to={`/research/datasets/images/${x.image_id}`} className="text-steel hover:underline">
                        {x.image_id}
                      </Link>
                    ) : (
                      `來源第 ${x.file_index} 個檔案`
                    ),
                    x.reason,
                  ])}
                />
              ) : (
                <p className="px-5 py-4 text-[14px] text-ink-soft">沒有需要人工確認的影像。</p>
              )}
            </Panel>
          </div>
          {rep.patient_tables && rep.patient_tables.length > 0 && (
            <Panel title="病人表自動對照" flush className="mt-5">
              <Table
                minWidth={560}
                head={['病人表', '列數', '已對照影像', '需人工確認', '找不到病人']}
                rows={rep.patient_tables.map((t) => (t.error ? [t.name, '—', <span key="e" className="text-alert">{t.error}</span>, '—', '—'] : [t.name, t.rows ?? 0, t.matched_images ?? 0, `${t.ambiguous_groups ?? 0} 組`, t.unmatched_images ?? 0]))}
              />
              <p className="px-5 py-3 text-[13px] text-ink-soft">
                需人工確認的組別在 <Link to="/research/datasets?tab=patients" className="text-steel underline">資料集 › 病人對照</Link> 處理。
              </p>
            </Panel>
          )}
        </>
      ) : (
        <Panel>
          <KeyValue items={[['狀態', d.status]]} />
        </Panel>
      )}
    </>
  )
}
