import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, KeyRound, PackageOpen, Play, Square, Wifi } from 'lucide-react'
import { Button, EmptyState, KeyValue, PageHeader, Panel, Pill, Table, Tabs, inputClass } from '../../components/ui'
import { api } from '../../api/client'
import { useAction, useApi, usePolling } from '../../api/hooks'
import { when, type ReceiverStatus } from '../../api/clinical'
import { OpenFolderButton } from '../../components/OpenFolder'

type Mode = 'demo' | 'device'

const ITEM_LABEL: Record<string, string> = { ok: '完成', received: '已收到', duplicate: '重複（略過）', layout_mismatch: '版面不符', residual: '去識別化有殘留', failed: '失敗' }

function DemoReceiver() {
  const { data, error, reload } = useApi<ReceiverStatus>('/clinical/receiver')
  usePolling(reload, 4000)
  const [address, setAddress] = useState('')
  const [pack, setPack] = useState<{ folder: string; patients: number; images: number } | null>(null)
  const start = useAction(async () => {
    await api.post('/clinical/receiver/start', { address: address || data?.suggested || null })
    await reload()
  })
  const stop = useAction(async () => {
    await api.post('/clinical/receiver/stop')
    await reload()
  })
  const code = useAction(async () => {
    await api.post('/clinical/receiver/code')
    await reload()
  })
  const makePack = useAction(async () => setPack(await api.post('/clinical/demo-pack', { patients: 6 })))
  const session = data?.session
  const err = start.error ?? stop.error ?? code.error ?? makePack.error ?? error

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        {err && <p className="rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{err.message}</p>}
        {session ? (
          <Panel title="接收中" aside={<Pill tone="ok">雙機接收進行中</Pill>}>
            <p className="text-ink-soft">在 A 電腦（傳送端）的瀏覽器打開下面的網址，輸入配對碼後就可以傳送影像。</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-line bg-paper px-4 py-3">
                <p className="text-[13px] text-ink-faint">A 電腦要打開的網址</p>
                <p className="mt-1 break-all font-mono text-[20px] font-semibold text-steel-dark">{session.url}</p>
              </div>
              <div className="rounded-lg border border-line bg-paper px-4 py-3">
                <p className="text-[13px] text-ink-faint">配對碼（{when(session.code_expires_at).slice(11)} 前有效）</p>
                <p className="mt-1 font-mono text-[32px] font-bold tracking-[0.3em]">{session.code ?? '——'}</p>
              </div>
            </div>
            <div className="mt-4">
              <KeyValue
                items={[
                  ['憑證指紋', <span key="f" className="break-all font-mono text-[12px]">{session.fingerprint}</span>],
                  ['開始時間', when(session.started_at)],
                ]}
              />
              <p className="mt-2 text-[13px] text-ink-faint">
                瀏覽器會顯示「連線不是私人連線」：這是自簽憑證，請比對上面的指紋前幾碼後選「繼續前往」。IP 改變（換網路）後要重新開始接收。
              </p>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button icon={KeyRound} disabled={code.busy} onClick={() => void code.run()}>換一個配對碼</Button>
              <Button icon={Square} disabled={stop.busy} onClick={() => void stop.run()}>停止接收</Button>
            </div>
          </Panel>
        ) : (
          <Panel title="開始接收">
            <p className="text-ink-soft">兩台筆電連同一個 Wi-Fi 或手機熱點。這台（B，醫師端）開始接收後，畫面會顯示網址和 6 位數配對碼。</p>
            {data && !data.interfaces.length ? (
              <p className="mt-3 rounded-md bg-amber-wash px-3 py-2 text-[14px] text-amber">找不到私人網段的網路介面：請先連上 Wi-Fi 或手機熱點，再重新整理。</p>
            ) : (
              <label className="mt-4 block max-w-sm">
                <span className="text-[14px] font-medium">網路介面</span>
                <select className={`${inputClass} mt-1.5`} value={address || data?.suggested || ''} onChange={(e) => setAddress(e.target.value)}>
                  {!data?.suggested && <option value="">請選擇</option>}
                  {data?.interfaces.map((i) => (
                    <option key={i.address} value={i.address}>
                      {i.address}（{i.name}）
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="mt-4">
              <Button variant="primary" icon={Play} disabled={start.busy || !data?.interfaces.length || !(address || data?.suggested)} onClick={() => void start.run()}>
                {start.busy ? '啟動中…' : '開始接收'}
              </Button>
            </div>
            {data && <p className="mt-3 text-[13px] text-ink-faint">{data.firewall_hint}</p>}
          </Panel>
        )}

        <Panel title="傳送紀錄" flush>
          {data?.batches.length ? (
            <Table
              minWidth={640}
              head={['傳送', '開始', '張數', '結果', '檢查', '摘要']}
              rows={data.batches.map((b) => [
                <span key="b" className="font-mono text-[13px]">{b.id}</span>,
                when(b.created_at),
                b.items,
                <span key="c" className="flex flex-wrap gap-1">
                  {b.status === 'receiving' && <Pill tone="steel">傳送中</Pill>}
                  {Object.entries(b.counts).map(([k, v]) => (
                    <Pill key={k} tone={k === 'ok' ? 'ok' : k === 'received' ? 'steel' : k === 'duplicate' ? 'neutral' : 'amber'}>
                      {ITEM_LABEL[k] ?? k} {v}
                    </Pill>
                  ))}
                </span>,
                b.exam_id ? (
                  <Link key="e" to={`/clinical/exams/${b.exam_id}`} className="text-steel hover:underline">
                    {b.exam_id}
                  </Link>
                ) : (
                  '—'
                ),
                <a key="s" href={`/api/clinical/receiver/batches/${b.id}/summary`} className="inline-flex items-center gap-1 text-[13px] text-steel hover:underline">
                  <Download className="h-3.5 w-3.5" aria-hidden />
                  下載
                </a>,
              ])}
            />
          ) : (
            <p className="px-5 py-6 text-ink-soft">還沒有傳送紀錄。</p>
          )}
        </Panel>
      </div>

      <div className="space-y-5">
        <Panel title="示範影像包">
          <p className="text-[14px] text-ink-soft">
            從主要切分的<strong>測試集</strong>病人挑去識別化影像（每側 1 張），附「示範清單.json」（病例代碼、側別、像素間距、年齡、性別、糖尿病；不含 eGFR）。
          </p>
          <p className="mt-2 text-[13px] text-amber">使用前請先確認醫院同意用去識別化影像展示。</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button icon={PackageOpen} disabled={makePack.busy} onClick={() => void makePack.run()}>
              {makePack.busy ? '匯出中…' : '匯出示範影像包'}
            </Button>
            {pack && <OpenFolderButton kind="relpath" id={pack.folder} />}
          </div>
          {pack && <p className="mt-2 text-[13px] text-ok">已匯出 {pack.patients} 位病人、{pack.images} 張影像：{pack.folder}</p>}
        </Panel>
        <Panel title="A 電腦的步驟">
          <ol className="list-decimal space-y-1.5 pl-5 text-[14px] text-ink-soft">
            <li>把示範影像包複製到 A 電腦。</li>
            <li>用瀏覽器打開左邊的網址，略過憑證警告。</li>
            <li>輸入配對碼。</li>
            <li>匯入「示範清單.json」，把 PNG 拖進頁面，按「傳送」。</li>
            <li>回到這台電腦的「工作清單」看分析結果。</li>
          </ol>
          <p className="mt-3 text-[13px] text-ink-faint">詳細步驟見 01_計畫與文件/雙機展示步驟.md。</p>
        </Panel>
      </div>
    </div>
  )
}

export default function Acquisition() {
  const [mode, setMode] = useState<Mode>('demo')
  return (
    <>
      <PageHeader title="影像接收" description="收到的影像會先存進受限區，再去識別化、建立檢查並自動分析；原始檔不會顯示在任何頁面。" />
      <Tabs
        label="接收模式"
        value={mode}
        onChange={setMode}
        tabs={[
          { id: 'demo', label: '雙機展示' },
          { id: 'device', label: '超音波設備' },
        ]}
      />
      {mode === 'demo' ? (
        <DemoReceiver />
      ) : (
        <EmptyState
          icon={Wifi}
          title="超音波設備模式尚未啟用"
          body="直接從超音波機器收圖時會保存姓名與病歷號（受限欄位），需要先取得 IRB 同意與醫院資訊單位核准，並確認設備的傳輸方式（DICOM 或資料夾）。目前只完成資料表與設定的基礎（設定 › 醫師端的「超音波設備模式」仍不能開啟）。展示請用「雙機展示」。"
        />
      )}
    </>
  )
}
