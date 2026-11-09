import { useState } from 'react'
import { GitBranch, ShieldCheck, ShieldAlert } from 'lucide-react'
import { api } from '../../../api/client'
import { useAction, useApi } from '../../../api/hooks'
import type { SplitGroup, SplitInfo } from '../../../api/types'
import { Button, EmptyState, Field, Panel, Pill, Table, inputClass } from '../../../components/ui'
import { ErrorNote } from '../../../components/live'
import { ConfirmDialog } from '../../../components/overlays'

interface Leakage {
  patient_in_multiple_groups: number
  near_duplicates_count: number
  near_duplicates_across_groups: { image_a: string; image_b: string; similarity: number; groups: string[] }[]
  unassigned_patients: string[]
  passed: boolean
}

const groupLabel = (g: string) => (g === 'test' ? '固定測試集' : g === 'prospective' ? '前瞻驗證集' : g)
const STRATA = ['eGFR <15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥90']

function GroupTable({ groups }: { groups: SplitGroup[] }) {
  return (
    <Table
      minWidth={680}
      head={['組別', '病人', '影像', 'eGFR 分組病人數（<15／15–29／30–59／60–89／≥90）', 'Toshiba 比例']}
      rows={groups.map((g) => [
        <span key="g" className={g.group === 'test' ? 'font-semibold' : ''}>
          {groupLabel(g.group)}
        </span>,
        g.patients,
        g.images,
        STRATA.map((s) => g.strata[s] ?? 0).join('／'),
        g.toshiba_ratio === null ? '—' : `${Math.round(g.toshiba_ratio * 100)}%`,
      ])}
    />
  )
}

