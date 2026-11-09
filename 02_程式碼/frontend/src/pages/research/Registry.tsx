import { Link } from 'react-router-dom'
import { Boxes } from 'lucide-react'
import { useApi } from '../../api/hooks'
import { fmt, modelHref, scoreLabel, zoneHome, type ModelInfo, type TaskId } from '../../api/ml'
import { EmptyState, PageHeader, Panel, Pill, Table } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'

export const stageTone = (s: string) => (s === 'clinical' ? 'ok' : s === 'candidate' ? 'steel' : s === 'retired' ? 'neutral' : 'amber')

/** 模型庫（依任務分開，決策 D28）。 */
export default function Registry({ task }: { task: TaskId }) {
  const models = useApi<{ models: ModelInfo[] }>(`/models?task=${task}`, [task])
  return (
    <>
      <PageHeader title={`${zoneHome[task].label}模型`} description="註冊後的模型檔不可修改（附 sha256）；推論前會檢查合約，不符就拒絕。醫師端優先使用「臨床上線」的模型；沒有時可以在「設定 › 醫師端」選「候選」模型，結果會標示「尚未臨床核准・僅供研究展示」（D40）。" />
      <ErrorNote error={models.error} />
      <Panel flush>
        {models.loading && !models.data ? (
          <Loading />
        ) : models.data?.models.length ? (
          <Table
            minWidth={760}
            head={['模型', '階段', '交叉驗證', '架構', '註冊']}
            rows={models.data.models.map((m) => [
              <Link key="id" to={modelHref(m.id)} className="font-medium text-steel hover:underline">
                {m.id}
              </Link>,
              <Pill key="s" tone={stageTone(m.stage)}>
                {m.stage_label}
              </Pill>,
              m.metrics?.mean_best_score == null ? '—' : `${scoreLabel[m.task]} ${fmt(m.metrics.mean_best_score)}${m.egfr_classes ? `・${m.egfr_classes} 類` : ''}`,
              m.architecture ? `${m.architecture.arch}${m.architecture.head ? `＋${m.architecture.head}` : ''}・${m.architecture.init}` : '—',
              `${m.created_at.slice(0, 10)}・${m.created_by}`,
            ])}
          />
        ) : (
          <EmptyState icon={Boxes} title="還沒有模型" body="訓練完成後，從訓練詳細頁按「註冊為模型」。" />
        )}
      </Panel>
    </>
  )
}
