import { useState } from 'react'
import { RotateCcw, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { Button, EmptyState, PageHeader, Panel, Table, Tabs } from '../../components/ui'
import { ConfirmDialog } from '../../components/overlays'
import { ErrorNote } from '../../components/live'

type Kind = '' | 'run' | 'split' | 'dataset_version' | 'mask' | 'clinical_exam'

/** 永久刪除時，每一類會刪掉哪些檔案（顯示在確認視窗）。 */
const PURGE_WHAT: Record<string, string> = {
  run: '訓練資料夾、評估、註冊的模型、預測遮罩，以及一起移入的遮罩組、特徵集、一鍵流程結果、比較組',
  split: '切分檔（還被訓練或遮罩組使用時不能刪）',
  dataset_version: '資料集版本資料夾（還被訓練或遮罩組使用時不能刪）',
  mask: '遮罩 PNG（醫師圈選匯入的遮罩被刪時，圈選項目回到「待檢查」）',
  clinical_exam: '去識別化影像、分析結果、報告 PDF、受限區的原始檔與接收暫存、研究端關於這筆檢查的臨床回饋',
}

interface Group {
  id: string
  kind: string
  kind_label: string
  label: string
  reason: string
  created_by: string
  created_at: string
}

export default function Trash() {
  const [kind, setKind] = useState<Kind>('')
  const [purging, setPurging] = useState<Group | null>(null)
  const list = useApi<{ groups: Group[] }>(`/trash${kind ? `?kind=${kind}` : ''}`, [kind])
  const restore = useAction((id: string) => api.post(`/trash/${id}/restore`))
  const purge = useAction((id: string) => api.post<{ removed: string[] }>(`/trash/${id}/purge`, { confirm: '永久刪除' }))
  const [removed, setRemoved] = useState<{ label: string; paths: string[] } | null>(null)

  return (
    <>
      <PageHeader title="回收桶" description="刪除的訓練（含註冊的模型）、資料切分、資料集版本、遮罩版本與醫師端檢查都先放在這裡，可以整組還原。永久刪除會連同資料夾裡的檔案一起刪除、不留下空資料夾，無法復原。" />
      <Tabs
        label="依類型篩選"
        value={kind}
        onChange={setKind}
        tabs={[
          { id: '', label: '全部' },
          { id: 'run', label: '訓練' },
          { id: 'split', label: '資料切分' },
          { id: 'dataset_version', label: '資料集版本' },
          { id: 'mask', label: '遮罩' },
          { id: 'clinical_exam', label: '醫師端檢查' },
        ]}
      />
      <ErrorNote error={list.error ?? restore.error ?? purge.error} />
      {removed && (
        <p role="status" className="mb-3 rounded-md bg-ok-wash px-3 py-2 text-[14px] text-ok">
          已永久刪除「{removed.label}」，刪除了 {removed.paths.length} 個檔案或資料夾{removed.paths.length ? `（${removed.paths.slice(0, 3).join('、')}${removed.paths.length > 3 ? ' 等' : ''}）` : ''}。
        </p>
      )}
      {list.data && list.data.groups.length === 0 ? (
        <EmptyState icon={Trash2} title="回收桶是空的" body="原本三個區域各自的回收桶已合併成這一個。" />
      ) : (
        <Panel flush>
          <Table
            minWidth={680}
            head={['項目', '類型', '刪除者', '時間', '']}
            rows={(list.data?.groups ?? []).map((g) => [
              g.label,
              g.kind_label,
              g.created_by,
              g.created_at.slice(0, 16).replace('T', ' '),
              <span key="a" className="flex gap-1">
                <Button variant="ghost" icon={RotateCcw} onClick={async () => { await restore.run(g.id); void list.reload() }}>
                  還原
                </Button>
                <Button variant="ghost" icon={Trash2} onClick={() => setPurging(g)}>
                  永久刪除
                </Button>
              </span>,
            ])}
          />
        </Panel>
      )}
      <ConfirmDialog
        open={Boolean(purging)}
        title="永久刪除"
        confirmLabel="永久刪除"
        danger
        requireText="永久刪除"
        onClose={() => setPurging(null)}
        onConfirm={async () => {
          if (purging) {
            const r = await purge.run(purging.id)
            if (r) setRemoved({ label: purging.label, paths: r.removed })
          }
          setPurging(null)
          void list.reload()
        }}
      >
        「{purging?.label}」會被永久刪除：資料庫紀錄與{PURGE_WHAT[purging?.kind ?? ''] ?? '資料夾裡的檔案'}一起刪除，變空的資料夾也會移除，無法復原。
        有檔案被其他程式開著（檔案總管、Excel、圖片檢視器）時會停下來，什麼都不刪；請關閉後再試。
      </ConfirmDialog>
    </>
  )
}
