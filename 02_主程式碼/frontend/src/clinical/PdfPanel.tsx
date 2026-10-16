import { useEffect,useId,useRef,useState } from 'react'
import { clinical } from './client'
import { useAction,useClinical } from './hooks'
import { ErrorNotice } from './Components'

interface Artifact {id:string;version:number;template_version:number;variant:string;status:string;sha256:string|null;created:number;error:string|null;url:string|null}
const labels:Record<string,string>={generating:'產生中',ready:'可預覽',deleting:'刪除中',deleted:'PDF 已刪除',failed:'產生失敗',interrupted:'產生中斷',deletion_failed:'刪除未完成'}
export function PdfPanel({reportId,version,disabled=false}:{reportId:string;version:number;disabled?:boolean}) {
  const endpoint=`/clinical/reports/${reportId}/versions/${version}/pdf`
  const records=useClinical<{variant:string;items:Artifact[]}>(endpoint+'-artifacts')
  const action=useAction(),[target,setTarget]=useState<Artifact>(),[reason,setReason]=useState(''),[message,setMessage]=useState('')
  const dialog=useRef<HTMLDialogElement>(null),title=useId()
  const current=records.data?.items.find(row=>row.variant===records.data?.variant)
  useEffect(()=>{if(target)dialog.current?.showModal();else dialog.current?.close()},[target])
  const generate=()=>action.run(async()=>{await clinical(endpoint,{});setMessage('PDF 已產生；內容來自此報告版本的固定快照。');records.refresh()})
  const remove=()=>action.run(async()=>{
    if(!target||!reason.trim())return
    await clinical(`/clinical/pdf-artifacts/${target.id}`,{expected_sha256:target.sha256,reason},'DELETE')
    setTarget(undefined);setMessage('指定 PDF 檔已刪除。報告與分析版本保留；預覽或下載不會重新產生。');records.refresh()
  })
  return <section className="space-y-4 rounded-xl border bg-slate-50 p-4" aria-label="PDF 產物管理">
    <h3 className="font-bold">此報告版本的 PDF</h3><p className="text-sm text-slate-600">須明確產生或重建；開啟此頁不會自動建立 PDF。重建不保證檔案位元組與舊檔相同。</p>
    <ErrorNotice message={records.error||action.error}/>{message&&<p role="status" className="text-teal-800">{message}</p>}
    <p role="status">{current?labels[current.status]||current.status:'尚未產生 PDF'}{current&&` · 模板 v${current.template_version}`}</p>
    <div className="flex flex-wrap gap-3"><button type="button" className="btn-primary" disabled={disabled||action.busy||!records.data||current?.status==='ready'} onClick={generate}>{action.busy?'處理中…':current?'重新產生 PDF':'產生 PDF'}</button><button type="button" className="btn-secondary" onClick={records.refresh}>更新 PDF 狀態</button>
      {current?.status==='ready'&&current.url&&<a className="btn-secondary" href={current.url+'?download=true'}>下載此版本 PDF</a>}
      {current&&['ready','deletion_failed'].includes(current.status)&&<button type="button" className="btn-danger" disabled={disabled||action.busy} onClick={()=>{setReason('');setTarget(current)}}>{current.status==='deletion_failed'?'重試刪除 PDF':'刪除此 PDF 檔案'}</button>}
    </div>
    {current?.status==='ready'&&current.url&&<iframe key={current.id} title="報告 PDF 預覽" className="h-[700px] w-full rounded-lg border bg-white" src={current.url}/>}
    <details><summary className="cursor-pointer py-2">產物歷史與雜湊（{records.data?.items.length??0}）</summary><ul className="space-y-3">{records.data?.items.map(row=><li key={row.id} className="break-all text-xs">{labels[row.status]||row.status} · {row.variant==='void'?'作廢衍生版':'原狀態版'} · {new Date(row.created*1000).toLocaleString()}<br/>{row.id}<br/>SHA-256：{row.sha256||'尚未完成'}{row.error&&<p className="text-red-800">{row.error}</p>}</li>)}</ul></details>
    <dialog ref={dialog} aria-labelledby={title} className="w-[calc(100%_-_2rem)] max-w-lg rounded-2xl border p-6 shadow-xl backdrop:bg-slate-950/60" onCancel={event=>{event.preventDefault();if(!action.busy)setTarget(undefined)}}>
      <h2 id={title} className="text-xl font-bold">確認刪除此 PDF 檔案</h2><p className="my-4">只刪除指定產物，不刪除報告、影像或分析版本。之後必須明確重建，且來源完整時才可重建。</p><p className="break-all text-xs">產物：{target?.id}<br/>SHA-256：{target?.sha256}</p>
      <label className="my-4 block"><span className="label">PDF 刪除理由（必填）</span><textarea aria-label="PDF 刪除理由（必填）" className="field" value={reason} maxLength={2000} disabled={action.busy} onChange={event=>setReason(event.target.value)}/></label><ErrorNotice message={action.error}/>
      <div className="flex flex-wrap gap-3"><button type="button" autoFocus className="btn-secondary" disabled={action.busy} onClick={()=>setTarget(undefined)}>取消</button><button type="button" className="btn-danger" disabled={action.busy||!reason.trim()} onClick={remove}>確認刪除 PDF</button></div>
    </dialog>
  </section>
}
