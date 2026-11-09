import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, FolderInput, RefreshCw, Sparkles, Trash2, Wand2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { draftSourceLabel } from '../../api/ml'
import { Button, Field, Panel, Pill, Table, inputClass } from '../../components/ui'
import { ErrorNote, JobProgress } from '../../components/live'
import { ConfirmDialog } from '../../components/overlays'

interface Stats {
  by_source: Record<string, { drafts: number; accepted: number; edited: number; rejected: number; pending: number; acceptance_rate: number | null }>
  regenerable: number
}

const LEGACY_HINT = 'C:\\Users\\chenp\\Desktop\\put\\IMG\\IMG_Mask'

/** 草稿準備：舊程式遮罩（含腎竇分割）→ 規則產生肝／脾；MedSAM 是選用的比較工具。 */
export default function MaskDrafts() {
  const stats = useApi<Stats>('/annotation/drafts/stats')
  const weights = useApi<{ weights: { name: string; downloaded: unknown }[] }>('/pretrained')
  const medsamReady = Boolean(weights.data?.weights.find((w) => w.name === 'medsam-vit-base')?.downloaded)
  const [folder, setFolder] = useState(LEGACY_HINT)
  const [jobs, setJobs] = useState<Record<string, string>>({})
  const [regenOpen, setRegenOpen] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [deleteOpen, setDeleteOpen] = useState(false)
  const remove = useAction((sources: string[]) => api.post<{ moved: number }>('/annotation/drafts/delete', { sources }))
  // 會被刪除的：待確認、被退回、之後被人工修改過的草稿；已接受的不動
  const deletable = (k: string) => {
    const s = stats.data?.by_source[k]
    return s ? s.pending + s.rejected + s.edited : 0
  }
  const pickedCount = picked.reduce((n, k) => n + deletable(k), 0)
  const run = useAction((key: string, url: string, body?: unknown) => api.post<{ job_id: string }>(url, body).then((r) => ({ key, ...r })))
  const go = async (key: string, url: string, body?: unknown) => {
    const r = await run.run(key, url, body)
    if (r) setJobs((j) => ({ ...j, [r.key]: r.job_id }))
  }
  const done = () => {
    void stats.reload()
    void weights.reload()
  }

  const step = (n: number, title: string, body: string, action: React.ReactNode, key: string) => (
    <li className="space-y-2 border-b border-line py-4 last:border-0">
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-steel-wash text-[14px] font-semibold text-steel">{n}</span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{title}</p>
          <p className="text-[13px] text-ink-soft">{body}</p>
        </div>
      </div>
      <div className="pl-10">{action}</div>
      {jobs[key] && (
        <div className="pl-10">
          <JobProgress jobId={jobs[key]} onDone={done} />
        </div>
      )}
    </li>
  )

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel title="遮罩草稿（其他來源）">
        <p className="text-[14px] text-ink-soft">
          M2.5 起，正式的遮罩由醫師在系統外圈選後上傳（
          <Link to="/research/annotation?tab=circling" className="text-steel underline">
            標註與回饋 › 醫師圈選
          </Link>
          ）。下面的舊程式匯入、規則肝／脾、MedSAM 只保留作參考，不建議再使用；主切分測試集的影像不會產生任何草稿。
        </p>
        <details className="mt-3 rounded border border-line">
          <summary className="cursor-pointer px-4 py-2 text-[14px] font-medium">其他草稿來源（不建議）</summary>
          <div className="px-4 pb-4">
        <ol>
          {step(
            1,
            '匯入舊程式遮罩',
            '整顆腎的輪廓換回原圖座標，並自動分出中央較亮的腎竇，存成草稿。碰到裁切邊緣、邊界對不上或分不出腎竇的會標成「需要確認」。只讀取，不改動原檔。',
            <div className="flex flex-wrap items-end gap-2">
              <Field label="舊遮罩資料夾（IMG_Mask）">
                <input className={`${inputClass} w-[28rem] max-w-full`} value={folder} onChange={(e) => setFolder(e.target.value)} />
              </Field>
              <Button icon={FolderInput} disabled={run.busy || !folder.trim()} onClick={() => void go('legacy', '/annotation/drafts/legacy', { folder })}>
                匯入
              </Button>
            </div>,
            'legacy',
          )}

          {step(
            2,
            '產生肝／脾草稿',
            '右腎找肝、左腎找脾：緊貼腎臟、紋理均勻的區域。太暗、太亮、太雜亂或和皮質深度差太多的標成「不可靠」。側別未知的影像會跳過。',
            <Button icon={Wand2} disabled={run.busy} onClick={() => void go('organs', '/annotation/drafts/organs')}>
              產生草稿
            </Button>,
            'organs',
          )}
          {step(
            3,
            'MedSAM 比較（選用）',
            '用舊遮罩當框讓 MedSAM 重畫。在 60 張真實影像上，它圈出的面積中位數只有舊遮罩的 53%，多半只圈到中央較亮的部分、漏掉皮質，所以不建議當作主要草稿；只在想比較時使用。需要顯示卡。',
            medsamReady ? (
              <Button icon={Sparkles} disabled={run.busy} onClick={() => void go('medsam', '/annotation/drafts/medsam')}>
                執行比較
              </Button>
            ) : (
              <Button icon={Download} disabled={run.busy} onClick={() => void go('medsam', '/pretrained/medsam-vit-base/download')}>
                先下載 MedSAM 權重（約 375 MB）
              </Button>
            ),
            'medsam',
          )}
        </ol>
        <div className="mt-2 rounded border border-line bg-paper p-4">
          <p className="font-medium">規則更新後：重新產生未確認的草稿</p>
          <p className="mt-1 text-[13px] text-ink-soft">
            匯入與產生草稿會跳過已經有草稿的影像，所以規則改進後，舊草稿不會自動更新。這裡會把還沒確認的舊程式與肝／脾草稿整批移入回收桶，再依序重做步驟 1 與 2。已經接受、修改或退回的不會動；在回收桶可以一次還原。
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button icon={RefreshCw} disabled={run.busy || !folder.trim() || !stats.data?.regenerable} onClick={() => setRegenOpen(true)}>
              用新規則重新產生
            </Button>
            <span className="text-[13px] text-ink-faint">可以重新產生：{stats.data?.regenerable ?? '—'} 份</span>
          </div>
          {jobs.regenerate && (
            <div className="mt-3">
              <JobProgress jobId={jobs.regenerate} onDone={done} />
            </div>
          )}
        </div>
          </div>
        </details>
        <ErrorNote error={run.error} />
        <ConfirmDialog
          open={deleteOpen}
          title="刪除草稿"
          confirmLabel="移入回收桶"
          danger
          onClose={() => setDeleteOpen(false)}
          onConfirm={async () => {
            setDeleteOpen(false)
            const r = await remove.run(picked)
            if (r) {
              setPicked([])
              done()
            }
          }}
        >
          <p>
            {picked.map((k) => draftSourceLabel[k] ?? k).join('、')}：共 {pickedCount} 份草稿（待確認、被退回、已被人工修改的）會移入回收桶，每個來源一組，可以一次還原；要永久刪除請到「回收桶」。
          </p>
          <p className="mt-2 text-ink-soft">已經接受的草稿與人工畫的遮罩不受影響。刪除後，可以在步驟 1、2 重新產生。</p>
        </ConfirmDialog>
        <ConfirmDialog
          open={regenOpen}
          title="用新規則重新產生草稿"
          confirmLabel="移入回收桶並重新產生"
          onClose={() => setRegenOpen(false)}
          onConfirm={() => {
            setRegenOpen(false)
            void go('regenerate', '/annotation/drafts/regenerate', { folder })
          }}
        >
          <p>{stats.data?.regenerable ?? 0} 份未確認的草稿會移入回收桶（同一組，可以一次還原），再用新規則從「{folder}」重新匯入舊遮罩並產生肝／脾草稿。</p>
          <p className="mt-2 text-ink-soft">已經接受、修改或退回的草稿不受影響。</p>
        </ConfirmDialog>
      </Panel>
      <Panel title="草稿確認進度" flush>
        {stats.data && Object.keys(stats.data.by_source).length ? (
          <>
            <Table
              minWidth={360}
              head={['', '來源', '草稿', '接受', '修改', '退回', '接受率']}
              rows={Object.entries(stats.data.by_source).map(([k, s]) => [
                <input
                  key="c"
                  type="checkbox"
                  className="h-4 w-4"
                  aria-label={`選取${draftSourceLabel[k] ?? k}`}
                  checked={picked.includes(k)}
                  disabled={deletable(k) === 0}
                  onChange={(e) => setPicked((p) => (e.target.checked ? [...p, k] : p.filter((x) => x !== k)))}
                />,
                draftSourceLabel[k] ?? k,
                s.drafts,
                s.accepted,
                s.edited,
                s.rejected,
                s.acceptance_rate == null ? '—' : `${Math.round(s.acceptance_rate * 100)}%`,
              ])}
            />
            <div className="flex items-center gap-3 px-5 pt-3">
              <Button icon={Trash2} disabled={!picked.length || remove.busy} onClick={() => setDeleteOpen(true)}>
                刪除勾選的草稿
              </Button>
              {picked.length > 0 && <span className="text-[13px] text-ink-faint">{pickedCount} 份</span>}
            </div>
            <div className="px-5">
              <ErrorNote error={remove.error} />
            </div>
          </>
        ) : (
          <p className="px-5 py-4 text-[14px] text-ink-soft">還沒有草稿。</p>
        )}
        <div className="px-5 py-4">
          <Link to="/research/annotation?tab=drafts" className="text-steel underline">
            前往「草稿確認」逐張接受或修改
          </Link>
          <p className="mt-2 text-[12px] text-ink-faint">
            <Pill tone="amber">提醒</Pill> 固定測試集的分割評估只接受人工確認過的遮罩。
          </p>
        </div>
      </Panel>
    </div>
  )
}
