import { useCallback, useEffect, useState } from 'react'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { humanApiError, requestJson } from '../lib/api'
import type { PageResult } from '../types/api'
import { InlineNotice } from './ui'

interface Sample {id:string;display_name:string;has_mask:boolean}
interface Checked {preflight_sha256:string;evidence:{image_name:string;image_sha256:string;mask_sha256:string}}
export function ReferenceMaskRegistration({datasetId}:{datasetId:string}) {
  const [sampleId,setSampleId]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(0)
  const [source,setSource]=useState(''),[reviewer,setReviewer]=useState(''),[method,setMethod]=useState('manual_annotation'),[confirmed,setConfirmed]=useState(false)
  const [checked,setChecked]=useState<Checked>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false)
  const load=useCallback((signal?:AbortSignal)=>requestJson<PageResult<Sample>>(`/datasets/${encodeURIComponent(datasetId)}/samples?limit=50&offset=${page*50}&search=${encodeURIComponent(search)}`,{signal}),[datasetId,page,search])
  const samples=useAsyncResource(load,Boolean(datasetId),`reference-samples:${datasetId}:${page}:${search}`)
  const body=JSON.stringify({dataset_id:datasetId,sample_id:sampleId,source,reviewer,annotation_method:method,independent_of_evaluated_model:confirmed,coordinate_mapping:'identity'})
  useEffect(()=>{setChecked(undefined);setSaved(false)},[body])
  const act=async(save:boolean)=>{setBusy(true);setError('');try{
    if(save){await requestJson('/evaluations/reference-masks',{method:'POST',body:JSON.stringify({...JSON.parse(body),expected_preflight_sha256:checked?.preflight_sha256})});setSaved(true);setChecked(undefined)}
    else setChecked(await requestJson<Checked>('/evaluations/reference-masks/preflight',{method:'POST',body}))
  }catch(e){setError(humanApiError(e));setChecked(undefined)}finally{setBusy(false)}}
  return <details className="mt-4 rounded-xl border border-slate-300 p-4"><summary className="cursor-pointer py-2 font-semibold">登錄獨立參考 Mask 來源（不產生遮罩）</summary>
    <p className="my-3 text-sm">僅登錄已匯入且同座標的 512×512 二值 Mask。程式核對檔案雜湊與尺寸；獨立性及標註品質是以下人員的聲明，不是醫師身分驗證。不得登錄本次模型自行生成的 Mask。</p>
    <fieldset disabled={busy||saved} className="grid gap-3 sm:grid-cols-2">
      <label><span className="label">搜尋參考影像</span><input className="field" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);setSampleId('')}}/></label>
      <label><span className="label">來源影像</span><select aria-label="來源影像" className="field" value={sampleId} onChange={e=>setSampleId(e.target.value)}><option value="">請選擇有參考 Mask 的影像</option>{samples.data?.items.map(sample=><option key={sample.id} value={sample.id} disabled={!sample.has_mask}>{sample.display_name}{sample.has_mask?'':'（無 Mask）'}</option>)}</select></label>
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2"><button className="btn-secondary" type="button" disabled={!page} onClick={()=>{setPage(p=>p-1);setSampleId('')}}>上一頁影像</button><span>第 {page+1} 頁 · 共 {samples.data?.total??'…'} 張</span><button className="btn-secondary" type="button" disabled={!samples.data||(page+1)*50>=samples.data.total} onClick={()=>{setPage(p=>p+1);setSampleId('')}}>下一頁影像</button></div>
      <label><span className="label">標註來源類型</span><select className="field" value={method} onChange={e=>setMethod(e.target.value)}><option value="manual_annotation">人工標註</option><option value="external_reference">外部參考標註</option></select></label>
      <label><span className="label">來源確認人員（自行填寫）</span><input className="field" maxLength={200} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label>
      <label className="sm:col-span-2"><span className="label">來源、標註方法與對位依據（至少 10 字）</span><textarea className="field" maxLength={4000} value={source} onChange={e=>setSource(e.target.value)}/></label>
      <label className="flex items-start gap-3 py-3 sm:col-span-2"><input className="mt-1" type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>確認不是待評估模型的自行輸出，且與所選影像具有相同座標。來源登錄後不可覆寫。</span></label>
      <button className="btn-secondary" type="button" disabled={!sampleId||!reviewer.trim()||source.trim().length<10||!confirmed} onClick={()=>void act(false)}>預檢參考來源</button>
      {checked&&<div className="space-y-2 break-all rounded-lg bg-slate-50 p-3 text-xs sm:col-span-2"><p>{checked.evidence.image_name}</p><p>影像 SHA：{checked.evidence.image_sha256}</p><p>Mask SHA：{checked.evidence.mask_sha256}</p><button className="btn-primary" type="button" onClick={()=>void act(true)}>確認並保存不可變來源紀錄</button></div>}
    </fieldset>{busy&&<p role="status">正在核對來源…</p>}{saved&&<p role="status" className="mt-3 text-teal-800">來源已保存。請重新檢查評估範圍，再提交評估。</p>}{(error||samples.error)&&<InlineNotice tone="danger">{error||samples.error}</InlineNotice>}
  </details>
}
