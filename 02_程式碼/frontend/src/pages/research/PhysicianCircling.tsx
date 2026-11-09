import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, FileInput, FolderPlus, PackageCheck, Undo2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { Button, Field, Panel, Pill, Table, inputClass } from '../../components/ui'
import type { Tone } from '../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../components/live'
import { ConfirmDialog } from '../../components/overlays'
import { OpenFolderButton } from '../../components/OpenFolder'

type ItemStatus = 'pending' | 'exported' | 'parsed' | 'imported' | 'needs_redraw' | 'unusable'
type State = 'drawn' | 'absent' | 'unlabeled'

interface Counts {
  total: number
  pending: number
  exported: number
  parsed: number
  imported: number
  needs_redraw: number
  unusable: number
  errors: number
}

interface Batch {
  id: string
  kind: 'test' | 'train' | 'all'
  split_id: string
  round: number
  note: string
  exported_at: string | null
  export_relpath: string | null
  include_original: boolean
  created_at: string
  counts: Counts
}

interface Item {
  id: number
  seq: number
  image_id: string
  side: string | null
  status: ItemStatus
  circler: string
  return_kind: string
  parse: { file?: string; errors?: string[]; warnings?: string[]; areas?: Record<string, number>; reference?: string }
  structures: Record<string, State>
  reject_reason: string
}

const STATUS: Record<ItemStatus, [string, Tone]> = {
  pending: ['待匯出', 'neutral'],
  exported: ['已匯出，等醫師傳回', 'steel'],
  parsed: ['已轉換，待檢查', 'amber'],
  imported: ['已匯入', 'ok'],
  needs_redraw: ['需請醫師重圈', 'alert'],
  unusable: ['醫師判定不能用（已排除）', 'neutral'],
}
const STRUCTURES: [string, string][] = [
  ['kidney', '腎臟外框'],
  ['sinus', '腎竇'],
  ['liver', '肝'],
  ['spleen', '脾'],
]
const STATE_LABEL: Record<State, string> = { drawn: '已畫', absent: '不在影像中', unlabeled: '未標' }
const sideLabel = (s: string | null) => (s === 'right' ? '右腎' : s === 'left' ? '左腎' : '側別未知')

/** 醫師圈選（決策 D16–D21）：醫師在系統外圈選；這裡建立批次、匯出、上傳傳回的圈選、檢查後匯入。 */
const batchName = (b: Pick<Batch, 'kind' | 'round'>) => (b.kind === 'test' ? '測試集' : b.kind === 'all' ? '全部影像' : `訓練第 ${b.round} 批`)

