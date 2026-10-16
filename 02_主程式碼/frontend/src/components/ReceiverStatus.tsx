import { Link } from 'react-router-dom'
import { useClinical, useAction } from '../clinical/hooks'
import { clinical } from '../clinical/client'

interface ReceiverSession {id:string; state:string; expires:number}
export function ReceiverStatus() {
  const sessions=useClinical<ReceiverSession[]>('/clinical/demo-sessions',5000), action=useAction()
  const active=sessions.data?.find(item=>item.state==='active')
  if (!active && !sessions.error && !action.error) return null
  return <aside className="border-b border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-950" aria-label="背景接收狀態">
    {active && <div className="flex flex-wrap items-center justify-center gap-3"><span role="status">雙機接收進行中 · 到期 {new Date(active.expires*1000).toLocaleString()}</span><Link className="underline" to="/clinical/demo">查看接收</Link><button className="btn-secondary" disabled={action.busy} onClick={()=>{if(window.confirm('結束接收會撤銷傳輸權限，並清理未保存暫存影像。確定結束？'))void action.run(async()=>{await clinical('/clinical/demo-sessions/'+active.id+'/stop',{});sessions.refresh()})}}>結束接收</button></div>}
    {(sessions.error||action.error)&&<p role="alert">接收狀態：{action.error||sessions.error}</p>}
  </aside>
}
