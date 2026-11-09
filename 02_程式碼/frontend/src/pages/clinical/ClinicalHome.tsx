import { Link } from 'react-router-dom'
import { CheckCircle2, CircleAlert } from 'lucide-react'
import { Figure, PageHeader, Panel, Pill } from '../../components/ui'
import { useApi, usePolling } from '../../api/hooks'
import { CANDIDATE_LABEL, when, type ClinicalOverview } from '../../api/clinical'

const ANALYSIS_NAME: Record<string, string> = { queued: '排隊中', running: '分析中', completed: '完成', partial: '部分完成', failed: '失敗' }

/** 醫師端首頁（B1）：開始前檢查、今日待辦、最近分析。 */
export default function ClinicalHome() {
  const { data, error, reload } = useApi<ClinicalOverview>('/clinical/overview')
  usePolling(reload, 8000)
  const c = data?.counts
  const todo = c
    ? [
        { n: c.pending_sign, label: '份報告待簽核', to: '/clinical/reports' },
        { n: c.ready, label: '筆檢查分析完成、等待確認', to: '/clinical/worklist' },
        { n: c.needs_data, label: '筆檢查待補資料', to: '/clinical/worklist' },
        { n: c.layout_mismatch, label: '筆檢查版面不符', to: '/clinical/worklist' },
        { n: c.failed, label: '筆分析失敗或部分完成', to: '/clinical/worklist' },
      ]
    : []
  return (
    <>
      <PageHeader title="醫師端" description="開始展示前先看這裡：分析方案、接收位址與備份都準備好，再到「影像接收」開始接收。" />
      {error && <p className="mb-3 rounded-md bg-alert-wash px-3 py-2 text-[14px] text-alert">{error.message}</p>}
      {data?.candidate && <p className="mb-4 rounded-md border border-amber/30 bg-amber-wash px-3 py-2 text-[14px] text-amber">分析方案用了候選模型：{CANDIDATE_LABEL}。</p>}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel title="今日待辦">
            {c && (
              <>
                <div className="mb-5 flex flex-wrap gap-10">
                  <Figure value={c.today} label="今天收到的檢查" />
                  <Figure value={c.analyzing} label="接收或分析中" />
                  <Figure value={c.drafts} label="報告草稿" />
                </div>
                <ul className="divide-y divide-line">
                  {todo.map((t) => (
                    <li key={t.label} className="flex items-center justify-between py-2 text-[14px]">
                      <span className={t.n ? '' : 'text-ink-faint'}>
                        <strong>{t.n}</strong> {t.label}
                      </span>
                      {t.n > 0 && <Link to={t.to} className="text-steel hover:underline">前往</Link>}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Panel>
          <Panel title="最近的分析">
            {data?.recent_analyses.length ? (
              <ul className="divide-y divide-line text-[14px]">
                {data.recent_analyses.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                    <Link to={`/clinical/exams/${a.exam_id}`} className="text-steel hover:underline">{a.exam_id}</Link>
                    <span className="text-ink-faint">{when(a.created_at)}</span>
                    <Pill tone={a.status === 'completed' ? 'ok' : a.status === 'failed' ? 'alert' : a.status === 'partial' ? 'amber' : 'steel'}>{ANALYSIS_NAME[a.status] ?? a.status}</Pill>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[14px] text-ink-soft">還沒有分析。</p>
            )}
          </Panel>
        </div>
        <Panel title="開始前檢查">
          <ul className="space-y-3">
            {data?.checks.map((k) => (
              <li key={k.key} className="flex gap-2.5 text-[14px]">
                {k.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-label="完成" /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber" aria-label="需要處理" />}
                <span>
                  <span className="font-medium">{k.label}</span>
                  <span className="block text-[13px] text-ink-soft">{k.detail}</span>
                  {!k.ok && <Link to={k.to} className="text-[13px] text-steel hover:underline">前往設定</Link>}
                </span>
              </li>
            ))}
          </ul>
          {data?.receiver ? (
            <p className="mt-4 rounded-md bg-ok-wash px-3 py-2 text-[14px] text-ok">接收中：{data.receiver.url}</p>
          ) : (
            <Link to="/clinical/acquisition" className="mt-4 inline-block text-[14px] text-steel hover:underline">前往影像接收 →</Link>
          )}
        </Panel>
      </div>
    </>
  )
}