export default function PhysicianCircling() {
  const list = useApi<{ batches: Batch[]; progress: { test_sides: number; test_sides_done: number; train_images_done: number } }>('/circling/batches')
  const colors = useApi<{ colors: { color: string; structure: string }[]; original_confirm: string }>('/circling/colors')
  const [size, setSize] = useState(100)
  const [selected, setSelected] = useState<string | null>(null)
  const create = useAction((kind: Batch['kind']) => api.post<{ id: string; count: number }>('/circling/batches', { kind, size }))
  const batches = list.data?.batches ?? []
  const current = selected ?? batches[0]?.id ?? null
  const p = list.data?.progress

  const make = async (kind: Batch['kind']) => {
    const r = await create.run(kind)
    if (r) {
      setSelected(r.id)
      void list.reload()
    }
  }

  return (
    <div className="space-y-5">
      <Panel title="醫師圈選">
        <p className="text-[14px] text-ink-soft">
          醫師不在本系統畫圖：先建立批次並匯出影像交給醫師，醫師在圖上用顏色圈出腎臟外框、腎竇、肝或脾，
          <strong>檔名與尺寸不要改</strong>，傳回後在這裡上傳。系統會和原本的影像逐像素比對、只取出醫師加的筆畫，轉成遮罩讓你檢查後匯入。
          測試集先做（每位測試病人每側 1 張），之後每批約 100 張；用分割訓練的學習曲線決定要不要下一批。規則見標註規範。
          使用「醫師圈選網站」時，選取全部影像後勾選原始影像匯出，圈完把網站輸出的資料夾路徑填到上傳欄位。
        </p>
        {colors.data && colors.data.colors.length === 0 && (
          <p className="mt-3 rounded border border-amber bg-amber-wash px-3 py-2 text-[13px]">
            <Pill tone="amber">尚未設定顏色對照</Pill> 彩色圈選要先到 <Link to="/settings?tab=colors" className="text-steel underline">設定 › 顏色對照</Link> 指定每種顏色代表的構造，才能轉換；標籤 PNG 不受影響。
          </p>
        )}
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded border border-line p-3">
            <p className="text-[13px] text-ink-faint">測試集完成度（病人側）</p>
            <p className="text-[22px] font-semibold tabular-nums">{p ? `${p.test_sides_done} / ${p.test_sides}` : '—'}</p>
          </div>
          <div className="rounded border border-line p-3">
            <p className="text-[13px] text-ink-faint">訓練影像已有醫師遮罩</p>
            <p className="text-[22px] font-semibold tabular-nums">{p ? p.train_images_done : '—'} 張</p>
          </div>
          <div className="flex flex-col justify-center gap-2 rounded border border-line p-3">
            <Button variant="primary" icon={FolderPlus} disabled={create.busy} onClick={() => void make('test')}>
              選取測試集（每側 1 張）
            </Button>
            <Button icon={FolderPlus} disabled={create.busy} onClick={() => void make('all')}>
              選取全部影像（圈選網站）
            </Button>
            <div className="flex items-center gap-2">
              <input type="number" min={1} max={500} className={`${inputClass} w-20`} value={size} onChange={(e) => setSize(Number(e.target.value))} aria-label="每批張數" />
              <Button icon={FolderPlus} disabled={create.busy} onClick={() => void make('train')}>
                選取下一批訓練影像
              </Button>
            </div>
          </div>
        </div>
        <ErrorNote error={create.error ?? list.error} />
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-ink-soft">
          <OpenFolderButton kind="index" label="開啟索引資料夾" />
          <span>各批次的匯出日期、傳回數、已匯入、需重圈在 醫師圈選批次.csv；每張影像的圈選批次與是否有醫師遮罩在 影像索引.csv（Excel 可開，不含個資）。</span>
        </div>
      </Panel>

      <Panel title="圈選批次" flush>
        {list.loading && !list.data ? (
          <Loading />
        ) : batches.length ? (
          <Table
            minWidth={720}
            head={['批次', '種類', '張數', '已匯出', '待檢查', '已匯入', '需重圈', '不能用', '匯出日期', '']}
            rows={batches.map((b) => [
              <span key="i" className={b.id === current ? 'font-semibold text-steel' : ''}>
                {b.id}
              </span>,
              batchName(b),
              b.counts.total,
              b.counts.exported + b.counts.parsed + b.counts.imported + b.counts.needs_redraw + (b.counts.unusable ?? 0),
              b.counts.parsed,
              b.counts.imported,
              b.counts.needs_redraw,
              b.counts.unusable ?? 0,
              b.exported_at ? b.exported_at.slice(0, 10) : '—',
              <Button key="o" variant="ghost" onClick={() => setSelected(b.id)}>
                開啟
              </Button>,
            ])}
          />
        ) : (
          <p className="px-5 py-4 text-[14px] text-ink-soft">還沒有批次。先選取測試集。</p>
        )}
      </Panel>

      {current && <BatchPanel key={current} batchId={current} confirmText={colors.data?.original_confirm ?? ''} onChange={() => void list.reload()} />}
    </div>
  )
}

