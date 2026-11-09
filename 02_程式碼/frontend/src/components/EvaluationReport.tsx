import { fmt } from '../api/ml'
import { ConfusionMatrix } from './charts'
import { Table } from './ui'

// 評估結果（交叉驗證或固定測試集）的表格：eGFR 分影像／病人層級（2／3／5 類，共同的尺是 AUC(<60)），分級任務分影像／病人＋側別層級，分割列出各類別 Dice。

type Metrics = Record<string, unknown>

const LEVELS: [string, string][] = [
  ['image', '影像層級'],
  ['patient', '病人層級'],
  ['patient_side', '病人＋側別層級'],
]

// [欄位, 名稱, 說明, 信賴區間欄位]
const ROWS: [string, string, string, string?][] = [
  ['auc_lt60', 'AUC(eGFR<60)', '區分 eGFR<60 與 ≥60 的能力；2、3、5 類模型共同的尺', 'auc_lt60_ci'],
  ['auc_lt30', 'AUC(eGFR<30)', '區分 eGFR<30 與 ≥30 的能力（3、5 類）', 'auc_lt30_ci'],
  ['auc', 'AUC', '區分兩組的能力；0.5＝亂猜，1＝完美', 'auc_ci'],
  ['qwk', '加權 Kappa（QWK）', '與標註的一致程度；0＝偶然，1＝完全一致', 'qwk_ci'],
  ['accuracy', '準確率', '判斷正確的比例'],
  ['sensitivity', '敏感度', '陽性（例如 eGFR < 60）被正確抓出的比例'],
  ['specificity', '特異度', '陰性（例如 eGFR ≥ 60）被正確判為陰性的比例'],
  ['mae', '平均絕對誤差', '預測分級與標註平均差幾級'],
  ['brier', 'Brier 分數', '預測機率的整體誤差；越小越好，0.25 約等於亂猜'],
  ['ece', '校準誤差（ECE）', '預測機率和實際比例差多少；越小越好'],
  ['brier_lt60', 'Brier(<60)', 'P(eGFR<60) 的整體誤差；越小越好'],
  ['ece_lt60', 'ECE(<60)', 'P(eGFR<60) 的校準誤差；越小越好'],
]

const DICE: [string, string][] = [
  ['dice_mean', '平均'],
  ['dice_parenchyma', '腎實質'],
  ['dice_sinus', '腎竇'],
  ['dice_liver', '肝'],
  ['dice_spleen', '脾'],
]

const isObj = (v: unknown): v is Metrics => typeof v === 'object' && v !== null && !Array.isArray(v)
const ci = (v: unknown) => (Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === 'number') ? `${fmt(v[0])}–${fmt(v[1])}` : null)

function withCi(value: unknown, interval: unknown) {
  const range = ci(interval)
  return (
    <span>
      <span className="font-medium text-ink">{fmt(value)}</span>
      {range && <span className="block text-[12px] text-ink-faint">95% CI {range}</span>}
    </span>
  )
}

/** 一行摘要（模型頁的評估清單用）：例如「病人層級 AUC 0.768（0.679–0.847）」。 */
export function evaluationHeadline(report: Metrics): string {
  for (const [level, label] of [...LEVELS].reverse()) {
    const m = report[level]
    if (!isObj(m)) continue
    const [name, key, ciKey] = m.auc_lt60 !== undefined ? ['AUC(<60)', 'auc_lt60', 'auc_lt60_ci'] : m.auc !== undefined ? ['AUC', 'auc', 'auc_ci'] : ['QWK', 'qwk', 'qwk_ci']
    const range = ci(m[ciKey])
    return `${label} ${name} ${fmt(m[key])}${range ? `（${range}）` : ''}${m.k ? `・${fmt(m.k)} 類` : ''}・n=${fmt(m.n)}`
  }
  const dice = report.dice_mean
  if (isObj(dice)) return `平均 Dice ${fmt(dice.mean)}${ci(dice.ci) ? `（${ci(dice.ci)}）` : ''}・n=${fmt(report.n)}`
  return '—'
}

export function EvaluationReport({ report }: { report: Metrics }) {
  const levels = LEVELS.filter(([key]) => isObj(report[key]))
  if (levels.length) {
    const hasLt60 = levels.some(([level]) => (report[level] as Metrics).auc_lt60 !== undefined)
    const rows = ROWS.filter(([key]) => !(hasLt60 && key === 'auc')).filter(([key]) => levels.some(([level]) => (report[level] as Metrics)[key] !== undefined))
    const patient = isObj(report.patient) ? (report.patient as Metrics) : null
    const classes = Array.isArray(patient?.classes) ? (patient!.classes as string[]) : null
    const confusion = Array.isArray(patient?.confusion) ? (patient!.confusion as number[][]) : null
    const collapsed3 = isObj(patient?.collapsed) && isObj((patient!.collapsed as Metrics)['3']) ? ((patient!.collapsed as Metrics)['3'] as Metrics) : null
    return (
      <div className="space-y-4">
      <Table
        minWidth={560}
        head={['指標', ...levels.map(([key, label]) => `${label}（n=${fmt((report[key] as Metrics).n)}）`)]}
        rows={rows.map(([key, name, hint, ciKey]) => [
          <span key="k">
            <span className="block">{name}</span>
            <span className="block text-[12px] text-ink-faint">{hint}</span>
          </span>,
          ...levels.map(([level]) => {
            const m = report[level] as Metrics
            return <span key={level}>{ciKey ? withCi(m[key], m[ciKey]) : <span className="font-medium text-ink">{fmt(m[key])}</span>}</span>
          }),
        ])}
      />
      {classes && confusion && (
        <div className="grid gap-4 px-5 pb-4 md:grid-cols-2">
          <div>
            <p className="mb-1 text-[13px] font-medium">病人層級混淆矩陣（{classes.length} 類）</p>
            <ConfusionMatrix labels={classes} matrix={confusion} />
          </div>
          {collapsed3 && Array.isArray(collapsed3.confusion) && (
            <div>
              <p className="mb-1 text-[13px] font-medium">合併成 3 類（QWK {fmt(collapsed3.qwk)}）</p>
              <ConfusionMatrix labels={['≥60', '30–59', '<30']} matrix={collapsed3.confusion as number[][]} />
            </div>
          )}
        </div>
      )}
      </div>
    )
  }
  const dice = DICE.filter(([key]) => isObj(report[key]))
  if (dice.length) {
    return (
      <Table
        minWidth={480}
        head={['Dice（分割重疊程度，1＝完全重疊）', '平均（95% CI）', '影像數']}
        rows={dice.map(([key, name]) => {
          const m = report[key] as Metrics
          return [name, withCi(m.mean, m.ci), fmt(m.n)]
        })}
      />
    )
  }
  return <pre className="max-h-96 overflow-auto rounded bg-paper p-3 text-[12px]">{JSON.stringify(report, null, 2)}</pre>
}
