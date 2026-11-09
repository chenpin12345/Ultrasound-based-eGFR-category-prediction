import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, Check, PenTool, X } from 'lucide-react'
import { api } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import type { TaskSummary } from '../../api/types'
import { Button, EmptyState, KeyValue, PageHeader, Panel, ProgressBar, Table, Tabs } from '../../components/ui'
import { GradeScale } from '../../components/GradeScale'
import { ErrorNote, Loading } from '../../components/live'
import DraftReview from './DraftReview'
import PhysicianCircling from './PhysicianCircling'

type Tab = 'tasks' | 'circling' | 'drafts' | 'feedback' | 'agreement' | 'guide'

const who: Record<TaskSummary['id'], string> = {
  mask: '醫師（在系統外圈選後上傳）',
  grade: '醫師（建議兩位獨立分級）',
  side: '研究人員',
}

interface Feedback {
  id: number
  exam_id: string
  item: string
  ai: string
  doctor: string
  by: string
  created_at: string
  decision: string | null
  kind: string
  side: 'right' | 'left' | null
  image_id: string | null
  reason: string
  model_id: string | null
  decided_by: string | null
}

interface Agreement {
  id: string
  created_at: string
  grade: { pairs: { raters: string[]; n: number; unsure: number; weighted_kappa: number | null; exact_agreement: number | null; differ_by_2_or_more: { patient_id: string; side: string; grades: number[] }[] }[] }
  mask: { images: number; dice: Record<string, { mean: number; n: number }> }
}

const structureName: Record<string, string> = { parenchyma: '腎實質', sinus: '腎竇', liver: '肝', spleen: '脾' }

