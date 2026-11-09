import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FolderInput, ScanSearch } from 'lucide-react'
import { api } from '../../../api/client'
import { useAction, useApi } from '../../../api/hooks'
import { Button, KeyValue, Panel, Pill, Table } from '../../../components/ui'
import { ErrorNote, JobProgress, Loading } from '../../../components/live'
import { useOperator } from '../../../auth/operator'

interface InboxInfo {
  original: { exists: boolean; imported: boolean; batch_status: string | null }
  folders: { name: string; images: number; tables: string[] }[]
}

interface Preview {
  total: number
  new: number
  duplicates: number
  unreadable: number
  unknown_sizes: { size: string; count: number }[]
  by_template: { template_id: string; machine: string; size: string; count: number }[]
  patient_tables: string[]
}

export default function ImportTab() {
  const { operator } = useOperator()
  const inbox = useApi<InboxInfo>('/inbox')
  const [source, setSource] = useState<{ source: 'original' | 'inbox'; folder?: string } | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [started, setStarted] = useState<{ batch_id: string; job_id: string } | null>(null)
  const doPreview = useAction((s: typeof source) => api.post<Preview>('/imports/preview', s))
  const doStart = useAction((s: typeof source) => api.post<{ batch_id: string; job_id: string }>('/imports', s))

  const choose = async (s: NonNullable<typeof source>) => {
    setSource(s)
    setPreview(null)
    setStarted(null)
    const p = await doPreview.run(s)
    if (p) setPreview(p)
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <Panel title="選擇匯入來源">
          {inbox.loading && !inbox.data ? (
            <Loading />
          ) : inbox.error ? (
            <ErrorNote error={inbox.error} />
          ) : (
            <ul className="divide-y divide-line">
              <li className="flex flex-wrap items-center gap-3 py-3">
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">原始資料集（IMG_original）</span>
                  <span className="block text-[13px] text-ink-faint">批次 B0000。系統只讀不改，不會複製原始檔。</span>
                </span>
                {inbox.data?.original.imported ? <Pill tone="ok">已匯入</Pill> : inbox.data?.original.batch_status ? <Pill tone="amber">{inbox.data.original.batch_status}</Pill> : <Pill>尚未匯入</Pill>}
                <Button icon={ScanSearch} disabled={!inbox.data?.original.exists || doPreview.busy} onClick={() => void choose({ source: 'original' })}>
                  預覽
                </Button>
              </li>
              {inbox.data?.folders.map((f) => (
                <li key={f.name} className="flex flex-wrap items-center gap-3 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">匯入區：{f.name}</span>
                    <span className="block text-[13px] text-ink-faint">
                      {f.images} 張影像{f.tables.length ? `・病人表 ${f.tables.join('、')}` : '・沒有病人表'}
                    </span>
                  </span>
                  <Button icon={ScanSearch} disabled={doPreview.busy} onClick={() => void choose({ source: 'inbox', folder: f.name })}>
                    預覽
                  </Button>
                </li>
              ))}
              {inbox.data && inbox.data.folders.length === 0 && (
                <li className="py-3 text-[14px] text-ink-soft">
                  匯入區沒有待匯入的資料夾。新收案時，把影像與病人表放進 <code>06_匯入區\待匯入\{'{資料夾}'}</code>，再按重新整理。
                </li>
              )}
            </ul>
          )}
          <div className="mt-3">
            <Button onClick={() => void inbox.reload()}>重新整理</Button>
          </div>
        </Panel>

        {doPreview.busy && <Loading text="正在計算雜湊與比對版面範本…" />}
        <ErrorNote error={doPreview.error} />
        {preview && source && (
          <Panel title={`預覽：${source.source === 'original' ? '原始資料集' : source.folder}`}>
            <KeyValue
              items={[
                ['影像總數', preview.total],
                ['新影像', preview.new],
                ['已匯入過（會略過）', preview.duplicates],
                ['無法讀取', preview.unreadable],
                ['沒有對應範本的尺寸', preview.unknown_sizes.length ? preview.unknown_sizes.map((u) => `${u.size}（${u.count} 張）`).join('、') : '無'],
                ['病人表（匯入後自動對照這一批）', preview.patient_tables.length ? preview.patient_tables.join('、') : '無；匯入後到「病人對照」上傳'],
              ]}
            />
            <div className="mt-4 overflow-hidden rounded-md border border-line">
              <Table minWidth={420} head={['版面範本', '機型', '尺寸', '新影像']} rows={preview.by_template.map((t) => [t.template_id, t.machine, t.size, t.count])} />
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                icon={FolderInput}
                disabled={preview.new === 0 || doStart.busy || Boolean(started)}
                onClick={async () => {
                  const r = await doStart.run(source)
                  if (r) setStarted(r)
                }}
              >
                開始匯入 {preview.new} 張
              </Button>
              {!operator && <span className="text-[13px] text-amber">建議先在右上角選擇操作者，紀錄才會寫明是誰匯入的。</span>}
            </div>
            <ErrorNote error={doStart.error} />
          </Panel>
        )}

        {started && (
          <Panel title={`匯入批次 ${started.batch_id}`}>
            <JobProgress jobId={started.job_id} onDone={() => void inbox.reload()} />
            <Link to={`/research/datasets/imports/${started.batch_id}`} className="mt-3 inline-block text-steel underline">
              查看匯入報表
            </Link>
          </Panel>
        )}
      </div>

      <Panel title="匯入時會做的事">
        <ol className="list-decimal space-y-2 pl-5 text-[14px] text-ink-soft">
          <li>以 SHA-256 判斷重複；已匯入過的影像會略過，所以中斷後重跑等於接續。</li>
          <li>依影像尺寸套用版面範本。</li>
          <li>OCR 讀出年齡、性別、掃描參數、技師量的 Dist A／B、側別；標頭原文讀完即丟棄。</li>
          <li>用深度尺刻度換算每像素 mm，並用數字交叉確認。</li>
          <li>遮蓋文字區；caliper 在模型用影像中修補、在灰階計算用影像中標為無效。</li>
          <li>在去識別化後的影像再跑一次 OCR，找個資殘留；有問題的列入「待人工確認」。</li>
          <li>改用隨機 ID 存檔；原始檔名只存在受限的對照表。</li>
          <li>資料夾裡若有病人表（CSV／XLSX），匯入完自動對照這一批影像；分不出來的列入「病人對照」的人工確認。</li>
        </ol>
        <p className="mt-3 text-[13px] text-ink-faint">975 張影像大約需要 30–90 分鐘（OCR 在 CPU 上執行，電腦同時執行其他程式會更慢）。匯入期間可以離開這一頁，進度在「任務紀錄」。</p>
      </Panel>
    </div>
  )
}
