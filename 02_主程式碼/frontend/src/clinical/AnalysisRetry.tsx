import {useState} from 'react'
import {clinical} from './client'

export function AnalysisRetry({id,onChanged}:{id:string;onChanged:(message:string)=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  async function retry(){
    setBusy(true);setError('')
    try{
      const result=await clinical<{status:string;result?:{message?:string}}>(`/clinical/monitor/operations/${id}/retry`,{})
      if(result.status==='completed')onChanged('重試分析完成；新作業與新分析版本已保存，原作業與已保存報告不覆寫。')
      else{
        setError(`重試仍未完成：${result.result?.message||result.status}。新作業紀錄已保留。`)
        onChanged('')
      }
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <div className="space-y-2"><p className="text-sm text-slate-600">使用原影像、同一封存方案及目前檢查基本資料建立新分析；不覆寫舊版本。</p><button type="button" className="btn-secondary" disabled={busy} onClick={()=>void retry()}>{busy?'正在執行新分析…':'使用同一方案重試分析'}</button>{error&&<p role="alert" className="text-sm text-red-800">{error} 不會自動重試，請先重新整理作業狀態。</p>}</div>
}
