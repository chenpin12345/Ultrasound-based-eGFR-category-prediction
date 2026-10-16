import { Link } from 'react-router-dom'
import { clinical,stateLabel } from './client'
import { useAction } from './hooks'

export function ErrorNotice({message}:{message?:string}) {return message?<p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{message}</p>:null}
export function PlanSelect({plans,value,onChange}:{plans:any[];value:string;onChange:(id:string)=>void}) {return <label className="block text-sm font-semibold">分析方案<select className="field mt-2" value={value} onChange={e=>onChange(e.target.value)}><option value="">僅接收及預覽（不分析）</option>{plans.map(p=><option key={p.id} value={p.id}>{p.name} · {p.profile.mode==='unknown'?'來源待確認':p.profile.mode}</option>)}</select></label>}

export interface PlanInfo {id:string;name:string;created:number;profile:{mode:string;width?:number;height?:number;validated_for_patient?:boolean};classifier:{name?:string;version?:string;architecture?:string;class_count?:number;sha256:string};segmenter?:{name?:string;sha256:string}|null;requirements:{field:string;label:string}[]}
export interface SourceStatus {source:string;label:string;mode:'plan'|'preview_only'|null;plan:PlanInfo|null;analyzable:boolean;problems:string[];setting:{id:string;evidence:string;created:number}|null}
export type AnalysisChoice={mode:'default'|'preview_only'|'plan';plan_id?:string}

/** One line that names the exact sealed plan version actually used. */
export function PlanLine({plan}:{plan:PlanInfo}) {
  return <span>{plan.name} · 封存於 {new Date(plan.created*1000).toLocaleString()} · {plan.classifier.class_count??'?'} 類 · {plan.classifier.architecture} · 權重 {plan.classifier.sha256.slice(0,12)}{plan.segmenter?' · 含分割':''}</span>
}

export function SourcePlanStatus({status,choice}:{status?:SourceStatus;choice?:AnalysisChoice}) {
  if(choice&&choice.mode==='preview_only')return <p role="status" className="rounded-lg bg-amber-50 p-3 text-amber-900">本次明確選擇「僅接收及預覽」：影像會保存與顯示，但不進行 AI 分析。</p>
  if(choice&&choice.mode==='plan')return <p className="rounded-lg bg-slate-50 p-3 text-sm">本次以進階設定指定方案（不使用模型區預設）。</p>
  if(!status)return <p className="text-sm text-slate-600">正在讀取模型區預設方案…</p>
  if(status.mode==='preview_only')return <p role="status" className="rounded-lg bg-amber-50 p-3 text-amber-900">模型區將{status.label}預設設為「僅接收及預覽」，不會分析。</p>
  return <div className={`rounded-lg p-3 text-sm ${status.analyzable?'bg-teal-50 text-teal-900':'bg-red-50 text-red-800'}`}>
    <p className="font-semibold">{status.label}預設方案：{status.plan?<PlanLine plan={status.plan}/>:'尚未設定'}</p>
    {status.analyzable?<p>可分析{status.plan?.requirements.length?`；需要案例欄位：${status.plan.requirements.map(r=>r.label).join('、')}`:'；不需要額外案例欄位'}。</p>
      :<p role="alert">無法使用：{status.problems.join(' ')} 不會自動改用其他方案；請到模型區設定，或在進階設定明確選擇「僅接收及預覽」。</p>}
  </div>
}

