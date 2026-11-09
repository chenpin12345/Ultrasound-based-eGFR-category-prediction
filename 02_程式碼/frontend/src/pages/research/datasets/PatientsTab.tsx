import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, Upload, Users } from 'lucide-react'
import { api } from '../../../api/client'
import { useAction, useApi } from '../../../api/hooks'
import { Button, EmptyState, KeyValue, Panel, Table, inputClass } from '../../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../../components/live'

interface PatientRow {
  id: string
  sex: string | null
  age: number | null
  has_diabetes: boolean | null
  has_fatty_liver: boolean | null
  egfr_group: string
  images: number
  right: number
  left: number
}
interface Candidate {
  row_key: string
  source_ref: string
  sex: string | null
  age: number | null
  diabetes: boolean | null
}
interface Review {
  table_id?: string
  ambiguous: { key: string; table_id?: string; note?: string; image_ids: string[]; candidates: Candidate[] }[]
  unmatched: string[]
}
interface MatchPreview {
  matched_images: number
  matched_patients: number
  ambiguous_groups: number
  ambiguous_images: number
  unmatched_images: number
}

const TABLE_KEY = 'kidney-last-patient-table'
const readTable = () => {
  try {
    return localStorage.getItem(TABLE_KEY) ?? ''
  } catch {
    return ''
  }
}

