import { Link } from 'react-router-dom'
import { useApi } from '../../api/hooks'
import { fmt } from '../../api/ml'
import { LineChartPanel } from '../../components/charts'
import { Panel, Pill, Table } from '../../components/ui'
import { ErrorNote } from '../../components/live'

interface Curve {
  split_id: string
  points: { run_id: string; name: string; masks: number; dice: number; gain?: number; finished_at: string }[]
  plateau: boolean
  threshold: number
}

/** 分割的學習曲線（決策 D20）：用累積的醫師遮罩訓練後，交叉驗證 Dice 不再明顯進步就可以停止請醫師圈選。 */
export default function LearningCurve() {
  const curve = useApi<Curve>('/training/learning-curve')
  const c = curve.data
  return (
    <Panel title="學習曲線（醫師圈選要不要下一批）">
      <p className="text-[13px] text-ink-soft">
        每個完成的分割訓練是一個點：橫軸是用到的醫師遮罩張數，縱軸是交叉驗證的平均 Dice（不用測試集）。連續兩輪進步都小於 {c ? c.threshold : 0.01} 時，再圈也幫助不大，可以停止。
      </p>
      <ErrorNote error={curve.error} />
      {c && c.points.length === 0 && <p className="mt-3 text-[14px] text-ink-soft">還沒有完成的分割訓練。醫師圈選的第一批匯入後，用目前的遮罩訓練一次。</p>}
      {c && c.points.length > 0 && (
        <>
          <div className="mt-3">
            <LineChartPanel data={c.points.map((p) => ({ masks: p.masks, dice: Number(p.dice.toFixed(4)) }))} xKey="masks" xLabel="遮罩張數" series={[{ key: 'dice', label: '交叉驗證 Dice', color: '#2F6F8F' }]} height={200} yDomain={['auto', 'auto']} />
          </div>
          <p className="mt-2 text-[14px]">
            {c.plateau ? <Pill tone="ok">已趨平：可以停止請醫師圈選</Pill> : <Pill tone="steel">還在進步：建議再圈一批</Pill>}
          </p>
          <div className="mt-3">
            <Table
              minWidth={420}
              head={['訓練', '遮罩張數', 'Dice', '比上一輪']}
              rows={c.points.map((p) => [
                <Link key="r" to={`/research/training/${p.run_id}`} className="text-steel underline">
                  {p.run_id}
                </Link>,
                p.masks,
                fmt(p.dice),
                p.gain == null ? '—' : `${p.gain >= 0 ? '+' : ''}${p.gain.toFixed(3)}`,
              ])}
            />
          </div>
        </>
      )}
    </Panel>
  )
}
