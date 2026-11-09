import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CheckCircle2, CircleDashed, DatabaseBackup, FolderTree, RefreshCw, UserPlus } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import type { Person } from '../../api/types'
import { Button, Field, PageHeader, Panel, Pill, Table, Tabs, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'
import { useOperator } from '../../auth/operator'
import { ConfirmDialog } from '../../components/overlays'
import { OpenFolderButton } from '../../components/OpenFolder'
import ColorMapping from './ColorMapping'
import ClinicalSettings from './ClinicalSettings'

type Tab = 'general' | 'people' | 'colors' | 'clinical' | 'folders' | 'backup' | 'audit' | 'doctor'

interface SettingsValues {
  trash_retention_days: number
  residual_check: boolean
  primary_split_id: string | null
}

function General() {
  const s = useApi<SettingsValues>('/settings')
  const splits = useApi<{ splits: { id: string; note: string; created_at: string }[] }>('/splits')
  const [draft, setDraft] = useState<Partial<SettingsValues>>({})
  const save = useAction(() => api.put<SettingsValues>('/settings', draft))
  if (!s.data) return s.error ? <ErrorNote error={s.error} /> : <Loading />
  const v = { ...s.data, ...draft }
  return (
    <Panel className="max-w-xl">
      <div className="space-y-4">
        <Field label="原始影像資料夾" hint="系統只讀取，不會修改或移動">
          <input className={inputClass} disabled value="腎超修改版\IMG_original" />
        </Field>
        <Field label="回收桶保留天數">
          <input type="number" min={1} max={365} className={inputClass} value={v.trash_retention_days} onChange={(e) => setDraft({ ...draft, trash_retention_days: Number(e.target.value) })} />
        </Field>
        <Field label="主切分" hint="醫師圈選批次、遮罩組、eGFR 比較組預設使用這個切分；沒有選時用最新的切分">
          <select className={inputClass} value={v.primary_split_id ?? ''} onChange={(e) => setDraft({ ...draft, primary_split_id: e.target.value || null })}>
            <option value="">（未設定，使用最新的切分）</option>
            {splits.data?.splits.map((sp) => (
              <option key={sp.id} value={sp.id}>
                {sp.id}
                {sp.note ? `：${sp.note}` : ''}
              </option>
            ))}
          </select>
        </Field>
        <label className="flex items-start gap-2 text-[14px]">
          <input type="checkbox" className="mt-1 accent-steel" checked={v.residual_check} onChange={(e) => setDraft({ ...draft, residual_check: e.target.checked })} />
          <span>
            匯入時檢查去識別化殘留
            <span className="block text-[13px] text-ink-faint">在去識別化後的影像再跑一次 OCR。比較慢（每張約多 1–2 秒），但建議開啟。</span>
          </span>
        </label>
        <Button
          variant="primary"
          disabled={!Object.keys(draft).length || save.busy}
          onClick={async () => {
            const r = await save.run()
            if (r) {
              s.setData(r)
              setDraft({})
            }
          }}
        >
          儲存設定
        </Button>
        <ErrorNote error={save.error} />
      </div>
    </Panel>
  )
}

interface MigrationItem {
  kind: 'run' | 'model' | 'evaluation'
  id: string
  from: string
  to: string
  note: string
}

const KIND_LABEL: Record<MigrationItem['kind'], string> = { run: '訓練', model: '模型', evaluation: '評估' }

/** 索引與資料夾整理（決策 D29）。 */
function Folders() {
  const refresh = useAction(() => api.post<{ written: string[]; skipped: string[] }>('/system/index'))
  const plan = useApi<{ items: MigrationItem[]; count: number }>('/system/folder-migration')
  const migrate = useAction(() => api.post<{ moved: number; skipped: unknown[] }>('/system/folder-migration'))
  const [confirm, setConfirm] = useState(false)
  const [done, setDone] = useState('')
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Panel title="索引（03_資料／09_索引）">
        <p className="text-[14px] text-ink-soft">
          Excel 可直接開啟的 CSV：影像、遮罩、醫師圈選批次、依任務分開的訓練與模型、評估、遮罩組、病人表上傳。不含個資：病人只用 P-編號，eGFR 只寫分組。匯入、訓練、評估、遮罩上傳後會自動更新。
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" icon={RefreshCw} disabled={refresh.busy} onClick={() => void refresh.run()}>
            更新索引
          </Button>
          <OpenFolderButton kind="index" label="開啟索引資料夾" />
          <OpenFolderButton kind="exports" label="開啟匯出資料夾" />
        </div>
        {refresh.busy && <p className="mt-3 text-[13px] text-ink-faint">更新中…</p>}
        <ErrorNote error={refresh.error} />
      </Panel>
      <Panel title="依任務整理訓練資料夾">
        <p className="text-[14px] text-ink-soft">
          把舊的訓練、模型、評估資料夾移到 eGFR／分割／回音分級 的子資料夾，資料夾名稱加上訓練名稱，並更新資料庫裡的位置。訓練中的不會搬。新的訓練會自動放在正確位置。
        </p>
        {plan.data && plan.data.count === 0 && <p className="mt-3 text-[14px] text-ok">資料夾都已在正確位置。</p>}
        {plan.data && plan.data.count > 0 && (
          <>
            <div className="mt-3">
              <Table
                minWidth={520}
                head={['種類', 'ID', '移到', '備註']}
                rows={plan.data.items.map((i) => [KIND_LABEL[i.kind], i.id, <span key="t" className="break-all text-[12px]">{i.to}</span>, i.note || '—'])}
              />
            </div>
            <div className="mt-3">
              <Button variant="primary" icon={FolderTree} disabled={migrate.busy} onClick={() => setConfirm(true)}>
                搬移 {plan.data.count} 個資料夾
              </Button>
            </div>
          </>
        )}
        {done && <p className="mt-3 text-[14px] text-ok">{done}</p>}
        <ErrorNote error={plan.error ?? migrate.error} />
        <ConfirmDialog
          open={confirm}
          title="依任務搬移資料夾"
          confirmLabel="開始搬移"
          onClose={() => setConfirm(false)}
          onConfirm={async () => {
            setConfirm(false)
            const r = await migrate.run()
            if (r) {
              setDone(`已搬移 ${r.moved} 個資料夾${r.skipped.length ? `，略過 ${r.skipped.length} 個` : ''}。`)
              void plan.reload()
            }
          }}
        >
          <p>檔案只是移動位置，不會刪除。搬移期間請不要開啟這些資料夾裡的檔案。</p>
        </ConfirmDialog>
      </Panel>
    </div>
  )
}

