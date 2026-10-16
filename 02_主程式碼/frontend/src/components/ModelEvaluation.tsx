import { Link } from 'react-router-dom'
import type { ModelEvaluationSummary } from '../types/api'

const names:Record<string,string>={accuracy:'Accuracy',macro_f1:'Macro F1（有定義類別）',dice:'前景 Dice（逐圖平均）',iou:'前景 IoU（逐圖平均）'}
export function ModelEvaluation({summary,details=false}:{summary?:ModelEvaluationSummary;details?:boolean}) {
  if(!summary?.evaluation_id)return <p className="text-sm text-slate-600">尚未評估，沒有可顯示的成績。</p>
  return <section aria-label="最近評估摘要" className="space-y-2 text-sm">
    <p className="font-semibold">最近建立的評估（不是最佳模型排名）</p>
    {summary.reason&&<p className="text-amber-800">{summary.reason}</p>}
    <dl className="flex flex-wrap gap-4">{Object.entries(summary.metrics).map(([key,value])=><div key={key}><dt>{names[key]||key}</dt><dd className="font-semibold">{value==null?'無法定義':`${(value*100).toFixed(2)}%`}</dd></div>)}</dl>
    <p>{summary.dataset_name} · {summary.split} · 完成 {summary.evaluated_sample_count??'—'} / {summary.sample_count??'—'} 張</p>
    <p>{summary.scope}</p>
    {details&&<div className="space-y-1 break-all text-xs text-slate-600"><p>權重 SHA-256：{summary.weight_sha256}</p><p>設定 SHA-256：{summary.configuration_sha256}</p><p>指標版本：{summary.metric_version}</p><p>完成時間：{summary.completed_at||'尚未完成'}</p></div>}
    <Link className="inline-block py-2 font-semibold text-clinical-700 underline" to={`/model-center/evaluations/${summary.evaluation_id}`}>查看評估範圍與逐筆結果</Link>
  </section>
}
