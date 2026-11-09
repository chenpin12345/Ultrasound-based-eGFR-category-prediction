import { Link } from 'react-router-dom'
import { useApi } from '../../api/hooks'
import type { Overview as OverviewData, TaskSummary } from '../../api/types'
import { Figure, PageHeader, Panel, ProgressBar } from '../../components/ui'
import { ErrorNote } from '../../components/live'

const phases = [
  { name: '介面', note: '確定整體介面與名稱', state: 'done' },
  { name: 'M1 資料基礎', note: '匯入與去識別化、病人對照、病人層級切分、標註、資料集版本', state: 'done' },
  { name: 'M2 訓練與模型', note: '通用訓練引擎、模型庫、評估與實驗、一鍵流程（不會自動訓練）', state: 'done' },
  { name: 'M2.5 醫師圈選與 eGFR 比較', note: '醫師圈選清單、遮罩組、eGFR 2／3／5 類與輸入 ①–⑥ 比較、三區分開、資料夾整理', state: 'now' },
  { name: 'M3 醫師端', note: '接收、自動分析、檢查工作區、報告與 PDF', state: 'later' },
  { name: '延伸', note: '影片影格、囊腫／結石／積水偵測', state: 'later' },
] as const

export default function Overview() {
  const o = useApi<OverviewData>('/overview')
  const tasks = useApi<{ tasks: TaskSummary[] }>('/annotation/tasks')
  const d = o.data
  const todo = d
    ? [
        { label: '待人工確認的影像', value: d.images.pending_review ?? 0, to: '/research/datasets?tab=images&status=pending_review' },
        { label: '還沒對到病人的影像', value: d.unmatched_images, to: '/research/datasets?tab=patients' },
        { label: '待審核的臨床回饋', value: d.pending_feedback, to: '/research/annotation' },
        { label: '失敗的背景工作', value: d.failed_jobs, to: '/jobs' },
      ]
    : []

  return (
    <>
      <PageHeader title="研究總覽" description="所有模型都會用新的病人層級切分重新訓練，不沿用舊的權重與成績。" />
      <ErrorNote error={o.error} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Panel title="資料">
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Figure value={d?.images.total ?? '—'} label="已匯入影像" note={d ? `${d.batches} 個批次` : undefined} />
              <Figure value={d?.images.usable ?? 0} label="可用影像" />
              <Figure value={d?.patients ?? '—'} label="病人" />
              <Figure value={d?.images.excluded ?? 0} label="已排除" />
            </div>
            {d && d.images.total === 0 && (
              <p className="mt-4 text-[14px] text-ink-soft">
                還沒有匯入任何影像。到{' '}
                <Link to="/research/datasets?tab=import" className="text-steel underline">
                  資料集 › 匯入
                </Link>{' '}
                匯入原始資料集。
              </p>
            )}
          </Panel>
          <Panel title="標註進度">
            <ul className="space-y-3">
              {(tasks.data?.tasks ?? []).map((t) => (
                <li key={t.id} className="grid grid-cols-[minmax(0,1fr)_160px_80px] items-center gap-3 text-[14px]">
                  <Link to={`/research/annotation/${t.id}`} className="hover:text-steel hover:underline">
                    {t.name}
                  </Link>
                  <ProgressBar value={t.total ? (t.done / t.total) * 100 : 0} label={t.name} />
                  <span className="text-right text-ink-soft">
                    {t.done}／{t.total}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="重建進度">
            <ol>
              {phases.map((p, i) => (
                <li key={p.name} className="grid grid-cols-[32px_1fr] gap-3">
                  <span className="flex flex-col items-center">
                    <span
                      className={`flex h-7 w-7 items-center justify-center rounded-full border text-[13px] font-semibold ${
                        p.state === 'now' ? 'border-steel bg-steel text-white' : p.state === 'done' ? 'border-ok bg-ok-wash text-ok' : 'border-line bg-white text-ink-faint'
                      }`}
                    >
                      {i}
                    </span>
                    {i < phases.length - 1 && <span className="w-px flex-1 bg-line" />}
                  </span>
                  <span className="pb-4">
                    <span className={`block font-medium ${p.state === 'later' ? 'text-ink-soft' : ''}`}>
                      {p.name}
                      {p.state === 'now' && <span className="ml-2 text-[13px] font-normal text-steel">進行中</span>}
                    </span>
                    <span className="block text-[13px] text-ink-faint">{p.note}</span>
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
        <Panel title="需要你處理">
          <ul className="divide-y divide-line text-[14px]">
            {todo.map((item) => (
              <li key={item.label}>
                <Link to={item.to} className="flex items-center justify-between py-2.5 hover:text-steel">
                  <span>{item.label}</span>
                  <span className={`font-semibold ${item.value ? 'text-amber' : 'text-ink-faint'}`}>{item.value}</span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 border-t border-line pt-4 text-[14px] text-ink-soft">
            <p className="font-medium text-ink">建議順序</p>
            <ol className="mt-1 list-decimal space-y-1 pl-5">
              <li>設定 › 一般：選擇主切分</li>
              <li>標註與回饋 › 醫師圈選：建立測試集批次並匯出給醫師</li>
              <li>設定 › 顏色對照：看過醫師的圖後設定顏色</li>
              <li>上傳醫師圈選、檢查後匯入</li>
              <li>eGFR 訓練：勾選 ①②③ 建立比較組（不需要遮罩）</li>
              <li>分割訓練 → 遮罩組 → 勾選 ④⑤⑥</li>
            </ol>
          </div>
        </Panel>
      </div>
    </>
  )
}
