import { useEffect,useRef,useState } from 'react'
import { flushSync } from 'react-dom'
import { useSearchParams } from 'react-router-dom'
import { clinical,stateLabel } from './client'
import { useAction,useClinical } from './hooks'
import { ErrorNotice } from './Components'
import { ClinicalRecordPicker } from './RecordPicker'
import { UnsavedReportGuard } from './UnsavedReportGuard'
import { PdfPanel } from './PdfPanel'
import { ReportAnalysisPicker } from './ReportAnalysisPicker'

export function ReportsPage(){
  const [params,setParams]=useSearchParams();const id=params.get('report')||'',examId=params.get('exam')||''
  const [revision,setRevision]=useState(0)
  const refresh=()=>setRevision(r=>r+1)
  return <><div><p className="text-sm text-teal-700">判讀與輸出</p><h1 className="mt-1 text-2xl font-bold">報告中心</h1><p className="mt-2 text-slate-600">AI 附件與醫師判讀分開保存；已確認版本保留原文，修訂會建立新版本。</p></div><div className="grid gap-6 lg:grid-cols-[280px_1fr]"><aside className="space-y-4"><div className="rounded-xl border bg-white p-4"><ClinicalRecordPicker section="exams" label="為檢查建立草稿" value={examId} onChange={exam=>setParams({exam})}/></div><div className="rounded-xl border bg-white p-4"><ClinicalRecordPicker section="reports" label="選擇既有報告" value={id} onChange={report=>setParams({report})} revision={revision}/></div></aside><section>{id||examId?<ReportEditor key={id||examId} id={id} examId={examId} onCreated={newId=>{refresh();setParams({report:newId})}} onUpdate={refresh}/>:<div className="rounded-xl border border-dashed p-12 text-center text-slate-600">選擇檢查或既有報告。</div>}</section></div></>
}

