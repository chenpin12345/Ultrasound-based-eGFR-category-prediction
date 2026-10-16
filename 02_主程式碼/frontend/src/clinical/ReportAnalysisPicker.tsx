import { useClinical } from './hooks'
import { ErrorNotice } from './Components'

interface Run {id:string;evidence:string;created:number;plan_name?:string|null;snapshot:{result:any;coordinates?:{processed_size?:number[]}}}
export function ReportAnalysisPicker({frameId,value,onChange,legacy=false}:{frameId:string;value:string;onChange:(value:string)=>void;legacy?:boolean}) {
  const runs=useClinical<Run[]>(`/clinical/frames/${frameId}/analyses/history`)
  const selected=runs.data?.find(run=>run.id===value),result=selected?.snapshot.result
  return <article className="space-y-3 rounded-xl border p-4"><label className="block"><span className="label">影像 {frameId.slice(0,8)} 的分析版本</span><select aria-label={`影像 ${frameId.slice(0,8)} 的分析版本`} className="field" value={value} onChange={event=>onChange(event.target.value)}><option value="">{legacy?'沿用原報告未核實的歷史數值':'不附分析版本'}</option>{runs.data?.map(run=><option key={run.id} value={run.id}>{new Date(run.created*1000).toLocaleString()} · {run.plan_name?`方案 ${run.plan_name}`:'未記錄方案'} · {run.evidence==='verified'?'已保存快照':'歷史未核實'} · {run.id.slice(0,12)}</option>)}</select></label><ErrorNotice message={runs.error}/>
    <p className="text-sm text-slate-600">分析版本固定後，重新分析不會自動替換報告附件。尚無實體長度量測，只呈現像素特徵。</p>
    {selected&&<><p className="break-all text-xs">分析版本：{selected.id}</p>{selected.evidence!=='verified'?<p className="text-amber-800">歷史產物對應未核實，不展示舊 Mask 為有效附件。</p>:<><h4 className="font-semibold">量測與相關特徵</h4>{result?.has_mask?<dl className="grid gap-2 text-sm sm:grid-cols-3">{[['Length_px','分割區域長軸特徵（px）'],['Contrast_Ratio','Contrast_Ratio（無單位）'],['Entropy','Entropy（影像熵特徵）']].map(([key,label])=><div key={key}><dt>{label}</dt><dd>{result.features?.[key]??'缺失，未補零'}</dd></div>)}</dl>:<p>本次未分割，不提供長軸或虛構 Mask。</p>}<h4 className="font-semibold">AI 預測 eGFR 類別：{result?.predicted_class||'缺失'}</h4><ul className="text-sm">{result?.probabilities?.map((item:any)=><li key={item.label}>{item.label}：{(item.probability*100).toFixed(2)}%（模型預測機率）</li>)}</ul><p className="text-xs text-slate-600">不是模型準確率、確診機率或病例期別。</p></>}</>}
  </article>
}
