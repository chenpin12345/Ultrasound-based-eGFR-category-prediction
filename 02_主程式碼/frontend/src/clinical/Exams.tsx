import { useEffect,useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { clinical,diabetesLabel,requirementLabel,stateLabel } from './client'
import { useAction,useClinical } from './hooks'
import { ErrorNotice,FrameResult,PlanLine,PlanSelect } from './Components'
import { ClinicalRecordPicker } from './RecordPicker'

export function ExamsPage() {
  const [params,setParams]=useSearchParams();const id=params.get('exam')||''
  const [revision,setRevision]=useState(0)
  const action=useAction();const [patientId,setPatientId]=useState(''),[kind,setKind]=useState('patient')
  return <><div><p className="text-sm text-teal-700">檢查管理</p><h1 className="mt-1 text-2xl font-bold">病人與檢查</h1></div><ErrorNotice message={action.error}/>
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]"><aside className="space-y-5"><details className="rounded-xl border bg-white p-5"><summary className="cursor-pointer font-bold">新增病人</summary><form className="mt-4 space-y-3" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void action.run(async()=>{const p=await clinical('/clinical/patients',{code:f.get('code'),name:f.get('name')});setRevision(r=>r+1);setPatientId(p.id)})}}><label className="block">識別碼<input name="code" required className="field"/></label><label className="block">姓名<input name="name" required className="field"/></label><button className="btn-primary" disabled={action.busy}>建立病人</button></form></details>
    <form className="space-y-3 rounded-xl border bg-white p-5" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void action.run(async()=>{const value=await clinical('/clinical/exams',{kind,patient_id:kind==='patient'?patientId:null,title:f.get('title'),side:f.get('side')});setRevision(r=>r+1);setParams({exam:value.id})})}}><h2 className="font-bold">建立檢查</h2><label className="block">類型<select className="field" value={kind} onChange={e=>setKind(e.target.value)}><option value="patient">病人檢查</option><option value="demo">獨立示範案例</option></select></label>{kind==='patient'&&<ClinicalRecordPicker section="patients" label="病人" value={patientId} onChange={setPatientId} revision={revision} required disabled={action.busy}/>}<label className="block">檢查名稱<input className="field" name="title" required defaultValue="腎臟超音波"/></label><label className="block">側別<select className="field" name="side"><option value="unspecified">尚未確認</option><option value="left">左側</option><option value="right">右側</option><option value="both">雙側</option></select></label><button className="btn-primary" disabled={action.busy}>建立檢查</button></form>
    <div className="rounded-xl border bg-white p-3"><ClinicalRecordPicker section="exams" label="選擇檢查／案例" value={id} onChange={exam=>setParams({exam})} revision={revision}/></div></aside>
    <section>{id?<ExamDetail key={id} id={id} frameId={params.get('frame')||''}/>:<div className="rounded-xl border border-dashed p-12 text-center text-slate-600">選擇或建立檢查，檢視已接收影像與報告。</div>}</section></div></>
}

const sideLabel:Record<string,string>={unspecified:'尚未確認',left:'左側',right:'右側',both:'雙側'}

