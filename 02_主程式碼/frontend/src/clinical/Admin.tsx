import { useState } from 'react'
import { clinical } from './client'
import { useAction,useClinical } from './hooks'
import { ErrorNotice,PlanLine,SourcePlanStatus,type PlanInfo,type SourceStatus } from './Components'
import { ModelSelector } from '../components/ModelSelector'

interface ClinicalPlan {id:string; name:string; created:number; profile:{mode:string;evidence:string;validated_for_patient?:boolean}; summary:PlanInfo}
interface Defaults {sources:Record<string,SourceStatus>;history:{id:string;source:string;mode:string;plan_name?:string;evidence:string;created:number}[]}

const SOURCE_LABELS:Record<string,string>={network_demo:'圖片傳輸',capture:'設備擷取'}

function DefaultPlanForm({source,status:loaded,plans,onSaved}:{source:string;status?:SourceStatus;plans:ClinicalPlan[];onSaved:()=>void}) {
  const action=useAction(),[mode,setMode]=useState<'plan'|'preview_only'>('plan'),[planId,setPlanId]=useState(''),[evidence,setEvidence]=useState('')
  const status=loaded&&{...loaded,label:SOURCE_LABELS[source]||loaded.label}
  const usable=plans.filter(p=>p.profile.mode!=='unknown'&&(source!=='capture'||p.profile.validated_for_patient))
  return <article className="space-y-3 rounded-xl border p-4"><h3 className="font-bold">{SOURCE_LABELS[source]}</h3><SourcePlanStatus status={status}/>
    {status?.setting&&<p className="text-xs text-slate-600">設定時間 {new Date(status.setting.created*1000).toLocaleString()} · 相容依據：{status.setting.evidence}</p>}
    <form className="space-y-3" onSubmit={e=>{e.preventDefault();void action.run(async()=>{await clinical('/clinical/default-plans',{source,mode,plan_id:mode==='plan'?planId:null,evidence});setEvidence('');onSaved()})}}>
      <ErrorNotice message={action.error}/>
      <div className="flex flex-wrap gap-4 text-sm"><label className="flex items-center gap-2"><input type="radio" checked={mode==='plan'} onChange={()=>setMode('plan')}/>使用指定封存方案</label><label className="flex items-center gap-2"><input type="radio" checked={mode==='preview_only'} onChange={()=>setMode('preview_only')}/>預設僅接收及預覽</label></div>
      {mode==='plan'&&<label className="block text-sm">相容的封存方案<select aria-label={`${SOURCE_LABELS[source]}預設方案`} className="field" required value={planId} onChange={e=>setPlanId(e.target.value)}><option value="">請選擇（不會自動選最新或第一個）</option>{usable.map(p=><option key={p.id} value={p.id}>{p.name} · {new Date(p.created*1000).toLocaleString()}</option>)}</select></label>}
      {mode==='plan'&&usable.length<plans.length&&<p className="text-xs text-slate-600">已隱藏來源前處理未確認{source==='capture'?'或尚未核實病人擷取適用性':''}的方案。</p>}
      <label className="block text-sm">相容依據（必填：為何此方案適用於{SOURCE_LABELS[source]}來源）<textarea className="field" rows={2} required value={evidence} onChange={e=>setEvidence(e.target.value)}/></label>
      <button className="btn-primary" disabled={action.busy||(mode==='plan'&&!planId)}>設定為醫師端預設</button>
      <p className="text-xs text-slate-500">變更只影響之後建立的接收／擷取；進行中與歷史會話仍使用建立時鎖定的方案。</p>
    </form></article>
}

