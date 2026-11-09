import { useState } from 'react'
import { Link } from 'react-router-dom'
import { History, Lock } from 'lucide-react'
import { api } from '../../../api/client'
import { useAction, useApi } from '../../../api/hooks'
import type { Batch } from '../../../api/types'
import { Button, EmptyState, Field, Panel, Pill, Table, inputClass } from '../../../components/ui'
import { ErrorNote } from '../../../components/live'

interface Version {
  id: string
  note: string
  image_count: number
  patient_count: number
  sha256: string
  created_by: string
  created_at: string
}

export function VersionsTab() {
  const [note, setNote] = useState('')
  const list = useApi<{ versions: Version[] }>('/dataset-versions')
  const create = useAction(() => api.post('/dataset-versions', { note }))
  return (
    <div className="space-y-5">
      <Panel title="凍結目前狀態">
        <p className="mb-3 text-[14px] text-ink-soft">把目前「可用且已對到病人」的影像、最新的遮罩版本與分級標註凍結成一個版本。訓練紀錄會記下用的是哪一版，確保結果可以重現。</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-80 max-w-full">
            <Field label="說明">
              <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="例如：完成第一批遮罩標註" />
            </Field>
          </div>
          <Button
            variant="primary"
            icon={Lock}
            disabled={create.busy}
            onClick={async () => {
              await create.run()
              setNote('')
              void list.reload()
            }}
          >
            凍結為新版本
          </Button>
        </div>
        <ErrorNote error={create.error} />
      </Panel>
      <Panel flush>
        {list.data && list.data.versions.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={History} title="還沒有資料集版本" body="完成匯入與病人對照後就可以凍結第一個版本。" />
          </div>
        ) : (
          <Table
            minWidth={640}
            head={['版本', '影像', '病人', '說明', '建立者', '時間', '雜湊']}
            rows={(list.data?.versions ?? []).map((v) => [
              <span key="v" className="font-semibold">
                {v.id}
              </span>,
              v.image_count,
              v.patient_count,
              v.note || '—',
              v.created_by,
              v.created_at.slice(0, 16).replace('T', ' '),
              <code key="h" className="text-[12px] text-ink-faint">
                {v.sha256.slice(0, 12)}
              </code>,
            ])}
          />
        )}
      </Panel>
    </div>
  )
}

const statusTone = (s: string) => (s === 'completed' ? 'ok' : s === 'running' ? 'steel' : s === 'failed' ? 'alert' : 'neutral')
const statusText: Record<string, string> = { completed: '完成', running: '執行中', failed: '失敗', stopped: '已停止' }

export function BatchesTab() {
  const list = useApi<{ batches: Batch[] }>('/imports')
  return (
    <Panel flush>
      <ErrorNote error={list.error} />
      {list.data && list.data.batches.length === 0 ? (
        <div className="p-5">
          <EmptyState icon={History} title="還沒有匯入紀錄" body="到「匯入」分頁開始第一次匯入。" />
        </div>
      ) : (
        <Table
          minWidth={720}
          head={['批次', '來源', '狀態', '已匯入', '待確認', '重複略過', '執行者', '時間']}
          rows={(list.data?.batches ?? []).map((b) => [
            <Link key="b" to={`/research/datasets/imports/${b.id}`} className="font-semibold text-steel hover:underline">
              {b.id}
            </Link>,
            b.source_label,
            <Pill key="s" tone={statusTone(b.status)}>
              {statusText[b.status] ?? b.status}
            </Pill>,
            b.counts.imported ?? '—',
            b.counts.pending_review ?? '—',
            b.counts.duplicates ?? '—',
            b.created_by,
            b.created_at.slice(0, 16).replace('T', ' '),
          ])}
        />
      )}
    </Panel>
  )
}
