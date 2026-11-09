import { useEffect, useState } from 'react'
import { Plus, Search, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { Button, Field, Panel, Table, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'

interface Mapping {
  color: string
  structure: string
}

interface Found {
  colors: { color: string; pixels: number }[]
  compared: boolean
}

const STRUCTURES: [string, string][] = [
  ['kidney', '腎臟外框（含腎竇）'],
  ['sinus', '腎竇'],
  ['liver', '肝'],
  ['spleen', '脾'],
]

/** 顏色對照（決策 D21）：醫師用哪種顏色畫哪個構造。看過醫師的圖後再設定；沒設定前不能轉換彩色圈選。 */
export default function ColorMapping() {
  const settings = useApi<{ circling_colors: Mapping[]; circling_color_tolerance: number }>('/settings')
  const [rows, setRows] = useState<Mapping[]>([])
  const [tolerance, setTolerance] = useState(40)
  const [path, setPath] = useState('')
  const [saved, setSaved] = useState(false)
  const [found, setFound] = useState<Found | null>(null)
  const save = useAction(() => api.put('/settings', { circling_colors: rows, circling_color_tolerance: tolerance }))
  const detect = useAction(() => api.post<Found>('/circling/colors/detect', { path }))

  useEffect(() => {
    if (settings.data) {
      setRows(settings.data.circling_colors ?? [])
      setTolerance(settings.data.circling_color_tolerance ?? 40)
    }
  }, [settings.data])

  if (!settings.data) return settings.error ? <ErrorNote error={settings.error} /> : <Loading />
  const update = (i: number, patch: Partial<Mapping>) => {
    setSaved(false)
    setRows((r) => r.map((row, n) => (n === i ? { ...row, ...patch } : row)))
  }

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Panel title="顏色對照">
        <p className="text-[14px] text-ink-soft">
          醫師在影像上用顏色圈選。等你看過醫師傳回的圖，再在這裡指定每種顏色代表哪個構造。同一種顏色只能對應一個構造；一個構造可以有多種顏色。
        </p>
        <div className="mt-3">
          <Table
            minWidth={420}
            head={['顏色', '代表', '']}
            rows={rows.map((row, i) => [
              <span key="c" className="flex items-center gap-2">
                <input type="color" aria-label="顏色" value={row.color} onChange={(e) => update(i, { color: e.target.value })} />
                <span className="font-mono text-[13px]">{row.color}</span>
              </span>,
              <select key="s" className={inputClass} value={row.structure} onChange={(e) => update(i, { structure: e.target.value })} aria-label="代表的構造">
                {STRUCTURES.map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>,
              <Button key="d" variant="ghost" icon={Trash2} onClick={() => setRows((r) => r.filter((_, n) => n !== i))} title="刪除這一列">
                刪除
              </Button>,
            ])}
          />
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Button icon={Plus} onClick={() => setRows((r) => [...r, { color: '#ff0000', structure: 'kidney' }])}>
            新增一種顏色
          </Button>
          <Field label="顏色容許距離" hint="5–150；JPEG 或筆刷邊緣顏色不純時可調大">
            <input type="number" min={5} max={150} className={`${inputClass} w-24`} value={tolerance} onChange={(e) => setTolerance(Number(e.target.value))} />
          </Field>
          <Button
            variant="primary"
            disabled={save.busy}
            onClick={async () => {
              if (await save.run()) {
                setSaved(true)
                void settings.reload()
              }
            }}
          >
            儲存顏色對照
          </Button>
        </div>
        {saved && <p className="mt-2 text-[14px] text-ok">已儲存。之前因為沒有顏色對照而失敗的批次，請重新上傳一次。</p>}
        <ErrorNote error={save.error} />
      </Panel>
      <Panel title="從醫師的圖找出顏色">
        <p className="text-[14px] text-ink-soft">
          輸入一張醫師傳回的圖的完整路徑。檔名含影像 ID 時，系統會和原本的影像比對，只看醫師加上的筆畫。只回傳顏色與像素數，不顯示影像。
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Field label="影像檔路徑">
            <input className={`${inputClass} w-[26rem] max-w-full`} value={path} onChange={(e) => setPath(e.target.value)} />
          </Field>
          <Button
            icon={Search}
            disabled={detect.busy || !path.trim()}
            onClick={async () => {
              const r = await detect.run()
              if (r) setFound(r)
            }}
          >
            找出顏色
          </Button>
        </div>
        <ErrorNote error={detect.error} />
        {found && (
          <div className="mt-3 space-y-2">
            <p className="text-[13px] text-ink-faint">{found.compared ? '已和原本的影像比對，只列出醫師加的筆畫。' : '找不到對應的影像，列出圖中所有鮮豔的顏色。'}</p>
            {found.colors.length === 0 && <p className="text-[14px]">沒有找到明顯的彩色筆畫。</p>}
            {found.colors.map((c) => (
              <div key={c.color} className="flex items-center gap-3 text-[14px]">
                <span className="inline-block h-5 w-8 rounded border border-line" style={{ background: c.color }} />
                <span className="font-mono">{c.color}</span>
                <span className="text-ink-faint">{c.pixels.toLocaleString()} 像素</span>
                <Button variant="ghost" icon={Plus} onClick={() => setRows((r) => (r.some((x) => x.color === c.color) ? r : [...r, { color: c.color, structure: 'kidney' }]))}>
                  加入對照
                </Button>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