export default function Annotation() {
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(window.location.search).get('tab') as Tab) || 'tasks')
  const tasks = useApi<{ tasks: TaskSummary[] }>('/annotation/tasks')
  const feedback = useApi<{ items: Feedback[] }>('/feedback')
  const agreement = useApi<{ report: Agreement | null }>('/annotation/agreement')
  const compute = useAction(() => api.post<Agreement>('/annotation/agreement'))
  const decide = useAction((id: number, d: 'accept' | 'reject') => api.post(`/feedback/${id}/${d}`))
  const pending = feedback.data?.items.filter((f) => !f.decision).length ?? 0
  const report = agreement.data?.report

  return (
    <>
      <PageHeader title="標註與回饋" description="遮罩由醫師在系統外圈選後上傳（醫師圈選分頁）；回音分級在系統內盲測判讀，畫面固定隱藏 eGFR、AI 結果與其他人的分級。" />
      <Tabs
        label="標註內容"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'tasks', label: '標註任務' },
          { id: 'circling', label: '醫師圈選' },
          { id: 'drafts', label: '草稿確認' },
          { id: 'feedback', label: `臨床回饋（${pending}）` },
          { id: 'agreement', label: '一致性報告' },
          { id: 'guide', label: '標註規範' },
        ]}
      />

      {tab === 'circling' && <PhysicianCircling />}

      {tab === 'tasks' && (
        <Panel flush>
          <ErrorNote error={tasks.error} />
          {tasks.loading && !tasks.data ? (
            <Loading />
          ) : (
            <Table
              minWidth={760}
              head={['標註項目', '由誰標', '進度', '完成', '']}
              rows={(tasks.data?.tasks ?? []).map((t) => [
                <span key="n" className="font-medium">
                  {t.name}
                </span>,
                who[t.id],
                <div key="p" className="w-40">
                  <ProgressBar value={t.total ? (t.done / t.total) * 100 : 0} label={`${t.name}進度`} />
                </div>,
                <span key="d">
                  {t.done}／{t.total}
                  {t.id === 'grade' && t.double !== undefined && <span className="block text-[12px] text-ink-faint">兩位醫師都分級：{t.double}</span>}
                </span>,
                t.total ? (
                  <Link key="b" to={`/research/annotation/${t.id}`} className="inline-flex items-center gap-1.5 text-steel hover:underline">
                    <PenTool className="h-4 w-4" aria-hidden />
                    開始標註
                  </Link>
                ) : (
                  <span key="b" className="text-[13px] text-ink-faint">
                    {t.id === 'grade' ? '需要先對照病人並標出側別' : '需要先匯入影像'}
                  </span>
                ),
              ])}
            />
          )}
        </Panel>
      )}

      {tab === 'drafts' && <DraftReview />}
      {tab === 'feedback' && (
        <Panel flush>
          <ErrorNote error={feedback.error ?? decide.error} />
          {feedback.data && feedback.data.items.length ? (
            <Table
              minWidth={900}
              head={['檢查', '項目', 'AI', '醫師', '原因／模型', '修改者', '時間', '']}
              rows={feedback.data.items.map((f) => [
                <span key="e">
                  {f.exam_id}
                  {f.image_id && <span className="block text-[12px] text-ink-faint">{f.image_id}</span>}
                </span>,
                `${f.side ? `${f.side === 'right' ? '右腎' : '左腎'}・` : ''}${f.item}`,
                <span key="a" className="text-ink-soft">
                  {f.ai}
                </span>,
                <span key="d" className="font-medium">
                  {f.doctor}
                </span>,
                <span key="r" className="text-[13px] text-ink-soft">
                  {f.reason || '—'}
                  {f.model_id && <span className="block font-mono text-[12px] text-ink-faint">{f.model_id}</span>}
                </span>,
                f.by,
                f.created_at.slice(0, 16).replace('T', ' '),
                f.decision ? (
                  <span key="x" className="text-ink-faint">
                    已{f.decision}
                    {f.decided_by && `（${f.decided_by}）`}
                  </span>
                ) : (
                  <span key="x" className="flex gap-1">
                    <Button variant="ghost" icon={Check} onClick={async () => { await decide.run(f.id, 'accept'); void feedback.reload() }}>
                      採用
                    </Button>
                    <Button variant="ghost" icon={X} onClick={async () => { await decide.run(f.id, 'reject'); void feedback.reload() }}>
                      不採用
                    </Button>
                  </span>
                ),
              ])}
            />
          ) : (
            <p className="px-5 py-8 text-ink-soft">沒有臨床回饋。醫師在醫師端檢查工作區排除影像、指定側別、修改腎長或分級時，會出現在這裡（不含年齡、糖尿病等臨床資料）。</p>
          )}
        </Panel>
      )}

      {tab === 'agreement' && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              icon={BarChart3}
              disabled={compute.busy}
              onClick={async () => {
                await compute.run()
                void agreement.reload()
              }}
            >
              {compute.busy ? '計算中…' : '重新計算一致性'}
            </Button>
            {report && <span className="text-[13px] text-ink-faint">上次計算：{report.created_at.slice(0, 16).replace('T', ' ')}</span>}
          </div>
          <ErrorNote error={compute.error ?? agreement.error} />
          {!report ? (
            <EmptyState icon={BarChart3} title="還沒有一致性資料" body="兩位醫師都完成分級、或兩位標註者都畫了同一張影像的遮罩後，按「重新計算一致性」。" />
          ) : (
            <div className="grid gap-5 xl:grid-cols-2">
              <Panel title="回音分級（醫師之間）" flush>
                {report.grade.pairs.length ? (
                  <Table
                    minWidth={460}
                    head={['醫師', '腎臟數', 'weighted kappa', '完全一致', '差 2 級以上']}
                    rows={report.grade.pairs.map((p) => [
                      p.raters.join(' × '),
                      p.n,
                      p.weighted_kappa === null ? '—' : p.weighted_kappa.toFixed(3),
                      p.exact_agreement === null ? '—' : `${Math.round(p.exact_agreement * 100)}%`,
                      p.differ_by_2_or_more.length,
                    ])}
                  />
                ) : (
                  <p className="px-5 py-4 text-[14px] text-ink-soft">還沒有兩位醫師都分級的腎臟。</p>
                )}
              </Panel>
              <Panel title={`遮罩（兩位標註者，${report.mask.images} 張影像）`}>
                {Object.keys(report.mask.dice).length ? (
                  <KeyValue items={Object.entries(report.mask.dice).map(([k, v]) => [structureName[k] ?? k, `Dice ${v.mean.toFixed(3)}（${v.n} 張）`])} />
                ) : (
                  <p className="text-[14px] text-ink-soft">還沒有兩位標註者都畫過的影像。</p>
                )}
              </Panel>
            </div>
          )}
        </div>
      )}

      {tab === 'guide' && (
        <div className="space-y-5">
          <Panel title="醫師圈選的遮罩規則（標註規範 v0.2，待醫師確認）">
            <ul className="max-w-3xl list-disc space-y-2 pl-5 text-[14px] text-ink-soft">
              <li>醫師在匯出的影像上用顏色圈出：腎臟外框（整顆腎，含腎竇）、腎竇、右腎的肝或左腎的脾。腎實質＝外框扣掉腎竇，由程式計算。</li>
              <li>肝、脾圈影像中看得到的整個器官（器官內的血管算在內；膽囊、腸道、陰影不算）；算回音比時程式只取和皮質同深度的部分。</li>
              <li>檔名不能改、尺寸不能縮放；建議存 PNG；輪廓要封閉，可以畫輪廓線或塗滿。顏色代表什麼在「設定 › 顏色對照」設定。</li>
              <li>每個構造的狀態：已畫、不在影像中、未標。未標的在訓練時忽略、不當背景；右腎影像的脾、左腎影像的肝自動設為不在影像中。</li>
              <li>待醫師確認：腎被膜內緣或外緣、輪廓線寬度算內或外、怎麼表示「沒有肝或脾」、囊腫是否另外圈。</li>
            </ul>
          </Panel>
        <Panel title="回音分級的定義（待醫師確認）">
          <GradeScale />
          <ul className="mt-5 max-w-3xl list-disc space-y-2 pl-5 text-[14px] text-ink-soft">
            <li>右腎皮質與肝臟比較，左腎皮質與脾臟比較；參考區要放在與腎皮質相同深度（上下 1 cm 內）。</li>
            <li>皮質＝整顆腎臟扣掉腎竇與腎盂；避開髓質錐體、囊腫、結石、血管與陰影。</li>
            <li>Grade 3 是「接近」還是「等於」腎竇亮度，尚待醫師決定。</li>
            <li>畫面中沒有肝或脾，或影像不足以判斷時，選「無法判斷」並寫原因。</li>
            <li>完整規範見專案文件《標註規範（草稿）》。</li>
          </ul>
        </Panel>
        </div>
      )}
    </>
  )
}
