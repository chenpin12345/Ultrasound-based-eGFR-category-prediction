import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Card, InlineNotice, PageHeader } from '../components/ui'
import { useClinical } from './hooks'
import { stateLabel } from './client'
import { LifecycleActions } from './LifecycleAction'
import { CleanupRetry } from './CleanupRetry'
import { AnalysisRetry } from './AnalysisRetry'

const sections={patients:'病人',exams:'檢查／示範',receivers:'接收會話',operations:'分析作業',previews:'預覽分析',reports:'報告',cleanup:'暫存清理',audit:'操作紀錄'}
type Section=keyof typeof sections
const operationLabel=(section:Section,status:string)=>section==='cleanup'&&status==='pending'?'等待清理':stateLabel[status]||status
interface Entry {id:string;created:number;name?:string;code?:string;title?:string;kind?:string;patient_name?:string;patient_code?:string;state?:string;status?:string;current_version?:number;exam_id?:string;plan_name?:string;error_code?:string;error_message?:string;actor_name?:string;action?:string;entity?:string;expires?:number;completed?:number;exam_count?:number;frame_count?:number;report_count?:number;version_count?:number;batch_count?:number;retry_of?:string}
interface Page {items:Entry[];total:number;updated_at:number}
const when=(value?:number)=>value==null?'—':new Date(value*1000).toLocaleString('zh-TW')

export function ClinicalMonitor(){
  const [params,setParams]=useSearchParams()
  const chosen=params.get('section')||'patients',section:Section=chosen in sections?chosen as Section:'patients'
  return <div className="space-y-5"><PageHeader title="紀錄與作業監控" description="查看病人、檢查、接收與分析作業的本機紀錄；不是生命徵象監控。"/>
    <nav className="flex flex-wrap gap-2" aria-label="監控紀錄分類">{Object.entries(sections).map(([key,label])=><button type="button" className={key===section?'btn-primary':'btn-secondary'} aria-pressed={key===section} key={key} onClick={()=>setParams({section:key})}>{label}</button>)}</nav>
    <MonitorList key={section} section={section}/>
  </div>
}