function BatchPanel({ batchId, confirmText, onChange }: { batchId: string; confirmText: string; onChange: () => void }) {
  const detail = useApi<Batch & { items: Item[] }>(`/circling/batches/${batchId}`)
  const [withOriginal, setWithOriginal] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [folder, setFolder] = useState('')
  const [circler, setCircler] = useState('')
  const [jobs, setJobs] = useState<{ export?: string; upload?: string }>({})
  const [filter, setFilter] = useState<'review' | 'all'>('review')
  const exp = useAction((include_original: boolean, confirm: string) => api.post<{ job_id: string }>(`/circling/batches/${batchId}/export`, { include_original, confirm }))
  const upload = useAction(() => api.post<{ job_id: string }>(`/circling/batches/${batchId}/upload`, { folder, circler }))
  const importAll = useAction(() => api.post<{ imported: number }>(`/circling/batches/${batchId}/import`, {}))
  const reload = () => {
    void detail.reload()
    onChange()
  }
  if (!detail.data) return detail.error ? <ErrorNote error={detail.error} /> : <Loading />
  const b = detail.data
  const ready = b.items.filter((i) => i.status === 'parsed' && !i.parse.errors?.length).length
  const shown = filter === 'all' ? b.items : b.items.filter((i) => i.status === 'parsed' || i.status === 'needs_redraw' || (i.parse.errors?.length ?? 0) > 0)

  const doExport = async (confirm = '') => {
    const r = await exp.run(withOriginal, confirm)
    if (r) setJobs((j) => ({ ...j, export: r.job_id }))
  }

  return (
    <Panel title={`${b.id}（${batchName(b)}，${b.counts.total} 張）`}>
      <div className="grid gap-5 xl:grid-cols-2">
        <section className="space-y-3">
          <h3 className="font-medium">1. 匯出給醫師</h3>
          <p className="text-[13px] text-ink-soft">產生去識別化影像（檔名就是影像 ID）、清單.csv、圈選說明.txt 與 zip，放在 03_資料／08_匯出。已匯入的影像不會再匯出。</p>
          <label className="flex items-start gap-2 text-[14px]">
            <input type="checkbox" className="mt-1 accent-steel" checked={withOriginal} onChange={(e) => setWithOriginal(e.target.checked)} />
            <span>
              另外匯出原始超音波影像
              <span className="block text-[12px] text-ink-faint">原始影像上有姓名、病歷號：只存在受限區（01_原始封存／醫師圈選匯出），只能經醫院允許的管道交給醫師，並須在 IRB 範圍內。</span>
            </span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" icon={Download} disabled={exp.busy} onClick={() => (withOriginal ? setConfirmOpen(true) : void doExport())}>
              匯出
            </Button>
            {b.export_relpath && <OpenFolderButton kind="relpath" id={b.export_relpath} label="開啟匯出資料夾" />}
          </div>
          {b.exported_at && <p className="text-[12px] text-ink-faint">上次匯出：{b.exported_at.replace('T', ' ').slice(0, 16)}{b.include_original ? '（含原始影像）' : ''}</p>}
          {jobs.export && <JobProgress jobId={jobs.export} onDone={reload} />}
          <ErrorNote error={exp.error} />
        </section>

        <section className="space-y-3">
          <h3 className="font-medium">2. 上傳醫師傳回的圈選</h3>
          <Field label="醫師傳回的資料夾" hint="資料夾內的影像依檔名中的影像 ID 對應；子資料夾也會讀取">
            <input className={inputClass} value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="例如 C:\Users\…\醫師傳回\CB-…" />
          </Field>
          <Field label="圈選者代號（選填）" hint="例如「醫師 A」，會記在匯入的遮罩上；請用代號，不要填姓名或其他個資">
            <input className={inputClass} value={circler} maxLength={40} onChange={(e) => setCircler(e.target.value)} />
          </Field>
          <Button
            icon={FileInput}
            disabled={upload.busy || !folder.trim()}
            onClick={async () => {
              const r = await upload.run()
              if (r) setJobs((j) => ({ ...j, upload: r.job_id }))
            }}
          >
            上傳並轉換
          </Button>
          {jobs.upload && <JobProgress jobId={jobs.upload} onDone={reload} />}
          <ErrorNote error={upload.error} />
        </section>
      </div>

      <section className="mt-6 space-y-3 border-t border-line pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-medium">3. 檢查後匯入</h3>
          <div className="flex flex-wrap items-center gap-2">
            <select className={inputClass} value={filter} onChange={(e) => setFilter(e.target.value as 'review' | 'all')} aria-label="顯示">
              <option value="review">只看待檢查、錯誤、需重圈</option>
              <option value="all">全部</option>
            </select>
            <Button
              variant="primary"
              icon={PackageCheck}
              disabled={!ready || importAll.busy}
              onClick={async () => {
                if (await importAll.run()) reload()
              }}
            >
              匯入 {ready} 張
            </Button>
          </div>
        </div>
        <p className="text-[13px] text-ink-soft">
          疊圖顏色：<span style={{ color: '#5EC4D6' }}>■</span> 腎實質 <span style={{ color: '#C792EA' }}>■</span> 腎竇 <span style={{ color: '#E0B455' }}>■</span> 肝 <span style={{ color: '#9CCB6B' }}>■</span> 脾。
          「未標」的構造在訓練時忽略、不當背景；確定影像中沒有的請改成「不在影像中」。
        </p>
        <ErrorNote error={importAll.error} />
        {shown.length ? (
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            {shown.map((i) => (
              <ItemCard key={i.id} item={i} onChange={reload} />
            ))}
          </div>
        ) : (
          <p className="text-[14px] text-ink-soft">目前沒有需要檢查的項目。</p>
        )}
      </section>

      <ConfirmDialog
        open={confirmOpen}
        title="匯出原始超音波影像"
        confirmLabel="匯出"
        danger
        requireText={confirmText}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false)
          void doExport(confirmText)
        }}
      >
        <p>原始影像上有病人的姓名與病歷號。檔案只會存在受限區，檔名改成影像 ID；這次匯出會寫入稽核紀錄。</p>
        <p className="mt-2 text-ink-soft">只能經醫院允許的管道交給醫師，並須在 IRB 核准範圍內。</p>
      </ConfirmDialog>
    </Panel>
  )
}

