import { ArrowLeft, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Structure } from '../api'

const KIND_LABEL = { core: '基本', preset: '預設', custom: '自訂' }

interface Draft {
  code: string | null
  name: string
  meaning: string
  color: string
  line: 'solid' | 'dashed'
  kind: Structure['kind']
}

export function Colors() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Structure[]>([])
  const [palette, setPalette] = useState<string[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    const data = await api<{ structures: Structure[]; palette: string[] }>('/structures')
    setItems(data.structures)
    setPalette(data.palette)
  }, [])

  useEffect(() => {
    load().catch((e: Error) => setError(e.message))
  }, [load])

  useEffect(() => {
    if (!draft) return
    let alive = true
    api<{ warnings: string[] }>('/structures/color-check', 'POST', { color: draft.color, code: draft.code })
      .then((r) => alive && setWarnings(r.warnings))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [draft?.color, draft?.code])  // eslint-disable-line react-hooks/exhaustive-deps

  const unusedColor = () => palette.find((c) => !items.some((s) => s.color.toUpperCase() === c.toUpperCase())) ?? palette[0]
  const startNew = () => {
    setError('')
    setDraft({ code: null, name: '', meaning: '', color: unusedColor(), line: 'solid', kind: 'custom' })
  }
  const startEdit = (item: Structure) => {
    setError('')
    setDraft({ code: item.code, name: item.name, meaning: item.meaning, color: item.color, line: item.line, kind: item.kind })
  }

  const save = async () => {
    if (!draft) return
    setError('')
    try {
      const body = draft.kind === 'core' ? { color: draft.color } : { name: draft.name, meaning: draft.meaning, color: draft.color, line: draft.line }
      if (draft.code) await api(`/structures/${draft.code}`, 'PATCH', body)
      else await api('/structures', 'POST', body)
      setDraft(null)
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const setActive = async (item: Structure, active: boolean) => {
    setError('')
    try {
      await api(`/structures/${item.code}`, 'PATCH', { active })
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const remove = async (item: Structure) => {
    if (!window.confirm(`刪除「${item.name}」？`)) return
    setError('')
    try {
      await api(`/structures/${item.code}`, 'DELETE')
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const locked = draft?.kind === 'core'

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => navigate(-1)} aria-label="返回" className="rounded p-1 text-ink-soft hover:bg-paper-deep"><ArrowLeft size={18} /></button>
          <h1 className="text-xl font-medium">顏色設定</h1>
        </div>
        <button type="button" onClick={startNew} className="flex items-center gap-1.5 rounded bg-steel px-3 py-1.5 text-sm font-medium text-white hover:bg-steel-dark"><Plus size={16} />新增顏色</button>
      </header>

      {error && <p role="alert" className="mb-3 rounded bg-alert-wash px-3 py-2 text-sm text-alert">{error}</p>}

      {draft && (
        <section className="mb-4 rounded-md border border-line bg-white p-4 text-sm" aria-label={draft.code ? '修改項目' : '新增項目'}>
          <h2 className="mb-2 font-medium">{draft.code ? `修改「${draft.name}」` : '新增顏色'}</h2>
          {locked && <p className="mb-2 text-ink-soft">基本項目對應主系統，只能改顏色。</p>}
          <div className="grid gap-3">
            {!locked && (
              <>
                <label className="block">名稱
                  <input value={draft.name} maxLength={20} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="mt-1 w-full rounded border border-line px-2 py-1.5" />
                </label>
                <label className="block">意義說明
                  <textarea value={draft.meaning} maxLength={200} rows={2} onChange={(e) => setDraft({ ...draft, meaning: e.target.value })} className="mt-1 w-full resize-none rounded border border-line px-2 py-1.5" />
                </label>
              </>
            )}
            <div>
              <span>顏色</span>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {palette.map((color) => (
                  <button key={color} type="button" aria-label={`選擇顏色 ${color}`} aria-pressed={draft.color.toUpperCase() === color.toUpperCase()} onClick={() => setDraft({ ...draft, color })}
                    className={`h-7 w-7 rounded ${draft.color.toUpperCase() === color.toUpperCase() ? 'ring-2 ring-ink ring-offset-1' : ''}`} style={{ background: color }} />
                ))}
                <label className="ml-2 flex items-center gap-1.5 text-ink-soft">自選
                  <input type="color" value={draft.color.toLowerCase()} onChange={(e) => setDraft({ ...draft, color: e.target.value })} className="h-7 w-9 cursor-pointer rounded border border-line" />
                </label>
              </div>
              {warnings.map((text) => <p key={text} className="mt-1 text-amber">{text}</p>)}
            </div>
            {!locked && (
              <fieldset>
                <legend>線型</legend>
                <div className="mt-1 flex gap-4">
                  {(['solid', 'dashed'] as const).map((line) => (
                    <label key={line} className="flex items-center gap-1.5"><input type="radio" name="line" checked={draft.line === line} onChange={() => setDraft({ ...draft, line })} className="accent-steel" />{line === 'solid' ? '實線' : '虛線'}</label>
                  ))}
                </div>
              </fieldset>
            )}
            <div className="flex gap-2">
              <button type="button" onClick={save} className="rounded bg-steel px-3 py-1.5 font-medium text-white hover:bg-steel-dark">儲存顏色</button>
              <button type="button" onClick={() => setDraft(null)} className="rounded border border-line px-3 py-1.5 text-ink-soft hover:bg-paper">取消</button>
            </div>
          </div>
        </section>
      )}

      <ul className="divide-y divide-line rounded-md border border-line bg-white text-sm">
        {items.map((item, n) => (
          <li key={item.code} className={`flex items-start gap-3 p-3 ${item.active ? '' : 'opacity-60'}`}>
            <span className="w-4 pt-0.5 text-right text-ink-faint">{item.active ? n + 1 : ''}</span>
            <span className="mt-0.5 h-5 w-5 shrink-0 rounded bg-viewer" style={{ boxShadow: `inset 0 0 0 3px ${item.color}` }} />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{item.name} <span className="ml-1 text-xs font-normal text-ink-faint">{KIND_LABEL[item.kind]}{item.active ? '' : '・已停用'}{item.used ? `・已圈 ${item.used} 處` : ''}</span></p>
              <p className="text-ink-soft">{item.meaning}</p>
            </div>
            <div className="flex shrink-0 gap-2 text-steel">
              <button type="button" onClick={() => startEdit(item)} className="hover:underline">修改</button>
              {item.kind !== 'core' && (item.used
                ? <button type="button" onClick={() => setActive(item, !item.active)} className="hover:underline">{item.active ? '停用' : '啟用'}</button>
                : <button type="button" onClick={() => remove(item)} className="text-alert hover:underline">刪除</button>)}
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink-faint">資料依項目代碼儲存，改名或改顏色不影響已圈的資料。<Link to="/" className="ml-1 text-steel hover:underline">回首頁</Link></p>
    </div>
  )
}
