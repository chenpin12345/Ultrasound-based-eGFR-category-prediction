import { useEffect, useId, useRef, useState } from 'react'
import { InlineNotice } from '../components/ui'
import { clinical } from './client'

type Entity='patients'|'exams'|'reports'
type Action='archive'|'trash'|'restore'|'delete_empty'
const labels:Record<Action,string>={archive:'封存',trash:'移至回收區',restore:'恢復',delete_empty:'永久刪除空白紀錄'}
interface Preflight {name:string;state:string;effective_state:string;revision:number;references:Record<string,number>;parents:{entity:string;id:string;state:string}[];allowed:boolean;blocking_reasons:string[];recoverable:boolean}
export function LifecycleActions({entity,id,state,onChanged}:{entity:Entity;id:string;state:string;onChanged:()=>void}) {
  const [action,setAction]=useState<Action>(),[checked,setChecked]=useState<Preflight>(),[reason,setReason]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const dialog=useRef<HTMLDialogElement>(null),titleId=useId()
  useEffect(()=>{if(action&&!dialog.current?.open)dialog.current?.showModal();if(!action&&dialog.current?.open)dialog.current?.close()},[action])
  const prepare=async(operation:Action)=>{setAction(operation);setChecked(undefined);setReason('');setError('');setBusy(true);try{setChecked(await clinical<Preflight>(`/clinical/lifecycle/${entity}/${id}?action=${operation}`))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  const submit=async()=>{if(!action||!checked?.allowed||!reason.trim())return;setBusy(true);setError('');try{await clinical(`/clinical/lifecycle/${entity}/${id}`,{action,expected_revision:checked.revision,reason});setAction(undefined);onChanged()}catch(e){setError((e as Error).message);setChecked(undefined)}finally{setBusy(false)}}
  return <><div className="flex flex-wrap gap-2">{(state==='normal'?['archive','trash']:state==='archived'?['restore','trash']:['restore']).map(operation=><button type="button" className="btn-secondary" key={operation} onClick={()=>void prepare(operation as Action)}>{labels[operation as Action]}</button>)}{entity!=='reports'&&<button type="button" className="btn-ghost text-red-800" onClick={()=>void prepare('delete_empty')}>檢查永久刪除條件</button>}</div>
    <dialog ref={dialog} aria-labelledby={titleId} className="w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-slate-300 p-6 text-slate-800 shadow-xl backdrop:bg-slate-950/60" onCancel={e=>{e.preventDefault();if(!busy)setAction(undefined)}}>
      <h2 id={titleId} className="text-xl font-bold">{action?labels[action]:'生命週期操作'}</h2>
      {busy&&!checked&&<p role="status" className="my-4">正在重新確認對象與引用…</p>}
      {checked&&<div className="my-4 space-y-3"><p className="font-semibold">{checked.name}</p><p className="text-sm">{checked.recoverable?'不刪除影像或歷史版本，可依父子層規則恢復。':'僅限無關聯的誤建／空白紀錄，刪除後不能在介面恢復。此操作不刪除影像檔。'}</p><ul className="list-inside list-disc text-sm">{Object.entries(checked.references).map(([key,value])=><li key={key}>{({exams:'檢查',frames:'影像',reports:'報告',clinical_operations:'分析作業',transfers:'傳輸引用',linked_receivers:'接收會話引用',case_data_edits:'案例資料修改紀錄',versions:'報告版本'} as Record<string,string>)[key]||key}：{value}</li>)}</ul>{!checked.allowed&&<InlineNotice tone="warning">{checked.blocking_reasons.join(' ')}</InlineNotice>}<label className="block"><span className="label">操作理由（必填）</span><textarea className="field" maxLength={2000} value={reason} disabled={busy||!checked.allowed} onChange={e=>setReason(e.target.value)}/></label><p className="text-xs text-slate-600">版本 {checked.revision}。提交時會再次檢查；不會自動重送失敗操作。</p></div>}
      {error&&<InlineNotice tone="danger">{error} 請關閉後重新預檢。</InlineNotice>}
      <div className="mt-5 flex flex-wrap justify-end gap-3"><button className="btn-secondary" type="button" autoFocus disabled={busy} onClick={()=>setAction(undefined)}>取消</button><button className={action==='delete_empty'?'btn-danger':'btn-primary'} type="button" disabled={busy||!checked?.allowed||!reason.trim()} onClick={()=>void submit()}>{busy?'處理中…':`確認${action?labels[action]:''}`}</button></div>
    </dialog>
  </>
}