export function ClinicalPlans(){
  const plans=useClinical<ClinicalPlan[]>('/clinical/plans'),defaults=useClinical<Defaults>('/clinical/default-plans'),action=useAction(),[mode,setMode]=useState('unknown')
  const [modelId,setModelId]=useState(''),[segmenterId,setSegmenterId]=useState('')
  return <div className="space-y-6"><h1 className="text-2xl font-bold">醫師分析方案</h1><ErrorNotice message={action.error||plans.error||defaults.error}/>
    <section className="rounded-xl border bg-white p-6"><h2 className="mb-2 text-xl font-bold">醫師端預設分析設定</h2><p className="mb-4 text-sm text-slate-600">醫師端接收影像時自動使用此處指定的不可變方案版本。研究區的預設模型、最新訓練或清單順序都不會被採用。圖片傳輸與設備擷取分開設定，避免把不相容的前處理用在另一種來源。</p>
      <div className="grid gap-4 lg:grid-cols-2">{['network_demo','capture'].map(source=><DefaultPlanForm key={source} source={source} status={defaults.data?.sources?.[source]} plans={plans.data||[]} onSaved={defaults.refresh}/>)}</div>
      {!!defaults.data?.history?.length&&<details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">預設設定歷史（不可修改）</summary><ul className="mt-2 space-y-1 text-sm">{defaults.data.history.map(h=><li key={h.id}>{new Date(h.created*1000).toLocaleString()} · {h.source==='capture'?'設備擷取':'圖片傳輸'} · {h.mode==='preview_only'?'僅接收及預覽':h.plan_name} · {h.evidence}</li>)}</ul></details>}
    </section>
    <section className="rounded-xl border bg-white p-6"><h2 className="mb-4 text-xl font-bold">建立不可變分析方案</h2><p className="mb-5 text-sm text-slate-600">來源尺寸不代表已完成前處理。確認來源處理步驟、尺度及模型適用性後再建立方案。更新請建立新版本。</p><form className="grid gap-5 md:grid-cols-2" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void action.run(async()=>{await clinical('/clinical/plans',{name:f.get('name'),model_id:f.get('model'),segmenter_id:f.get('segmenter')||null,device:f.get('device'),profile:{mode,width:Number(f.get('width')),height:Number(f.get('height')),evidence:f.get('evidence'),validated_for_patient:f.get('validated')==='on',version:1}});plans.refresh()})}}>
    <label>方案名稱<input name="name" className="field" required/></label><ModelSelector name="model" label="分類模型" task="classification" required value={modelId} onChange={setModelId} disabled={action.busy}/><ModelSelector name="segmenter" label="分割模型" task="segmentation" value={segmenterId} onChange={setSegmenterId} disabled={action.busy}/><label>運算裝置<select name="device" className="field"><option value="auto">自動解析實際裝置</option><option value="cpu">CPU</option><option value="cuda">NVIDIA CUDA</option></select></label><label>來源前處理<select className="field" value={mode} onChange={e=>setMode(e.target.value)}><option value="unknown">未確認（僅預覽）</option><option value="legacy">Legacy 原始版面（裁切、RB）</option><option value="prepared">已核實完成前處理</option></select></label><div className="grid grid-cols-2 gap-3"><label>原始寬度<input className="field" name="width" type="number" min="1" max="16000" required={mode!=='unknown'}/></label><label>原始高度<input className="field" name="height" type="number" min="1" max="16000" required={mode!=='unknown'}/></label></div><label className="md:col-span-2">確認依據／處理步驟與特徵尺度<textarea name="evidence" className="field" rows={4} required={mode!=='unknown'}/></label><label className="flex items-center gap-3 md:col-span-2"><input name="validated" type="checkbox" disabled={mode==='unknown'}/>已另行核實適用於病人擷取來源（記錄於上述依據）</label><button className="btn-primary" disabled={action.busy}>封存模型與建立方案</button></form><p className="mt-4 text-sm text-slate-500">模型需先於模型區匯入並通過既有相容性檢查。</p></section>
    <section className="rounded-xl border bg-white p-6"><h2 className="mb-4 text-xl font-bold">已封存方案</h2>{plans.data?.map(p=><article className="border-t py-4" key={p.id}><p className="font-semibold">{p.summary?<PlanLine plan={p.summary}/>:p.name} · {p.profile.mode}{p.profile.validated_for_patient?' · 已核實病人擷取':''}</p><p className="text-sm text-slate-600">{p.profile.evidence||'待確認來源'}</p>{p.summary&&<p className="text-sm">需要案例欄位：{p.summary.requirements.length?p.summary.requirements.map(r=>r.label).join('、'):'無'}</p>}<p className="break-all font-mono text-xs">{p.id}</p></article>)}</section></div>
}