export default function SplitsTab() {
  const [seed, setSeed] = useState(42)
  const [folds, setFolds] = useState(5)
  const [testRatio, setTestRatio] = useState(0.2)
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState<{ groups: SplitGroup[]; patients: number } | null>(null)
  const [leak, setLeak] = useState<Record<string, Leakage>>({})
  const [trashing, setTrashing] = useState<string | null>(null)
  const list = useApi<{ splits: SplitInfo[] }>('/splits')
  const doPreview = useAction(() => api.post<{ groups: SplitGroup[]; patients: number }>('/splits/preview', { seed, folds, test_ratio: testRatio }))
  const create = useAction(() => api.post('/splits', { seed, folds, test_ratio: testRatio, note }))
  const extend = useAction((id: string, mode: 'folds' | 'prospective') => api.post(`/splits/${id}/extend`, { mode, note: '' }))
  const check = useAction((id: string) => api.get<Leakage>(`/splits/${id}/leakage`))
  const trash = useAction((id: string) => api.post('/trash', { kind: 'split', id, reason: '' }))

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Panel title="建立新的切分">
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="方法">
              <input className={inputClass} disabled value="依病人分層 K-fold" />
            </Field>
            <Field label="折數">
              <input type="number" min={2} max={10} className={inputClass} value={folds} onChange={(e) => setFolds(Number(e.target.value))} />
            </Field>
            <Field label="固定測試集">
              <select className={inputClass} value={testRatio} onChange={(e) => setTestRatio(Number(e.target.value))}>
                {[0.15, 0.2, 0.25].map((r) => (
                  <option key={r} value={r}>
                    {Math.round(r * 100)}% 病人
                  </option>
                ))}
              </select>
            </Field>
            <Field label="隨機種子">
              <input type="number" className={inputClass} value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
            </Field>
            <div className="sm:col-span-4">
              <Field label="備註">
                <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="例如：第一次正式切分" />
              </Field>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <Button
              onClick={async () => {
                const p = await doPreview.run()
                if (p) setPreview(p)
              }}
            >
              預覽
            </Button>
            <Button
              variant="primary"
              icon={GitBranch}
              disabled={!preview || create.busy}
              onClick={async () => {
                await create.run()
                setPreview(null)
                void list.reload()
              }}
            >
              建立切分
            </Button>
          </div>
          <ErrorNote error={doPreview.error ?? create.error} />
          {preview && (
            <div className="mt-4 overflow-hidden rounded-md border border-line">
              <GroupTable groups={preview.groups} />
            </div>
          )}
        </Panel>
        <Panel title="說明">
          <ul className="list-disc space-y-2 pl-5 text-[14px] text-ink-soft">
            <li>同一位病人的所有影像只會在一組。</li>
            <li>固定測試集先切出，之後所有實驗都不碰，最後才評估一次。</li>
            <li>新收案病人用「增量分配」：舊病人組別不變，新病人分到各折，或放進前瞻驗證集（時間上的外部驗證）。</li>
          </ul>
        </Panel>
      </div>

      <Panel title="既有切分" flush>
        <ErrorNote error={list.error ?? extend.error ?? check.error ?? trash.error} />
        {list.data && list.data.splits.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={GitBranch} title="還沒有資料切分" body="完成病人對照後，在上方預覽並建立第一個切分。" />
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {(list.data?.splits ?? []).map((s) => {
              const l = leak[s.id]
              return (
                <li key={s.id} className="space-y-2 px-5 py-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-semibold">{s.id}</span>
                    {s.parent_id && <Pill>由 {s.parent_id} 增量</Pill>}
                    <span className="text-[13px] text-ink-soft">
                      {s.method}・{s.folds} 折・種子 {s.seed}・{s.created_at.slice(0, 16).replace('T', ' ')}・{s.created_by}
                    </span>
                    <span className="ml-auto flex flex-wrap gap-1">
                      <Button
                        variant="ghost"
                        onClick={async () => {
                          const r = await check.run(s.id)
                          if (r) setLeak({ ...leak, [s.id]: r })
                        }}
                      >
                        洩漏檢查
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={async () => {
                          await extend.run(s.id, 'folds')
                          void list.reload()
                        }}
                      >
                        新病人分到各折
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={async () => {
                          await extend.run(s.id, 'prospective')
                          void list.reload()
                        }}
                      >
                        新病人放前瞻集
                      </Button>
                      <Button variant="ghost" onClick={() => setTrashing(s.id)}>
                        移入回收桶
                      </Button>
                    </span>
                  </div>
                  <p className="text-[13px] text-ink-soft">
                    {Object.entries(s.counts)
                      .sort()
                      .map(([g, n]) => `${groupLabel(g)} ${n} 位`)
                      .join('、')}
                    {s.note && `・${s.note}`}
                  </p>
                  <p className="text-[12px] text-ink-faint">雜湊 {s.sha256.slice(0, 16)}…</p>
                  {l && (
                    <div className={`rounded-md px-3 py-2 text-[14px] ${l.passed ? 'bg-ok-wash text-ok' : 'bg-amber-wash text-amber'}`}>
                      <span className="flex items-center gap-2 font-medium">
                        {l.passed ? <ShieldCheck className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
                        {l.passed ? '洩漏檢查通過' : '有需要注意的地方'}
                      </span>
                      <span className="mt-1 block">
                        病人跨組：{l.patient_in_multiple_groups}・近似重複影像跨組：{l.near_duplicates_count} 對・有影像但未分組的病人：{l.unassigned_patients.length} 位
                      </span>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Panel>
      <ConfirmDialog
        open={trashing !== null}
        title={`把 ${trashing} 移入回收桶`}
        confirmLabel="移入回收桶"
        danger
        onClose={() => setTrashing(null)}
        onConfirm={async () => {
          const id = trashing
          setTrashing(null)
          if (id && (await trash.run(id)) !== undefined) void list.reload()
        }}
      >
        <p>移入回收桶後，這個切分不會出現在清單，也不能再做增量分配。之後可以在「回收桶」還原。</p>
      </ConfirmDialog>
    </div>
  )
}