export default function PatientsTab() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [tableId, setTableId] = useState(readTable)
  const [rows, setRows] = useState<number | null>(null)
  const [preview, setPreview] = useState<MatchPreview | null>(null)
  const [choice, setChoice] = useState<Record<string, string>>({})
  const patients = useApi<{ patients: PatientRow[] }>('/patients')
  const review = useApi<Review>('/patients/review')
  const rematch = useAction(() => api.post<{ job_id: string }>('/patients/review/rematch'))
  const [rematchJob, setRematchJob] = useState<string | null>(null)

  const upload = useAction(async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<{ table_id: string; rows: number; has_filename_column: boolean }>('/patients/tables', form)
  })
  const doPreview = useAction((id: string) => api.post<MatchPreview>('/patients/match-preview', { table_id: id }))
  const apply = useAction((id: string) => api.post('/patients/match', { table_id: id }))
  const resolve = useAction((table: string, imageIds: string[], rowKey: string) => api.post('/patients/review/resolve', { table_id: table, image_ids: imageIds, row_key: rowKey }))

  const remember = (id: string) => {
    setTableId(id)
    try {
      localStorage.setItem(TABLE_KEY, id)
    } catch {
      // 只保留在這次瀏覽
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel title="1. 上傳病人表">
          <p className="mb-3 text-[14px] text-ink-soft">
            CSV 或 XLSX。欄位會自動辨識：病人編號、性別、年齡、是否糖尿病、eGFR、日期；若有「影像檔名」欄，會直接用檔名對應。初始資料集使用 <code>add_HbA1C.xlsx</code>。
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (!f) return
              const r = await upload.run(f)
              if (r) {
                remember(r.table_id)
                setRows(r.rows)
                setPreview(null)
              }
            }}
          />
          <Button icon={Upload} disabled={upload.busy} onClick={() => fileRef.current?.click()}>
            {upload.busy ? '上傳中…' : '選擇病人表'}
          </Button>
          {tableId && (
            <p className="mt-3 text-[14px]">
              目前病人表：<code>{tableId}</code>
              {rows !== null && `（${rows} 列）`}
            </p>
          )}
          <ErrorNote error={upload.error} />
          <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
            <Button
              disabled={!tableId || doPreview.busy}
              onClick={async () => {
                const p = await doPreview.run(tableId)
                if (p) setPreview(p)
              }}
            >
              2. 預覽對照結果
            </Button>
            <Button
              variant="primary"
              disabled={!preview || apply.busy}
              onClick={async () => {
                await apply.run(tableId)
                void patients.reload()
                void review.reload()
                setPreview(null)
              }}
            >
              3. 套用對照
            </Button>
          </div>
          <ErrorNote error={doPreview.error ?? apply.error} />
          {preview && (
            <div className="mt-4">
              <KeyValue
                items={[
                  ['可自動對照的影像', `${preview.matched_images} 張（${preview.matched_patients} 位病人）`],
                  ['需人工確認', `${preview.ambiguous_groups} 組、${preview.ambiguous_images} 張`],
                  ['找不到病人', `${preview.unmatched_images} 張`],
                ]}
              />
            </div>
          )}
        </Panel>
        <Panel title="對照規則">
          <ol className="list-decimal space-y-2 pl-5 text-[14px] text-ink-soft">
            <li>病人表有影像檔名欄 → 直接對應。</li>
            <li>否則用原始檔名前綴（eGFR 數值）比對病人表的 eGFR。</li>
            <li>同一個 eGFR 有多位病人時，用影像上 OCR 讀到的年齡、性別區分。</li>
            <li>還是分不出來的，列在下方請你選擇。</li>
          </ol>
          <p className="mt-3 text-[13px] text-ink-faint">原始檔名就是答案（eGFR），對照完成後不會再被任何程式使用。</p>
        </Panel>
      </div>

      <Panel
        title="需要人工確認"
        flush
        aside={
          review.data?.ambiguous.length ? (
            <Button
              icon={RefreshCw}
              disabled={rematch.busy || Boolean(rematchJob)}
              onClick={async () => {
                const r = await rematch.run()
                if (r) setRematchJob(r.job_id)
              }}
            >
              重新比對（年齡＋同一人分組）
            </Button>
          ) : undefined
        }
      >
        {rematchJob && (
          <div className="px-5 pt-4">
            <JobProgress
              jobId={rematchJob}
              onDone={() => {
                setRematchJob(null)
                void review.reload()
                void patients.reload()
              }}
            />
            <p className="mt-2 text-[12px] text-ink-faint">用年齡與性別重新比對；並讀標頭的病歷號，只用來判斷哪些影像是同一位病人（不保存、不顯示）。</p>
          </div>
        )}
        <ErrorNote error={rematch.error} />
        {review.loading && !review.data ? (
          <Loading />
        ) : review.data && review.data.ambiguous.length ? (
          <Table
            minWidth={700}
            head={['組別', '影像', '候選病人', '']}
            rows={review.data.ambiguous.map((g, i) => [
              `第 ${i + 1} 組`,
              <span key="i" className="text-[13px]">
                {g.image_ids.slice(0, 3).map((id) => (
                  <Link key={id} to={`/research/datasets/images/${id}`} className="mr-2 text-steel hover:underline">
                    {id}
                  </Link>
                ))}
                {g.image_ids.length > 3 && `等 ${g.image_ids.length} 張`}
                {g.note && <span className="mt-1 block text-[12px] text-ink-soft">{g.note}</span>}
              </span>,
              <select key="c" className={`${inputClass} w-auto`} value={choice[g.key] ?? ''} onChange={(e) => setChoice({ ...choice, [g.key]: e.target.value })} aria-label={`${g.key} 的病人`}>
                <option value="">請選擇</option>
                {g.candidates.map((c) => (
                  <option key={c.row_key} value={c.row_key}>
                    {c.source_ref || '—'}・{c.sex === 'M' ? '男' : c.sex === 'F' ? '女' : '?'} {c.age ?? '?'} 歲{c.diabetes ? '・糖尿病' : ''}
                  </option>
                ))}
              </select>,
              <Button
                key="b"
                variant="ghost"
                disabled={!choice[g.key] || resolve.busy}
                onClick={async () => {
                  await resolve.run(g.table_id ?? review.data?.table_id ?? tableId, g.image_ids, choice[g.key])
                  void review.reload()
                  void patients.reload()
                }}
              >
                確認
              </Button>,
            ])}
          />
        ) : (
          <p className="px-5 py-6 text-[14px] text-ink-soft">沒有需要人工確認的對照。{review.data?.unmatched.length ? `另有 ${review.data.unmatched.length} 張影像在病人表中找不到病人。` : ''}</p>
        )}
        <ErrorNote error={resolve.error} />
      </Panel>

      <Panel title={`病人（${patients.data?.patients.length ?? 0} 位）`} flush>
        {patients.data && patients.data.patients.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={Users} title="還沒有病人" body="匯入影像後，上傳病人表並套用對照，病人才會出現在這裡。" />
          </div>
        ) : (
          <Table
            minWidth={640}
            head={['病人', '性別／年齡', '糖尿病', '脂肪肝', 'eGFR 分組', '影像', '右／左']}
            rows={(patients.data?.patients ?? []).map((p) => [
              <Link key="p" to={`/research/datasets?tab=images&patient=${p.id}`} className="font-medium text-steel hover:underline">
                {p.id}
              </Link>,
              `${p.sex === 'M' ? '男' : p.sex === 'F' ? '女' : '—'}／${p.age ?? '—'}`,
              p.has_diabetes === null ? '—' : p.has_diabetes ? '有' : '無',
              p.has_fatty_liver === null ? '—' : p.has_fatty_liver ? '有' : '無',
              p.egfr_group,
              p.images,
              `${p.right}／${p.left}`,
            ])}
          />
        )}
      </Panel>
    </div>
  )
}