function People() {
  const { people, reloadPeople } = useOperator()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<Person['kind']>('physician')
  const add = useAction(() => api.post('/people', { name, kind }))
  const toggle = useAction((p: Person) => api.patch(`/people/${p.id}`, { active: !p.active }))
  return (
    <div className="space-y-5">
      <Panel title="新增">
        <p className="mb-3 text-[14px] text-ink-soft">系統不登入。這份名單用來記錄是誰做的：標註、分級、匯入、簽核報告與模型升級時，從這裡選擇。</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-56">
            <Field label="姓名">
              <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          </div>
          <div className="w-40">
            <Field label="類型">
              <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value as Person['kind'])}>
                <option value="physician">醫師</option>
                <option value="operator">操作者</option>
              </select>
            </Field>
          </div>
          <Button
            variant="primary"
            icon={UserPlus}
            disabled={!name.trim() || add.busy}
            onClick={async () => {
              const r = await add.run()
              if (r) {
                setName('')
                void reloadPeople()
              }
            }}
          >
            新增
          </Button>
        </div>
        <ErrorNote error={add.error ?? toggle.error} />
      </Panel>
      <Panel title="名單" flush>
        <Table
          minWidth={480}
          head={['姓名', '類型', '狀態', '']}
          rows={people.map((p) => [
            p.name,
            p.kind === 'physician' ? '醫師' : '操作者',
            <Pill key="s" tone={p.active ? 'ok' : 'neutral'}>
              {p.active ? '使用中' : '已停用'}
            </Pill>,
            <Button key="t" variant="ghost" onClick={async () => { await toggle.run(p); void reloadPeople() }}>
              {p.active ? '停用' : '啟用'}
            </Button>,
          ])}
        />
      </Panel>
    </div>
  )
}

