import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Ban, FileClock, FileDown, PenLine, Printer, Save, Send, ShieldCheck } from 'lucide-react'
import { AiBadge, BackLink, Button, Field, Panel, Pill, Timeline, inputClass } from '../../components/ui'
import { Drawer } from '../../components/overlays'
import { useOperator } from '../../auth/operator'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import { CANDIDATE_LABEL, SIDE_LABEL, pct, reportTone, when, type Report, type ReportPayload, type ReportSide, type Side } from '../../api/clinical'

const MANUAL: { key: keyof ReportSide; label: string; hint: string }[] = [
  { key: 'corticomedullary', label: '皮髓質分界', hint: '例如：清楚／模糊' },
  { key: 'hydronephrosis', label: '積水', hint: '例如：無／輕度' },
  { key: 'stones', label: '結石', hint: '' },
  { key: 'cysts', label: '囊腫', hint: '' },
]
const STATUS_NAME = { draft: '草稿', pending: '待簽核', signed: '已簽核', void: '已作廢' } as const

export default function ReportEditor() {
  const { examId } = useParams()
  const [params] = useSearchParams()
  const { physicians } = useOperator()
  const [reportId, setReportId] = useState(params.get('id'))
  useEffect(() => {
    if (!reportId && examId) void api.post<{ id: string }>(`/clinical/exams/${examId}/report`).then((r) => setReportId(r.id)).catch(() => undefined)
  }, [reportId, examId])
  const { data: report, error, reload, setData } = useApi<Report>(reportId ? `/clinical/reports/${reportId}` : null, [reportId])
  const [draft, setDraft] = useState<ReportPayload | null>(null)
  const [signer, setSigner] = useState('')
  const [confirmName, setConfirmName] = useState('')
  const [ack, setAck] = useState<string[]>([])
  const [history, setHistory] = useState(false)
  const [viewing, setViewing] = useState<{ version: number; payload: ReportPayload } | null>(null)
  const [voidReason, setVoidReason] = useState('')
  const [pdfStamp, setPdfStamp] = useState(0)
  useEffect(() => {
    if (report) setDraft(report.payload)
  }, [report])

  const editable = report?.status === 'draft' || report?.status === 'pending'
  const run = useAction(async (fn: () => Promise<Report | unknown>) => {
    const r = await fn()
    if (r && typeof r === 'object' && 'payload' in (r as Report)) setData(r as Report)
    else await reload()
    setPdfStamp(Date.now())
  })
  if (error && !report) return <p className="rounded-md bg-alert-wash px-3 py-2 text-alert">{error.message}</p>
  if (!report || !draft) return <p className="text-ink-soft">讀取中…</p>

  const setSide = (side: Side, key: keyof ReportSide, value: string) =>
    setDraft({ ...draft, sides: { ...draft.sides, [side]: { ...(draft.sides[side] as ReportSide), [key]: value } } })
  const save = (submit: boolean) => run.run(() => api.put<Report>(`/clinical/reports/${report.id}`, { payload: draft, submit }))
  const sign = () => run.run(() => api.post<Report>(`/clinical/reports/${report.id}/sign`, { physician: signer, confirm_name: confirmName, acknowledged: ack }))
  const dirty = JSON.stringify(draft) !== JSON.stringify(report.payload)
  const checklistDone = report.checklist.every((c) => ack.includes(c.key))
  const pdfUrl = `/api/clinical/reports/${report.id}/pdf?v=${report.pdf.version}-${pdfStamp}`

  return (
    <>
      <BackLink to={`/clinical/exams/${report.exam_id}`}>回檢查工作區</BackLink>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-[24px] font-bold leading-tight">
          報告 {report.id}
          <span className="ml-3 text-[16px] font-normal text-ink-soft">{report.case_code}・{report.exam_id}・第 {report.version} 版</span>
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={reportTone[report.status]}>{report.status_label}</Pill>
          <Button icon={FileClock} variant="ghost" onClick={() => setHistory(true)}>版本歷史</Button>
          {report.status !== 'void' && <Button icon={FileDown} disabled={run.busy} onClick={() => void run.run(() => api.post(`/clinical/reports/${report.id}/pdf`))}>產生 PDF</Button>}
          {report.pdf.exists && (
            <>
              <a href={pdfUrl} target="_blank" rel="noreferrer" className="inline-flex min-h-[38px] items-center gap-2 rounded-md border border-line bg-white px-3.5 text-[14px] hover:bg-paper">開啟 PDF</a>
              <Button icon={Printer} onClick={() => { const w = window.open(pdfUrl); w?.addEventListener('load', () => w.print()) }}>列印</Button>
            </>
          )}
        </div>
      </div>
      {report.candidate && <p className="mb-4 rounded-md border border-amber/30 bg-amber-wash px-3 py-2 text-[14px] text-amber">AI 結果來自候選模型：{CANDIDATE_LABEL}。PDF 上也會標示。</p>}
      {report.status === 'void' && <p className="mb-4 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">已作廢：{report.void_reason}。PDF 已覆蓋成作廢版。</p>}
      {run.error && <p className="mb-4 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{run.error.message}</p>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Panel title="eGFR（AI 預測，整次檢查）">
            {draft.egfr ? (
              <p className="text-[14px]">P(eGFR&lt;60) <strong className="text-[18px]">{pct(draft.egfr.p_lt60)}</strong>・預測類別 {draft.egfr.predicted} <AiBadge state={draft.ai_confirmed ? 'confirmed' : 'suggested'} /></p>
            ) : (
              <p className="text-[14px] text-ink-soft">沒有 eGFR 結果。</p>
            )}
          </Panel>
          {(['right', 'left'] as Side[]).map((side) => {
            const s = draft.sides[side]
            if (!s) return null
            return (
              <Panel key={side} title={SIDE_LABEL[side]}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="腎長（mm）" hint={s.length_ai !== null ? `AI ${s.length_ai.toFixed(1)} mm` : 'AI 沒有量到（缺像素間距或分割失敗）'}>
                    <span className="flex items-center gap-2">
                      <input className={inputClass} inputMode="decimal" disabled={!editable} value={s.length_mm ?? ''} onChange={(e) => setSide(side, 'length_mm', e.target.value)} />
                      {(s.length_ai !== null || s.length_mm !== s.length_ai) && <AiBadge state={s.length_mm !== s.length_ai ? 'edited' : draft.ai_confirmed ? 'confirmed' : 'suggested'} />}
                    </span>
                  </Field>
                  <Field label="回音分級" hint={s.grade_ai ? `AI ${s.grade_ai}` : '分析方案沒有分級模型，請醫師判讀'}>
                    <select className={inputClass} disabled={!editable} value={s.grade ?? ''} onChange={(e) => setSide(side, 'grade', e.target.value)}>
                      <option value="">未填</option>
                      {['G0', 'G1', 'G2', 'G3'].map((g) => <option key={g} value={g}>{g}</option>)}
                    </select>
                  </Field>
                  {MANUAL.map((m) => (
                    <Field key={m.key} label={`${m.label}（醫師填寫）`} hint={m.hint}>
                      <input className={inputClass} disabled={!editable} value={String(s[m.key] ?? '')} onChange={(e) => setSide(side, m.key, e.target.value)} />
                    </Field>
                  ))}
                </div>
              </Panel>
            )
          })}
          <Panel title="判讀">
            <div className="space-y-3">
              {(['findings', 'impression', 'advice', 'notes'] as const).map((k) => (
                <Field key={k} label={{ findings: '檢查所見', impression: '醫師判讀', advice: '建議', notes: '備註' }[k]}>
                  <textarea className={`${inputClass} min-h-[72px]`} disabled={!editable} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
                </Field>
              ))}
              <label className="flex items-center gap-2 text-[14px]">
                <input type="checkbox" className="accent-steel" disabled={!editable} checked={draft.ai_confirmed} onChange={(e) => setDraft({ ...draft, ai_confirmed: e.target.checked })} />
                我已確認 AI 預填的腎長、eGFR（與分級）
              </label>
            </div>
            {editable && (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button icon={Save} disabled={run.busy || !dirty} onClick={() => void save(false)}>儲存草稿</Button>
                <Button icon={Send} disabled={run.busy} onClick={() => void save(true)}>送簽核</Button>
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-5">
          {editable && (
            <Panel title="簽核">
              {report.checklist.length > 0 && (
                <div className="mb-4">
                  <p className="mb-2 text-[14px] font-medium">簽核前檢查清單</p>
                  <ul className="space-y-1.5">
                    {report.checklist.map((c) => (
                      <li key={c.key}>
                        <label className="flex gap-2 text-[14px]">
                          <input type="checkbox" className="mt-1 accent-steel" checked={ack.includes(c.key)} onChange={(e) => setAck(e.target.checked ? [...ack, c.key] : ack.filter((k) => k !== c.key))} />
                          <span><span className="text-amber">{c.text}</span>：已知悉</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Field label="判讀醫師">
                <select className={inputClass} value={signer} onChange={(e) => setSigner(e.target.value)}>
                  <option value="">請選擇</option>
                  {physicians.map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
                </select>
              </Field>
              {!physicians.length && <p className="mt-1 text-[13px] text-amber">醫師名單是空的：到「設定 › 醫師與操作者名單」新增。</p>}
              <div className="mt-3">
                <Field label="輸入判讀醫師姓名確認">
                  <input className={inputClass} value={confirmName} onChange={(e) => setConfirmName(e.target.value)} />
                </Field>
              </div>
              <div className="mt-3">
                <Button variant="primary" icon={ShieldCheck} disabled={run.busy || dirty || !signer || confirmName.trim() !== signer || !checklistDone} onClick={() => void sign()}>簽核</Button>
                {dirty && <p className="mt-1 text-[13px] text-ink-faint">有未儲存的修改，請先儲存。</p>}
              </div>
              <p className="mt-3 text-[12px] text-ink-faint">簽核是本機操作紀錄，不是電子簽章。簽核後產生 PDF，資料夾只保留最新一份。</p>
            </Panel>
          )}
          {report.status === 'signed' && (
            <Panel title="已簽核">
              <p className="text-[14px]">判讀醫師 {report.signed_by}・{when(report.signed_at)}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button icon={PenLine} disabled={run.busy} onClick={() => void run.run(() => api.post<Report>(`/clinical/reports/${report.id}/revise`))}>修訂</Button>
              </div>
            </Panel>
          )}
          {report.status !== 'void' && (
            <Panel title="作廢">
              <Field label="作廢原因（必填）">
                <input className={inputClass} value={voidReason} onChange={(e) => setVoidReason(e.target.value)} />
              </Field>
              <div className="mt-3">
                <Button icon={Ban} disabled={run.busy || !voidReason.trim()} onClick={() => { if (window.confirm('作廢後不能復原，PDF 會覆蓋成作廢版。確定作廢？')) void run.run(() => api.post<Report>(`/clinical/reports/${report.id}/void`, { reason: voidReason })) }}>作廢報告</Button>
              </div>
            </Panel>
          )}
          <Panel title="使用的模型">
            <ul className="space-y-1 text-[13px]">
              {Object.entries(report.models).map(([z, m]) => <li key={z}><span className="font-mono">{m.model_id}</span>（{m.stage === 'candidate' ? '候選' : m.stage === 'clinical' ? '臨床上線' : m.stage}）</li>)}
              {!Object.keys(report.models).length && <li className="text-ink-faint">—</li>}
            </ul>
            <p className="mt-2 text-[12px] text-ink-faint">報告固定引用分析 {report.analysis_id}；重新分析不會改變這份報告。</p>
          </Panel>
        </div>
      </div>

      <Drawer open={history} title="版本歷史" onClose={() => { setHistory(false); setViewing(null) }}>
        {viewing ? (
          <div className="text-[14px]">
            <button type="button" className="mb-3 text-steel hover:underline" onClick={() => setViewing(null)}>← 回版本列表</button>
            <p className="font-medium">第 {viewing.version} 版內容</p>
            {(['right', 'left'] as Side[]).map((s) => viewing.payload.sides[s] && (
              <p key={s} className="mt-2">{SIDE_LABEL[s]}：腎長 {viewing.payload.sides[s]!.length_mm ?? '—'} mm、分級 {viewing.payload.sides[s]!.grade || '—'}、積水 {viewing.payload.sides[s]!.hydronephrosis || '—'}</p>
            ))}
            <p className="mt-2 whitespace-pre-wrap">判讀：{viewing.payload.impression || '—'}</p>
            <p className="mt-1 whitespace-pre-wrap">建議：{viewing.payload.advice || '—'}</p>
          </div>
        ) : (
          <>
            <Timeline entries={report.versions.map((v) => ({
              title: `第 ${v.version} 版・${STATUS_NAME[v.status]}`,
              time: when(v.created_at),
              by: v.actor,
              note: v.acknowledged.length ? `已知悉 ${v.acknowledged.length} 項` : undefined,
              tone: v.status === 'signed' ? 'ok' : v.status === 'void' ? 'alert' : undefined,
            }))} />
            <div className="flex flex-wrap gap-1">
              {report.versions.map((v) => (
                <button key={v.version} type="button" className="rounded px-2 py-1 text-[13px] text-steel hover:bg-steel-wash"
                  onClick={() => void api.get<ReportPayload>(`/clinical/reports/${report.id}/versions/${v.version}`).then((p) => setViewing({ version: v.version, payload: p }))}>
                  看第 {v.version} 版
                </button>
              ))}
            </div>
            <p className="mt-3 text-[12px] text-ink-faint">每次儲存都是新的版本，存在資料庫；PDF 資料夾只保留最新一份。</p>
          </>
        )}
      </Drawer>
    </>
  )
}
