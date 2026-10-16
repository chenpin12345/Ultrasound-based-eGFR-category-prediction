import { useEffect, useState } from 'react'
import { InlineNotice } from '../components/ui'
import { useClinical } from './hooks'
import { stateLabel } from './client'

interface RecordItem {id:string;name?:string;code?:string;title?:string;patient_name?:string;kind?:string;state?:string;current_version?:number}
interface Page {items:RecordItem[];total:number}
function display(row:RecordItem){return [row.code,row.name,row.kind==='demo'?'示範':row.patient_name,row.title,row.state?`${stateLabel[row.state]||row.state} · v${row.current_version}`:null].filter(Boolean).join(' · ')||row.id}
export function ClinicalRecordPicker({section,label,value,onChange,kind,revision=0,disabled=false,required=false}:{section:'patients'|'exams'|'reports';label:string;value:string;onChange:(id:string)=>void;kind?:'patient'|'demo';revision?:number;disabled?:boolean;required?:boolean}) {
  const [search,setSearch]=useState(''),[page,setPage]=useState(0)
  useEffect(()=>{setPage(0)},[kind])
  const filter=kind?`&kind=${kind}`:''
  const list=useClinical<Page>(`/clinical/monitor/${section}?search=${encodeURIComponent(search)}&offset=${page*50}&limit=50${filter}&refresh=${revision}`)
  const selected=useClinical<Page>(value?`/clinical/monitor/${section}?exact_id=${encodeURIComponent(value)}${filter}&refresh=${revision}`:'')
  const item=selected.data?.items[0],inPage=list.data?.items.some(row=>row.id===value)
  return <div className="space-y-2"><label className="block"><span className="label">{label}搜尋</span><input className="field" value={search} disabled={disabled} onChange={e=>{setSearch(e.target.value);setPage(0)}}/></label>
    <label className="block"><span className="label">{label}</span><select aria-label={label} className="field" value={value} required={required} disabled={disabled} onChange={e=>onChange(e.target.value)}><option value="">請選擇</option>{value&&!inPage&&<option value={value} disabled={!item}>{item?`${display(item)}（已選）`:selected.data?'紀錄不存在或條件不符，請重新選擇':'正在確認已選紀錄…'}</option>}{list.data?.items.map(row=><option key={row.id} value={row.id}>{display(row)}</option>)}</select></label>
    <div className="flex flex-wrap items-center gap-2 text-sm"><button className="btn-secondary" type="button" aria-label={`${label}上一頁`} disabled={disabled||page===0} onClick={()=>setPage(p=>p-1)}>上一頁</button><span>共 {list.data?.total??'…'} 筆 · 第 {page+1} 頁</span><button className="btn-secondary" type="button" aria-label={`${label}下一頁`} disabled={disabled||!list.data||(page+1)*50>=list.data.total} onClick={()=>setPage(p=>p+1)}>下一頁</button></div>
    {(list.error||selected.error)&&<InlineNotice tone="danger">{list.error||selected.error}</InlineNotice>}
  </div>
}