/** Advanced override; the default path needs no choice at all. */
export function AnalysisChoiceField({plans,value,onChange,disabled}:{plans:any[];value:AnalysisChoice;onChange:(v:AnalysisChoice)=>void;disabled?:boolean}) {
  return <fieldset className="space-y-2 text-sm" disabled={disabled}><legend className="font-semibold">本次分析模式</legend>
    <label className="flex items-center gap-2"><input type="radio" name="analysis-mode" checked={value.mode==='default'} onChange={()=>onChange({mode:'default'})}/>使用模型區預設方案（建議）</label>
    <label className="flex items-center gap-2"><input type="radio" name="analysis-mode" checked={value.mode==='preview_only'} onChange={()=>onChange({mode:'preview_only'})}/>僅接收及預覽（明確不分析）</label>
    <label className="flex items-center gap-2"><input type="radio" name="analysis-mode" checked={value.mode==='plan'} onChange={()=>onChange({mode:'plan',plan_id:value.plan_id||plans[0]?.id})}/>指定其他封存方案</label>
    {value.mode==='plan'&&<select aria-label="指定方案" className="field" value={value.plan_id||''} onChange={e=>onChange({mode:'plan',plan_id:e.target.value})}>{plans.map(p=><option key={p.id} value={p.id}>{p.name} · {new Date(p.created*1000).toLocaleDateString()} · {p.profile.mode==='unknown'?'來源待確認':p.profile.mode}</option>)}</select>}
  </fieldset>
}export function FrameResult({frame,onSave}:{frame:any;onSave?:()=>void}) {
  const action=useAction();const result=frame.result
  // Pin each displayed artifact to the result's immutable run. Legacy results
  // have no verifiable artifact binding and must not use the latest mask.
  const runId=result?.analysis_run_id
  const artifact=(name:string)=>`/api/clinical/analyses/${encodeURIComponent(runId)}/${name}`
  return <article className="rounded-2xl border bg-white p-5"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-bold">影像 {frame.id.slice(0,12)}</h3><p className="text-sm text-slate-600">{stateLabel[frame.status]||frame.status} · {new Date(frame.created*1000).toLocaleString()}</p></div><Link className="btn-secondary" to={`/clinical/exams?exam=${frame.exam_id}&frame=${frame.id}`}>開啟案例／補充資料</Link></div>
    <div className="grid gap-4 md:grid-cols-2"><figure><img src={frame.url} className="h-72 w-full rounded-xl bg-slate-950 object-contain" alt="接收的原始影像"/><figcaption className="mt-2 text-sm">原始影像</figcaption></figure>{frame.status==='completed'&&runId&&<figure><img src={artifact(result?.has_mask?'overlay':'processed')} className="h-72 w-full rounded-xl bg-slate-950 object-contain" alt="對應本張影像的分析結果"/><figcaption className="mt-2 text-sm">本張影像的處理結果{result?.has_mask?'與遮罩':''}</figcaption></figure>}</div>
    {frame.status==='completed'&&runId&&result?.has_mask&&<details className="my-4"><summary className="cursor-pointer text-sm font-semibold">分別檢視處理圖與本張遮罩</summary><div className="mt-3 grid gap-4 md:grid-cols-2">{[['processed','模型實際使用的處理圖'],['mask','對應本張影像的分割遮罩']].map(([type,label])=><figure key={type}><img loading="lazy" src={artifact(type)} className="h-72 w-full rounded-xl bg-slate-950 object-contain" alt={label}/><figcaption className="mt-2 text-sm">{label}</figcaption></figure>)}</div></details>}
    {frame.status==='completed'&&!runId&&<p role="status" className="my-3 rounded-lg bg-amber-50 p-3 text-amber-900">舊分析數值保留，但歷史 Mask／疊圖關聯未核實，不以最新產物代替。</p>}
    {runId&&<p className="my-3 break-all text-xs text-slate-600">分析版本：{runId}；影像與特徵依此版本配對。</p>}
    <p className="my-3 break-all font-mono text-xs text-slate-500">原始 SHA-256：{frame.sha256}</p>{result?.message&&<p role={frame.status==='needs_data'?'alert':undefined} className="rounded-lg bg-amber-50 p-3 text-amber-900">{result.message}</p>}
    {result?.probabilities&&<div className="my-4 grid gap-3 sm:grid-cols-3">{result.probabilities.map((p:any)=><div key={p.label} className="rounded-xl bg-slate-50 p-3"><p className="text-sm">{p.label}</p><p className="text-xl font-bold">{(p.probability*100).toFixed(1)}%</p><p className="text-xs text-slate-500">模型預測機率</p></div>)}</div>}
    {result?.processing_ms!==undefined&&<p className="text-sm text-slate-600">分析 {result.processing_ms} ms · 實際使用方案 {frame.result_plan?`${frame.result_plan.name}（封存於 ${new Date(frame.result_plan.created*1000).toLocaleString()}）`:result.plan_id?.slice(0,12)} · 前處理 {result.profile?.mode}</p>}
    {result?.features&&Object.keys(result.features).length>0&&<details className="my-3"><summary>影像特徵（Length_px 單位為像素）</summary><pre className="overflow-auto p-3 text-xs">{JSON.stringify(result.features,null,2)}</pre></details>}
    <ErrorNotice message={action.error}/><button className="btn-primary mt-4" disabled={!!frame.saved||action.busy} onClick={()=>action.run(async()=>{await clinical('/clinical/frames/'+frame.id+'/save',{});onSave?.()})}>{frame.saved?'已保存影像與結果':'保存影像與結果'}</button>
  </article>
}
