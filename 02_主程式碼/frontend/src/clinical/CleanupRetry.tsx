import { useEffect, useId, useRef, useState } from 'react'
import { InlineNotice } from '../components/ui'
import { clinical } from './client'

export function CleanupRetry({id,onChanged}:{id:string;onChanged:()=>void}) {
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[reason,setReason]=useState(''),[error,setError]=useState('')
  const dialog=useRef<HTMLDialogElement>(null),title=useId()
  useEffect(()=>{if(open&&!dialog.current?.open)dialog.current?.showModal();if(!open&&dialog.current?.open)dialog.current?.close()},[open])
  async function submit(){
    if(!reason.trim()||busy)return
    setBusy(true);setError('')
    try{await clinical(`/clinical/monitor/cleanup/${id}/retry`,{reason});setOpen(false);onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <><button className="btn-secondary" type="button" onClick={()=>{setError('');setReason('');setOpen(true)}}>重試暫存清理</button>
    <dialog ref={dialog} aria-labelledby={title} className="w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-slate-300 p-6 text-slate-800 shadow-xl backdrop:bg-slate-950/60" onCancel={e=>{e.preventDefault();if(!busy)setOpen(false)}}>
      <h2 id={title} className="text-xl font-bold">確認重試暫存清理</h2>
      <p className="my-4">僅刪除此作業記錄的未保存暫存影像，無法從回收區恢復。提交時會重新檢查保存、分析與報告引用；不會清空回收區或刪除已保存影像。</p>
      <p className="break-all text-xs text-slate-600">作業：{id}</p>
      <label className="my-4 block"><span className="label">重試理由（必填）</span><textarea className="field" value={reason} maxLength={2000} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
      {error&&<InlineNotice tone="danger">{error} 未確認完成，不會自動重試。</InlineNotice>}
      <div className="mt-5 flex flex-wrap justify-end gap-3"><button className="btn-secondary" type="button" autoFocus disabled={busy} onClick={()=>setOpen(false)}>取消</button><button className="btn-danger" type="button" disabled={busy||!reason.trim()} onClick={()=>void submit()}>{busy?'清理中…':'確認重試清理'}</button></div>
    </dialog>
  </>
}
