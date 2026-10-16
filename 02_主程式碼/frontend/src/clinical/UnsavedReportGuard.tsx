import { useEffect,useId,useRef,useState } from 'react'
import { useBlocker } from 'react-router-dom'
import { ErrorNotice } from './Components'

export function UnsavedReportGuard({dirty,canSave,save}:{dirty:boolean;canSave:boolean;save:()=>Promise<void>}) {
  const dirtyRef=useRef(dirty);dirtyRef.current=dirty
  const blocker=useBlocker(()=>dirtyRef.current)
  const dialog=useRef<HTMLDialogElement>(null),title=useId()
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{
    const beforeUnload=(event:BeforeUnloadEvent)=>{if(dirtyRef.current){event.preventDefault();event.returnValue=''}}
    window.addEventListener('beforeunload',beforeUnload)
    return()=>window.removeEventListener('beforeunload',beforeUnload)
  },[])
  useEffect(()=>{
    if(blocker.state==='blocked'){setError('');dialog.current?.showModal()}
    else dialog.current?.close()
  },[blocker.state])
  const stay=()=>{if(!busy&&blocker.state==='blocked')blocker.reset()}
  const proceed=async()=>{
    if(blocker.state!=='blocked')return
    setBusy(true);setError('')
    try{await save();blocker.proceed()}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <dialog ref={dialog} aria-labelledby={title} className="w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border border-slate-300 p-6 text-slate-800 shadow-xl backdrop:bg-slate-950/60" onCancel={event=>{event.preventDefault();stay()}}>
    <h2 id={title} className="text-xl font-bold">報告尚未保存</h2>
    <p className="my-4">目前編輯的文字與影像選擇尚未保存。可以保存草稿後離開，或放棄本次未保存的變更。</p>
    <ErrorNotice message={error}/>
    <div className="mt-5 flex flex-wrap gap-3"><button type="button" autoFocus className="btn-secondary" disabled={busy} onClick={stay}>留在此頁</button><button type="button" className="btn-secondary" disabled={busy} onClick={()=>blocker.state==='blocked'&&blocker.proceed()}>放棄變更並離開</button><button type="button" className="btn-primary" disabled={busy||!canSave} onClick={()=>void proceed()}>{busy?'保存中…':'保存草稿並離開'}</button></div>
    {!canSave&&<p className="mt-3 text-sm text-amber-800">資料尚未載入、已受限制或發生版本衝突，不能直接保存；請留在此頁檢查。</p>}
  </dialog>
}
