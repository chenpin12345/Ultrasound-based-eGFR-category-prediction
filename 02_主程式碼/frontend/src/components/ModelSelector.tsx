import { useCallback, useEffect, useState } from 'react'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api } from '../lib/api'
import { InlineNotice } from './ui'

type Props={name?:string; label:string; value:string; onChange:(id:string)=>void; task:'classification'|'segmentation'; classCount?:number; architecture?:string; analysisMode?:'mlp'|'image_only'; disabled?:boolean; required?:boolean}
export function ModelSelector({name,label,value,onChange,task,classCount,architecture,analysisMode,disabled,required}:Props){
  const [search,setSearch]=useState(''),[page,setPage]=useState(0)
  useEffect(()=>{setPage(0)},[task,classCount,architecture,analysisMode])
  const query=new URLSearchParams({task,search,limit:'50',offset:String(page*50),sort:'name'})
  if(classCount)query.set('class_count',String(classCount))
  if(architecture)query.set('architecture',architecture)
  if(analysisMode)query.set('analysis_mode',analysisMode)
  const key=query.toString()
  const load=useCallback((signal?:AbortSignal)=>api.modelPage(new URLSearchParams(key),signal),[key])
  const models=useAsyncResource(load,true,`selector:${key}`)
  const loadSelected=useCallback((signal?:AbortSignal)=>api.getModel(value,signal),[value])
  const selected=useAsyncResource(loadSelected,Boolean(value),`model-detail:${value}`)
  const validSelected=selected.data?.task===task&&(!classCount||selected.data?.class_count===classCount)&&(!architecture||selected.data?.architecture===architecture)&&(!analysisMode||selected.data?.architecture?.includes('mlp')===(analysisMode==='mlp'))
  const inPage=models.data?.items.some(model=>model.id===value)
  return <div className="space-y-2">
    <label className="block"><span className="label">{label}搜尋</span><input className="field" value={search} disabled={disabled} onChange={event=>{setSearch(event.target.value);setPage(0)}} placeholder="依模型名稱搜尋"/></label>
    <label className="block"><span className="label">{label}</span><select className="field" aria-label={label} name={name} value={value} required={required} disabled={disabled} onChange={event=>onChange(event.target.value)}>
      <option value="">{required?'請選擇':'不使用'}</option>
      {value&&!inPage&&<option value={value} disabled={!validSelected}>{selected.loading?'正在確認已選模型…':validSelected?`${selected.data?.name}（已選）`:'已選模型不存在或與條件不符，請重新選擇'}</option>}
      {models.data?.items.map(model=><option key={model.id} value={model.id} disabled={!['ready','completed'].includes(model.status||'')}>{model.name} · v{model.version}{model.active?'（研究預設）':''}</option>)}
    </select></label>
    <div className="flex flex-wrap items-center gap-2 text-sm"><button type="button" className="btn-secondary" disabled={disabled||page===0} onClick={()=>setPage(p=>p-1)} aria-label={`${label}上一頁`}>上一頁</button><span>共 {models.data?.total??'…'} 筆 · 第 {page+1} 頁</span><button type="button" className="btn-secondary" disabled={disabled||!models.data||(page+1)*50>=models.data.total} onClick={()=>setPage(p=>p+1)} aria-label={`${label}下一頁`}>下一頁</button></div>
    {(models.loading||models.updating)&&<p role="status" className="text-sm text-slate-500">正在更新模型清單…</p>}
    {(models.error||models.updateError||selected.error)&&<InlineNotice tone="danger">{models.error||models.updateError||selected.error}</InlineNotice>}
    {value&&selected.data&&!validSelected&&<InlineNotice tone="warning">目前模型與篩選條件不符，請重新選擇。</InlineNotice>}
  </div>
}