function Backups() {
  const list = useApi<{ backups: { time: string; kind: string; size_bytes: number; status: string }[] }>('/backups')
  const snap = useAction(() => api.post('/backups/snapshot'))
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <Panel title="備份紀錄" flush>
        <Table minWidth={480} head={['時間', '類型', '大小', '狀態']} rows={(list.data?.backups ?? []).map((b) => [b.time, b.kind, `${(b.size_bytes / 1024 / 1024).toFixed(1)} MB`, b.status])} />
      </Panel>
      <Panel title="備份與還原">
        <ul className="mb-4 list-disc space-y-1.5 pl-5 text-[13px] text-ink-soft">
          <li>每天第一次啟動時自動快照三個資料庫，保留 14 天，存在 07_備份\每日資料庫。</li>
          <li>完整備份（含影像與模型）：先執行 stop.bat，再執行 backup.bat，選擇外接硬碟上的資料夾。</li>
          <li>原始影像含有個資，完整備份請妥善保管。</li>
        </ul>
        <Button icon={DatabaseBackup} disabled={snap.busy} onClick={async () => { await snap.run(); void list.reload() }}>
          立即建立資料庫快照
        </Button>
        <ErrorNote error={snap.error} />
      </Panel>
    </div>
  )
}

function Audit() {
  const list = useApi<{ entries: { time: string; actor: string; action: string; target_type: string; target_id: string; result: string }[] }>('/audit?limit=300')
  return (
    <Panel flush>
      <Table
        minWidth={640}
        head={['時間', '操作者', '動作', '對象', '結果']}
        rows={(list.data?.entries ?? []).map((a) => [
          a.time.slice(0, 19).replace('T', ' '),
          a.actor,
          a.action,
          a.target_id ? `${a.target_id}` : '—',
          a.result === '成功' ? a.result : <span key="r" className="text-alert">{a.result}</span>,
        ])}
      />
    </Panel>
  )
}

function Doctor() {
  const d = useApi<{ checks: { name: string; ok: boolean; note: string }[] }>('/system/doctor')
  if (!d.data) return d.error ? <ErrorNote error={d.error} /> : <Loading text="檢查中…" />
  return (
    <Panel className="max-w-2xl" flush>
      <ul className="divide-y divide-line">
        {d.data.checks.map((c) => (
          <li key={c.name} className="flex items-center gap-3 px-5 py-3 text-[14px]">
            {c.ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-label="正常" /> : <CircleDashed className="h-4 w-4 shrink-0 text-amber" aria-label="需要注意" />}
            <span className="w-32 shrink-0 font-medium">{c.name}</span>
            <span className="text-ink-soft">{c.note}</span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: '一般' },
  { id: 'people', label: '醫師與操作者名單' },
  { id: 'colors', label: '顏色對照' },
  { id: 'clinical', label: '醫師端' },
  { id: 'folders', label: '資料夾與索引' },
  { id: 'backup', label: '備份與還原' },
  { id: 'audit', label: '稽核紀錄' },
  { id: 'doctor', label: '系統檢查' },
]

export default function Settings() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab') as Tab | null
  const tab: Tab = requested && TABS.some((t) => t.id === requested) ? requested : 'general'
  return (
    <>
      <PageHeader title="設定" />
      <Tabs label="設定分類" value={tab} onChange={(t) => setParams({ tab: t })} tabs={TABS} />
      {tab === 'general' && <General />}
      {tab === 'people' && <People />}
      {tab === 'colors' && <ColorMapping />}
      {tab === 'clinical' && <ClinicalSettings />}
      {tab === 'folders' && <Folders />}
      {tab === 'backup' && <Backups />}
      {tab === 'audit' && <Audit />}
      {tab === 'doctor' && <Doctor />}
    </>
  )
}
