import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export interface Series {
  key: string
  label: string
  color: string
  dashed?: boolean
}

const axis = { stroke: '#7A8894', fontSize: 12 }

/** 共用折線圖：訓練曲線、趨勢圖都用它，維持同一套樣式。 */
export function LineChartPanel({
  data,
  xKey,
  xLabel,
  series,
  height = 240,
  yDomain,
}: {
  data: Record<string, number | string | null>[]
  xKey: string
  xLabel?: string
  series: Series[]
  height?: number
  yDomain?: [number | 'auto', number | 'auto']
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <CartesianGrid stroke="#E2E8E7" vertical={false} />
          <XAxis dataKey={xKey} tick={axis} tickLine={false} axisLine={{ stroke: '#D3DCDB' }} label={xLabel ? { value: xLabel, position: 'insideBottomRight', offset: -2, fontSize: 12, fill: '#7A8894' } : undefined} />
          <YAxis tick={axis} tickLine={false} axisLine={false} domain={yDomain ?? ['auto', 'auto']} width={48} />
          <Tooltip contentStyle={{ borderRadius: 6, borderColor: '#D3DCDB', fontSize: 13 }} />
          <Legend wrapperStyle={{ fontSize: 13 }} iconType="plainline" />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dashed ? '5 4' : undefined}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 混淆矩陣：列是答案、欄是預測，顏色深淺代表筆數。 */
export function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const max = Math.max(...matrix.flat())
  return (
    <div className="overflow-x-auto">
      <table className="text-[13px]">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left font-normal text-ink-faint">答案 \ 預測</th>
            {labels.map((l) => (
              <th key={l} className="w-14 px-2 py-1 text-center font-medium">
                {l}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, r) => (
            <tr key={r}>
              <th className="px-2 py-1 text-left font-medium">{labels[r]}</th>
              {row.map((v, c) => {
                const strength = max ? v / max : 0
                return (
                  <td
                    key={c}
                    className="h-11 w-14 border border-white text-center"
                    style={{ background: `rgba(46,106,132,${0.08 + strength * 0.8})`, color: strength > 0.55 ? '#fff' : '#1B2A38' }}
                  >
                    {v}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