function ReportEditor({id,examId,onCreated,onUpdate}:{id:string;examId:string;onCreated:(id:string)=>void;onUpdate:()=>void}){
  const report=useClinical(id?'/clinical/reports/'+id:''),exam=useClinical(examId?'/clinical/exams/'+examId:report.data?'/clinical/exams/'+report.data.exam_id:'')
  const [fields,setFields]=useState<Record<string,string>>({}),[images,setImages]=useState<string[]>([]),[ai,setAi]=useState(false),[version,setVersion]=useState(0)
  const [runIds,setRunIds]=useState<Record<string,string>>({})
  const [acknowledgedVersion,setAcknowledgedVersion]=useState<number>()
  const [dirty,setDirty]=useState(false),[baseVersion,setBaseVersion]=useState(0)
  const dirtyRef=useRef(false)
  const edit=()=>{dirtyRef.current=true;setDirty(true)}
  const action=useAction(),latest=report.data?.versions[0],locked=!!id&&report.data?.state!=='draft'
  const conflict=!!id&&!!report.data&&dirty&&report.data.current_version!==baseVersion
  const archived=report.data?.effective_lifecycle==='archived'
  const ready=!!exam.data&&(!id||!!report.data)&&!action.busy&&!conflict&&!archived
  useEffect(()=>{if(latest&&!dirtyRef.current){setFields(latest.payload.fields);setRunIds(Object.fromEntries(latest.payload.images.filter((item:any)=>item.analysis_run_id).map((item:any)=>[item.id,item.analysis_run_id])));setImages(latest.payload.images.map((i:any)=>i.id));setAi(latest.payload.include_ai);setVersion(latest.version);setBaseVersion(latest.version)}},[latest])
  async function save(operation:string,navigate=true){
    if(!ready)throw new Error('資料尚未就緒或版本已變更，請先比較內容。')
    const body={exam_id:exam.data.id,expected_version:baseVersion,fields,frame_ids:images,include_ai:ai,analysis_run_ids:Object.fromEntries(images.filter(fid=>fid in runIds).map(fid=>[fid,runIds[fid]])),action:operation,acknowledge_missing:acknowledgedVersion===baseVersion}
    const value=await clinical(id?'/clinical/reports/'+id+'/versions':'/clinical/reports',body)
    dirtyRef.current=false
    flushSync(()=>{setDirty(false);setBaseVersion(value.version);setVersion(value.version)})
    if(!id&&navigate)onCreated(value.id);else{report.refresh();onUpdate()}
  }
  return <div className="space-y-5"><UnsavedReportGuard dirty={dirty} canSave={ready&&!locked} save={()=>save('draft',false)}/>{dirty&&<p role="status" className="rounded-lg bg-amber-50 p-3 text-amber-900">有尚未保存的報告變更。背景更新不會覆蓋這些文字。</p>}{conflict&&<ErrorNotice message="另一個操作已建立新報告版本。您編輯的內容仍保留，但不能覆寫新版本；請另行保留文字後重新開啟並比較。"/>}{archived&&<p role="status" className="rounded-lg bg-slate-100 p-3 text-slate-700">此報告或父層已封存，僅供讀取；請先從紀錄監控恢復。</p>}<ErrorNotice message={action.error||report.error||exam.error}/><div className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-bold">{exam.data?.title||'載入中…'}</h2>{exam.data?.kind==='demo'&&<p className="my-4 rounded-lg bg-amber-50 p-3 text-amber-900">真實影像示範／非正式診斷書（每頁固定標記）</p>}<p className="mb-5 text-sm text-slate-500">{id?`${report.data?.state==='pending'?'待確認':stateLabel[report.data?.state]||''} · v${report.data?.current_version||''}`:'新報告草稿'}</p>
    <fieldset disabled={!!locked||!ready} className="space-y-5">
      <h3 className="font-semibold">超音波影像（最多 20 張，僅此檢查已保存影像）</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{exam.data?.frames.filter((f:any)=>f.saved).map((f:any)=><label className="rounded-lg border p-2" key={f.id}><input aria-label={'選取影像 '+f.id.slice(0,8)} type="checkbox" checked={images.includes(f.id)} disabled={!images.includes(f.id)&&images.length>=20} onChange={event=>{edit();setImages(event.target.checked?[...images,f.id]:images.filter(x=>x!==f.id));if(event.target.checked)setRunIds(current=>({...current,[f.id]:f.result?.analysis_run_id||''}))}}/><img className="h-28 w-full object-contain" src={f.url} alt={'代表影像 '+f.id.slice(0,8)}/><span className="text-xs">{f.id.slice(0,8)}</span></label>)}</div>
      <label className="flex items-center gap-2"><input type="checkbox" checked={ai} onChange={event=>{edit();setAi(event.target.checked)}}/>附上已保存的 AI 輔助資料</label>
      {ai&&images.map(fid=><ReportAnalysisPicker key={fid} frameId={fid} value={runIds[fid]||''} legacy={!(fid in runIds)&&!!latest?.payload.images.find((item:any)=>item.id===fid)?.analysis} onChange={run=>{edit();setRunIds(current=>({...current,[fid]:run}))}}/>)}
      {!images.length&&<p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">尚未選取影像，草稿可以保存；不代表資料完整。</p>}
      {[['findings','檢查所見'],['diagnosis','醫師判讀'],['advice','建議'],['notes','備註'],['physician','判讀醫師'],['institution','院所']].map(([key,label])=><label key={key} className="block font-semibold">{label}<textarea aria-label={label} className="field mt-2 font-normal" rows={key==='diagnosis'||key==='findings'?4:2} maxLength={10000} value={fields[key]||''} onChange={event=>{edit();setFields({...fields,[key]:event.target.value})}}/></label>)}
      <p className="text-sm text-slate-600">判讀醫師由人工填寫，不是本機操作身分，也不是已驗證電子簽章。</p>
    </fieldset>
    {!!report.data?.missing_items?.length&&<div className="my-4 space-y-2 rounded-lg bg-amber-50 p-4 text-amber-900"><h3 className="font-semibold">此已保存版本的缺項</h3><ul className="list-inside list-disc">{report.data.missing_items.map((item:string)=><li key={item}>{item}</li>)}</ul>{report.data.state==='pending'&&<label className="flex items-start gap-2"><input type="checkbox" checked={acknowledgedVersion===baseVersion} onChange={event=>setAcknowledgedVersion(event.target.checked?baseVersion:undefined)}/>我已確認上述缺項，仍要確認此版本。這不代表分析完整或確診。</label>}</div>}
    <div className="mt-6 flex flex-wrap gap-3">{!locked&&<button className="btn-primary" disabled={!ready} onClick={()=>action.run(()=>save('draft'))}>保存草稿版本</button>}{id&&report.data?.state==='draft'&&<button className="btn-secondary" disabled={!ready} onClick={()=>action.run(()=>save('pending'))}>送交確認</button>}{id&&report.data?.state==='pending'&&<><button className="btn-primary" disabled={!ready} onClick={()=>action.run(()=>save('confirmed'))}>確認此版本</button><button className="btn-secondary" disabled={!ready} onClick={()=>action.run(()=>save('draft'))}>返回草稿</button></>}{id&&report.data?.state==='confirmed'&&<button className="btn-primary" disabled={!ready} onClick={()=>action.run(()=>save('revise'))}>建立修訂草稿</button>}{id&&report.data?.state!=='void'&&<button className="btn-secondary" disabled={!ready} onClick={()=>action.run(()=>save('void'))}>作廢報告</button>}</div></div>
    {id&&report.data&&exam.data&&version>0&&<section className="space-y-4 rounded-2xl border bg-white p-5"><label className="block">預覽版本<select aria-label="預覽版本" className="field" value={version} onChange={event=>setVersion(Number(event.target.value))}>{report.data.versions.map((v:any)=><option key={v.version} value={v.version}>v{v.version} · {v.state==='pending'?'待確認':stateLabel[v.state]}</option>)}</select></label><PdfPanel key={id+':'+version+':'+report.data.state} reportId={id} version={version} disabled={archived||action.busy}/></section>}</div>
}