function ItemCard({ item, onChange }: { item: Item; onChange: () => void }) {
  const [reason, setReason] = useState('')
  const patch = useAction((structures: Record<string, State>) => api.patch(`/circling/items/${item.id}`, { structures }))
  const reject = useAction(() => api.post(`/circling/items/${item.id}/reject`, { reason }))
  const [label, tone] = STATUS[item.status]
  const areas = item.parse.areas ?? {}
  const drawn: Record<string, number> = { kidney: (areas.parenchyma ?? 0) + (areas.sinus ?? 0), sinus: areas.sinus ?? 0, liver: areas.liver ?? 0, spleen: areas.spleen ?? 0 }
  const showImage = item.status === 'parsed' || item.status === 'imported'
  return (
    <div className="rounded border border-line">
      {showImage ? (
        <img src={`/api/circling/items/${item.id}/overlay`} alt={`${item.image_id} 的轉換結果`} className="w-full rounded-t bg-viewer" loading="lazy" />
      ) : (
        <div className="flex h-24 items-center justify-center rounded-t bg-paper text-[13px] text-ink-faint">尚無轉換結果</div>
      )}
      <div className="space-y-2 p-3 text-[13px]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium">
            #{item.seq}・{item.image_id}・{sideLabel(item.side)}
          </span>
          <Pill tone={tone}>{label}</Pill>
        </div>
        {item.circler && <p className="text-ink-faint">圈選者：{item.circler}</p>}
        {item.parse.errors?.map((e) => (
          <p key={e} className="text-alert">
            {e}
          </p>
        ))}
        {item.parse.warnings?.map((w) => (
          <p key={w} className="text-amber">
            {w}
          </p>
        ))}
        {item.reject_reason && item.status === 'needs_redraw' && <p className="text-alert">退回原因：{item.reject_reason}</p>}
        {item.status === 'parsed' && (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            {STRUCTURES.map(([key, name]) => {
              const value = item.structures[key] ?? 'unlabeled'
              return (
                <label key={key} className="flex items-center justify-between gap-2">
                  <span>{name}</span>
                  {drawn[key] ? (
                    <span className="text-ok">已畫</span>
                  ) : (
                    <select
                      className="rounded border border-line bg-white px-1 py-0.5"
                      value={value}
                      disabled={patch.busy}
                      onChange={async (e) => {
                        if (await patch.run({ [key]: e.target.value as State })) onChange()
                      }}
                    >
                      <option value="unlabeled">{STATE_LABEL.unlabeled}</option>
                      <option value="absent">{STATE_LABEL.absent}</option>
                    </select>
                  )}
                </label>
              )
            })}
          </div>
        )}
        {(item.status === 'parsed' || item.status === 'exported') && (item.parse.file || item.parse.errors?.length) ? (
          <div className="flex items-center gap-2 pt-1">
            <input className={`${inputClass} flex-1`} placeholder="退回原因（選填）" value={reason} onChange={(e) => setReason(e.target.value)} />
            <Button
              icon={Undo2}
              disabled={reject.busy}
              onClick={async () => {
                if (await reject.run()) onChange()
              }}
            >
              退回重圈
            </Button>
          </div>
        ) : null}
        <ErrorNote error={patch.error ?? reject.error} />
      </div>
    </div>
  )
}