function MonitorList({section}:{section:Section}) {
  const [lifecycle,setLifecycle]=useState('normal'),[message,setMessage]=useState('')
  const [search,setSearch]=useState(''),[status,setStatus]=useState(''),[kind,setKind]=useState(''),[sort,setSort]=useState('newest'),[from,setFrom]=useState(''),[to,setTo]=useState(''),[page,setPage]=useState(0),[poll,setPoll]=useState(true)
  const query=new URLSearchParams({search,sort,offset:String(page*50),limit:'50',lifecycle})
  if(status)query.set('status',status)
  if(kind)query.set('kind',kind)
  if(from)query.set('date_from',String(new Date(`${from}T00:00:00`).getTime()/1000))
  if(to)query.set('date_to',String(new Date(`${to}T23:59:59.999`).getTime()/1000))
  const records=useClinical<Page>(`/clinical/monitor/${section}?${query}`,poll?5000:0)
  const update=(setter:(value:string)=>void,value:string)=>{setter(value);setPage(0)}
  const statuses:Partial<Record<Section,string[]>>={reports:['draft','pending','confirmed','void'],operations:['running','completed','unavailable','failed','interrupted'],previews:['running','completed','failed','cancelled','interrupted'],receivers:['active','interrupted','ended','expired'],cleanup:['pending','completed','failed','interrupted']}
  return <><Card className="p-5"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    {['patients','exams','reports','operations','previews'].includes(section)&&<label><span className="label">生命週期／回收區</span><select aria-label="生命週期／回收區" className="field" value={lifecycle} onChange={e=>update(setLifecycle,e.target.value)}><option value="normal">正常紀錄</option><option value="archived">封存紀錄（含父層限制）</option><option value="trashed">回收區（不自動清空）</option></select></label>}
    <label><span className="label">搜尋名稱或識別碼</span><input className="field" value={search} onChange={e=>update(setSearch,e.target.value)}/></label>
    {statuses[section]&&<label><span className="label">作業／報告狀態</span><select aria-label="作業／報告狀態" className="field" value={status} onChange={e=>update(setStatus,e.target.value)}><option value="">全部狀態</option>{statuses[section]?.map(value=><option key={value} value={value}>{operationLabel(section,value)}</option>)}</select></label>}
    {['exams','reports','operations','previews'].includes(section)&&<label><span className="label">資料類型</span><select aria-label="資料類型" className="field" value={kind} onChange={e=>update(setKind,e.target.value)}><option value="">病人及示範</option><option value="patient">病人檢查</option><option value="demo">示範案例</option></select></label>}
    <label><span className="label">開始日期（本機時區）</span><input className="field" type="date" value={from} onChange={e=>update(setFrom,e.target.value)}/></label>
    <label><span className="label">結束日期（本機時區）</span><input className="field" type="date" value={to} onChange={e=>update(setTo,e.target.value)}/></label>
    <label><span className="label">建立時間排序</span><select aria-label="建立時間排序" className="field" value={sort} onChange={e=>update(setSort,e.target.value)}><option value="newest">最新在前</option><option value="oldest">最早在前</option></select></label>
  </div><div className="mt-4 flex flex-wrap items-center gap-3"><button className="btn-secondary" type="button" onClick={records.refresh}>重新整理</button><label className="flex items-center gap-2 py-2"><input type="checkbox" checked={poll} onChange={e=>setPoll(e.target.checked)}/>每 5 秒背景更新</label><p className="text-sm text-slate-600">更新時間：{when(records.data?.updated_at)}</p></div></Card>
    {records.error&&<InlineNotice tone="danger">讀取／更新失敗：{records.error}。已載入資料可能過期，請重新整理。</InlineNotice>}
    {message&&<p role="status" className="rounded-lg bg-teal-50 p-4 text-teal-900">{message}</p>}
    <Card className="p-5"><h2 className="section-title">{sections[section]}紀錄</h2><div className="my-4 flex flex-wrap items-center gap-3"><button className="btn-secondary" disabled={!page} onClick={()=>setPage(p=>p-1)}>上一頁紀錄</button><span>第 {page+1} 頁 · 共 {records.data?.total??'…'} 筆 · 每頁 50 筆</span><button className="btn-secondary" disabled={!records.data||(page+1)*50>=records.data.total} onClick={()=>setPage(p=>p+1)}>下一頁紀錄</button></div>
      {!records.data&&!records.error&&<p role="status">正在載入紀錄…</p>}
      {records.data?.items.length===0&&<p className="rounded-lg bg-slate-50 p-6 text-slate-600">此範圍尚無紀錄，請檢查篩選條件。</p>}
      <ul className="divide-y">{records.data?.items.map(row=><li key={row.id} className="space-y-2 py-4"><div className="flex flex-wrap items-start justify-between gap-3"><h3 className="font-bold">{row.name||row.title||row.plan_name||row.action||sections[section]}{row.code&&` · ${row.code}`}</h3><span>{operationLabel(section,row.status||row.state||'')}</span></div>
        {(row.patient_name||row.kind==='demo')&&<p className="text-sm">{row.kind==='demo'?'示範案例':`${row.patient_name} · ${row.patient_code}`}</p>}
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">{([['exam_count','檢查'],['frame_count','影像'],['report_count','報告'],['version_count','版本'],['batch_count','傳输批次']] as const).map(([key,label])=>row[key]!=null&&<span key={key}>{label}：{row[key]}</span>)}{row.current_version!=null&&<span>目前版本：v{row.current_version}</span>}</div>
        <p className="text-sm text-slate-600">建立：{when(row.created)}{row.completed!=null&&` · 結束：${when(row.completed)}`}{row.expires!=null&&` · 到期：${when(row.expires)}`}</p>
        {row.plan_name&&['operations','previews'].includes(section)&&<p className="text-sm">採用方案：{row.plan_name}</p>}{row.actor_name&&<p className="text-sm">操作者：{row.actor_name}（不代表已驗證判讀醫師）</p>}
        {row.error_message&&<p role="status" className="text-sm text-red-800">{row.error_code}：{row.error_message}</p>}
        <details><summary className="cursor-pointer py-2 text-sm text-slate-600">識別與追溯資訊</summary><p className="break-all text-xs">{row.id}{row.entity&&` · 對象 ${row.entity}`}{row.retry_of&&` · 前次作業 ${row.retry_of}`}</p></details>
        {lifecycle!=='trashed'&&section==='exams'&&<Link className="btn-secondary" to={`/clinical/exams?exam=${encodeURIComponent(row.id)}`}>查看檢查／案例</Link>}{lifecycle!=='trashed'&&section==='reports'&&<Link className="btn-secondary" to={`/clinical/reports?report=${encodeURIComponent(row.id)}`}>查看報告</Link>}{lifecycle!=='trashed'&&section==='operations'&&row.exam_id&&<Link className="btn-secondary" to={`/clinical/exams?exam=${encodeURIComponent(row.exam_id)}`}>查看分析影像</Link>}
      {section==='cleanup'&&['failed','interrupted'].includes(row.status||'')&&<CleanupRetry id={row.id} onChanged={()=>{setMessage('指定作業的未保存暫存影像已刪除，不能從回收區恢復；作業紀錄仍保留。');records.refresh()}}/>}
      {section==='operations'&&lifecycle==='normal'&&['failed','unavailable','interrupted'].includes(row.status||'')&&<AnalysisRetry id={row.id} onChanged={value=>{setMessage(value);records.refresh()}}/>}
      {(['patients','exams','reports'] as string[]).includes(section)&&<LifecycleActions entity={section as 'patients'|'exams'|'reports'} id={row.id} state={lifecycle} onChanged={()=>{setMessage('操作已完成；紀錄清單已重新讀取。永久刪除的空白紀錄不能由介面恢復，其餘請從封存／回收區操作。');records.refresh()}}/>}
      </li>)}</ul>
    </Card></>
}
