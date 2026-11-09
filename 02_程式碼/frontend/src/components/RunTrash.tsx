import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { api } from '../api/client'
import { useAction } from '../api/hooks'
import type { RunInfo } from '../api/ml'
import { Button } from './ui'
import { ConfirmDialog } from './overlays'
import { ErrorNote } from './live'

const ACTIVE = ['queued', 'running']

/** 訓練紀錄表的勾選（排隊中、訓練中的不能選）：回傳第一欄的全選框、每列的勾選框，以及移入回收桶的按鈕列。 */
export function useRunSelection(runs: RunInfo[], onTrashed: () => void) {
  const [picked, setPicked] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const trash = useAction((ids: string[]) => api.post<{ group_id: string; runs: number; models: string[] }>('/training/runs/trash', { run_ids: ids }))
  const selectable = runs.filter((r) => !ACTIVE.includes(r.status)).map((r) => r.id)
  const shown = picked.filter((id) => selectable.includes(id))
  const allPicked = selectable.length > 0 && selectable.every((id) => shown.includes(id))

  const headCell: ReactNode = (
    <input
      key="all"
      type="checkbox"
      className="h-4 w-4"
      aria-label="全選訓練"
      checked={allPicked}
      disabled={!selectable.length}
      onChange={(e) => setPicked(e.target.checked ? selectable : [])}
    />
  )
  const rowCell = (r: RunInfo): ReactNode => (
    <input
      key="c"
      type="checkbox"
      className="h-4 w-4"
      aria-label={`選取 ${r.id}`}
      checked={shown.includes(r.id)}
      disabled={ACTIVE.includes(r.status)}
      onChange={(e) => setPicked((p) => (e.target.checked ? [...p, r.id] : p.filter((x) => x !== r.id)))}
    />
  )
  const bar: ReactNode = (
    <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
      <Button icon={Trash2} disabled={!shown.length || trash.busy} onClick={() => setOpen(true)}>
        移入回收桶{shown.length ? `（${shown.length}）` : ''}
      </Button>
      <span className="text-[13px] text-ink-faint">排隊中、訓練中的不能選；回收桶可以還原，永久刪除時才會刪掉資料夾</span>
      <ErrorNote error={trash.error} />
      <ConfirmDialog
        open={open}
        title="訓練移入回收桶"
        confirmLabel="移入回收桶"
        onClose={() => setOpen(false)}
        onConfirm={async () => {
          setOpen(false)
          if (await trash.run(shown)) {
            setPicked([])
            onTrashed()
          }
        }}
      >
        <p>{shown.length} 個訓練（{shown.slice(0, 5).join('、')}{shown.length > 5 ? ' 等' : ''}）會移入回收桶，清單不再顯示；用這些訓練註冊的模型、分割訓練產生的遮罩組與特徵集也會一起移入。比較組的訓練全部移入時，比較組也一起移入。</p>
        <p className="mt-2 text-ink-soft">
          在 <Link to="/trash" className="text-steel underline">回收桶</Link> 可以整組還原。永久刪除時，會一併刪除訓練資料夾、評估資料夾、模型資料夾、預測遮罩、遮罩組、特徵集、用這些模型跑的一鍵流程結果，並移除變空的資料夾，無法復原。
          其他訓練還用到這些遮罩組或特徵集時，請一起勾選。eGFR 比較組裡被刪除的格子會顯示「找不到」；已經做過的固定測試集評估仍然算數，測試集不會因此解鎖。
        </p>
      </ConfirmDialog>
    </div>
  )
  return { headCell, rowCell, bar }
}
