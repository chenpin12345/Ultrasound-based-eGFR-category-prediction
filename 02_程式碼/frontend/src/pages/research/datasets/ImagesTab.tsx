import { useState } from 'react'
import { Ban, ChevronLeft, ChevronRight, RotateCcw, ScanSearch } from 'lucide-react'
import { api, imageUrl } from '../../../api/client'
import { useAction, useApi } from '../../../api/hooks'
import { sideLabel, statusLabel, type ImageInfo } from '../../../api/types'
import { Button, Panel, Table, inputClass } from '../../../components/ui'
import { ImageGrid } from '../../../components/ImageGrid'
import { EmptyState } from '../../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../../components/live'
import { ImageIcon } from 'lucide-react'

const PAGE = 48
const REASONS = ['腎臟截斷', '陰影遮蔽', '非長軸', '增益異常', '非腎臟', '去識別化殘留', '重複']

export default function ImagesTab({ initialStatus = '', patient = '' }: { initialStatus?: string; patient?: string }) {
  const [status, setStatus] = useState(initialStatus)
  const [machine, setMachine] = useState('')
  const [side, setSide] = useState('')
  const [unmatched, setUnmatched] = useState(false)
  const [offset, setOffset] = useState(0)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [reason, setReason] = useState(REASONS[0])

  const query = new URLSearchParams({ offset: String(offset), limit: String(PAGE) })
  if (status) query.set('status', status)
  if (machine) query.set('machine', machine)
  if (side) query.set('side', side)
  if (unmatched) query.set('unmatched', 'true')
  if (patient) query.set('patient_id', patient)
  const list = useApi<{ total: number; images: ImageInfo[] }>(`/images?${query}`)
  const stats = useApi<{ rows: { machine: string; size: string; status: string; count: number }[] }>('/images/stats')
  const bulk = useAction((ids: string[], to: 'usable' | 'excluded') => api.post('/images/bulk-status', { image_ids: ids, status: to, exclude_reason: to === 'excluded' ? reason : null }))
  const bulkSide = useAction((ids: string[], side: 'right' | 'left') => api.post('/images/bulk-side', { image_ids: ids, side }))
  const reread = useAction(() => api.post<{ job_id: string }>('/images/reread-side'))
  const [rereadJob, setRereadJob] = useState<string | null>(null)

  const total = list.data?.total ?? 0
  const filterSelect = (label: string, value: string, set: (v: string) => void, options: [string, string][]) => (
    <label className="text-[13px] text-ink-soft">
      {label}
      <select
        className={`${inputClass} mt-1 w-auto`}
        value={value}
        onChange={(e) => {
          set(e.target.value)
          setOffset(0)
        }}
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <div className="space-y-5">
      {stats.data && stats.data.rows.length > 0 && (
        <Panel title="已匯入影像（依機型、尺寸、狀態）" flush>
          <Table minWidth={420} head={['機型', '尺寸', '狀態', '張數']} rows={stats.data.rows.map((r) => [r.machine, r.size, statusLabel[r.status as ImageInfo['status']] ?? r.status, r.count])} />
        </Panel>
      )}
      {patient && <p className="text-[14px] text-ink-soft">只顯示病人 {patient} 的影像。</p>}
      <div className="flex flex-wrap items-end gap-3">
        {filterSelect('狀態', status, setStatus, [['', '全部'], ['usable', '可用'], ['pending_review', '待人工確認'], ['excluded', '已排除']])}
        {filterSelect('機型', machine, setMachine, [['', '全部'], ['Toshiba', 'Toshiba'], ['Canon Aplio 300', 'Canon Aplio 300']])}
        {filterSelect('側別', side, setSide, [['', '全部'], ['right', '右'], ['left', '左'], ['unknown', '未知']])}
        <label className="inline-flex items-center gap-2 pb-2 text-[14px]">
          <input type="checkbox" className="accent-steel" checked={unmatched} onChange={(e) => setUnmatched(e.target.checked)} />
          只看還沒對到病人
        </label>
        <div className="ml-auto flex flex-wrap items-end gap-2">
          <Button
            icon={ScanSearch}
            disabled={reread.busy}
            onClick={async () => {
              const r = await reread.run()
              if (r) setRereadJob(r.job_id)
            }}
          >
            重新判斷側別
          </Button>
          <Button
            onClick={() => {
              setSelectMode((v) => !v)
              setSelected([])
            }}
          >
            {selectMode ? '取消選取' : '選取多張'}
          </Button>
          {selectMode && (
            <>
              <select className={`${inputClass} w-auto`} value={reason} onChange={(e) => setReason(e.target.value)} aria-label="排除原因">
                {REASONS.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <Button
                icon={Ban}
                disabled={!selected.length || bulk.busy}
                onClick={async () => {
                  await bulk.run(selected, 'excluded')
                  setSelected([])
                  void list.reload()
                }}
              >
                排除 {selected.length} 張
              </Button>
              {(['right', 'left'] as const).map((s) => (
                <Button
                  key={s}
                  disabled={!selected.length || bulkSide.busy}
                  onClick={async () => {
                    await bulkSide.run(selected, s)
                    setSelected([])
                    void list.reload()
                  }}
                >
                  設為{sideLabel[s]}腎
                </Button>
              ))}
              <Button
                icon={RotateCcw}
                disabled={!selected.length || bulk.busy}
                onClick={async () => {
                  await bulk.run(selected, 'usable')
                  setSelected([])
                  void list.reload()
                }}
              >
                設為可用
              </Button>
            </>
          )}
        </div>
      </div>
      <ErrorNote error={list.error ?? bulk.error ?? bulkSide.error ?? reread.error} />
      {rereadJob && (
        <Panel title="重新判斷側別（體表示意圖）">
          <p className="mb-3 text-[13px] text-ink-soft">讀取每張影像右下角的體表示意圖：有肚臍「×」是正面圖、有脊椎直線是背面圖，再看探頭在中線哪一邊。人工設定過的側別不會被覆蓋。</p>
          <JobProgress key={rereadJob} jobId={rereadJob} onDone={() => void list.reload()} />
        </Panel>
      )}
      {list.loading && !list.data ? (
        <Loading />
      ) : total === 0 ? (
        <EmptyState icon={ImageIcon} title="沒有符合條件的影像" body="還沒有匯入影像，或篩選條件太嚴格。到「匯入」分頁匯入原始資料集或匯入區的新收案。" />
      ) : (
        <>
          <ImageGrid
            items={(list.data?.images ?? []).map((i) => ({
              id: i.id,
              to: `/research/datasets/images/${i.id}`,
              src: imageUrl(i.id, 'thumb'),
              caption: i.id,
              sub: `${i.patient_id ?? '未對照'}・${i.side ? sideLabel[i.side] + '腎' : '側別未知'}・${i.machine.startsWith('Canon') ? 'Canon' : 'Toshiba'}`,
              flag: i.status === 'usable' ? undefined : statusLabel[i.status],
              selected: selected.includes(i.id),
            }))}
            onToggle={selectMode ? (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id])) : undefined}
          />
          <div className="flex items-center justify-between text-[14px]">
            <span className="text-ink-soft">
              第 {offset + 1}–{Math.min(offset + PAGE, total)} 張，共 {total} 張
            </span>
            <span className="flex gap-2">
              <Button icon={ChevronLeft} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                上一頁
              </Button>
              <Button disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
                下一頁
                <ChevronRight className="h-4 w-4" aria-hidden />
              </Button>
            </span>
          </div>
        </>
      )}
    </div>
  )
}