/** Case data as saved on the backend; never prefilled from another case or local storage. */
function CaseData({value,onSaved}:{value:any;onSaved:()=>void}) {
  const action=useAction(),[notice,setNotice]=useState('')
  const missing:string[]=value.transfer?.missing_now||[]
  const [editing,setEditing]=useState(missing.length>0)
  const p=value.payload,demo=value.kind==='demo'
  const rows:[string,string][]=[[demo?'案例識別':'檢查名稱',value.title],['側別',sideLabel[value.side]||value.side],['年齡',p.age??'未填寫'],['糖尿病狀態',value.diabetes_status?diabetesLabel[value.diabetes_status]:'未填寫'],['檢查名稱',p.exam_name||'—'],['檢查時間',p.exam_time||'—'],['備註',p.notes||'—'],...(demo?[['病人識別（示範，未核實）',p.patient_ref||'—'],['姓名（示範，未核實）',p.patient_name||'—']] as [string,string][]:[])]
  const highlight=(field:string)=>missing.includes(field)?'border-red-500 ring-2 ring-red-200':''
  return <div className="my-4 space-y-3">
    {value.transfer&&<div className="rounded-lg bg-slate-50 p-3 text-sm"><p>由 A 電腦傳送 · 案例資料版本 {value.revision}（{value.versions?.length||1} 筆紀錄）</p><p>接收會話鎖定方案：{value.transfer.plan_mode==='preview_only'?'僅接收及預覽':value.transfer.plan?<PlanLine plan={value.transfer.plan}/>:'舊版會話'} · 狀態：{stateLabel[value.transfer.status]||value.transfer.status}</p></div>}
    {missing.length>0&&<p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-900">待補資料：{missing.map(m=>requirementLabel[m]||m).join('、')}。保存後會自動分析一次；不會以 0 或「無」代替未填寫的值。</p>}
    {notice&&<p role="status" className="rounded-lg bg-teal-50 p-3 text-teal-900">{notice}</p>}<ErrorNotice message={action.error}/>
    {!editing?<><dl className="grid gap-2 text-sm sm:grid-cols-2">{rows.map(([k,v])=><div key={k}><dt className="text-slate-500">{k}</dt><dd className="font-medium">{String(v)}</dd></div>)}</dl><button className="btn-secondary" onClick={()=>setEditing(true)}>修改案例資料</button></>
    :<form key={value.revision} className="grid gap-4 sm:grid-cols-2" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);const text=(k:string)=>{const v=String(f.get(k)||'').trim();return v||null};void action.run(async()=>{const r=await clinical(`/clinical/exams/${value.id}/case?expected_revision=${value.revision}`,{title:text('title'),side:f.get('side'),age:f.get('age')===''?null:Number(f.get('age')),diabetes:f.get('diabetes')||null,exam_name:text('exam_name'),exam_time:text('exam_time'),notes:text('notes'),...(demo?{patient_ref:text('patient_ref'),patient_name:text('patient_name')}:{})},'PUT');setNotice(`已保存為資料版本 ${r.revision}`+(r.resumed?'，已自動排入分析。':'。先前的分析結果與報告維持原本的資料版本。'));setEditing(false);onSaved()})}}>
      <label>{demo?'案例識別':'檢查名稱'}<input name="title" className="field" required maxLength={200} defaultValue={value.title}/></label>
      <label>側別<select name="side" className="field" defaultValue={value.side}>{Object.entries(sideLabel).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
      <label>年齡（僅此案例）<input name="age" className={`field ${highlight('age')}`} type="number" min="0" max="130" step="1" defaultValue={p.age??''}/></label>
      <label>糖尿病狀態<select name="diabetes" className={`field ${highlight('has_diabetes')}`} defaultValue={value.diabetes_status||''}><option value="">未填寫</option><option value="no">無</option><option value="yes">有</option><option value="unknown">未知</option></select></label>
      <label>檢查名稱<input name="exam_name" className="field" maxLength={80} defaultValue={p.exam_name||''}/></label>
      <label>檢查時間<input name="exam_time" className="field" type="datetime-local" defaultValue={p.exam_time||''}/></label>
      {demo&&<><label>病人識別（示範顯示，未核實）<input name="patient_ref" className="field" maxLength={40} defaultValue={p.patient_ref||''}/></label><label>姓名（示範顯示，未核實）<input name="patient_name" className="field" maxLength={60} defaultValue={p.patient_name||''}/></label></>}
      <label className="sm:col-span-2">備註<textarea name="notes" className="field" maxLength={500} rows={2} defaultValue={p.notes||''}/></label>
      <div className="flex gap-3 sm:col-span-2"><button className="btn-primary" disabled={action.busy}>保存案例資料</button>{missing.length===0&&<button type="button" className="btn-secondary" onClick={()=>setEditing(false)}>取消</button>}</div>
    </form>}
  </div>
}

function ExamDetail({id,frameId}:{id:string;frameId:string}) {
  const exam=useClinical('/clinical/exams/'+id),plans=useClinical<any[]>('/clinical/plans');const action=useAction(),[plan,setPlan]=useState('')
  const loaded=!!exam.data
  // Open straight at the requested image, or at the case itself on narrow screens
  // where it sits below the creation forms.
  useEffect(()=>{if(!loaded)return;const target=frameId?document.getElementById('frame-'+frameId):window.innerWidth<1024?document.getElementById('exam-detail'):null;target?.scrollIntoView?.({block:'start'})},[frameId,loaded])
  if(!exam.data)return <ErrorNotice message={exam.error||'正在載入檢查…'}/>
  const value=exam.data
  return <div id="exam-detail" className="space-y-5"><div className="rounded-xl border bg-white p-5"><h2 className="text-xl font-bold">{value.title}</h2><p className="my-2 text-sm text-slate-600">{value.kind==='demo'?'真實影像示範 · 每張圖片為獨立案例 · 不是正式病人檢查':`病人：${value.payload.patient?.name} · ${value.payload.patient?.code}`}</p>
    <CaseData key={value.id+':'+value.revision} value={value} onSaved={exam.refresh}/>
    <div className="mt-4 flex flex-wrap gap-3"><Link className="btn-primary" to={'/clinical/reports?exam='+id}>建立此檢查報告</Link>{value.kind==='patient'&&<Link className="btn-secondary" to={'/clinical/capture?exam='+id}>前往設備接收</Link>}</div>
    <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold">進階：以指定方案手動重新分析</summary><ErrorNotice message={action.error}/><p className="my-2 text-sm text-slate-600">一般情況不需要：接收時已依會話鎖定的方案自動分析。手動分析會建立新的分析版本，不會覆寫舊版本或報告。</p><PlanSelect plans={plans.data||[]} value={plan} onChange={setPlan}/></details></div>
    {value.frames.length===0&&<p className="p-5 text-slate-600">尚無影像。病人檢查請從設備擷取；示範圖片請由 A 電腦傳送。</p>}{value.frames.map((frame:any)=><div key={frame.id} id={'frame-'+frame.id} className={`space-y-2 ${frame.id===frameId?'rounded-2xl ring-2 ring-teal-400':''}`}><FrameResult frame={frame} onSave={exam.refresh}/>{plan&&<button className="btn-secondary" disabled={action.busy} onClick={()=>action.run(async()=>{await clinical(`/clinical/frames/${frame.id}/analyze?plan_id=${plan}`,{});exam.refresh()})}>以指定方案重新分析此影像</button>}</div>)}</div>
}
