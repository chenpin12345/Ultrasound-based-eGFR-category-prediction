import { useEffect,useState } from 'react'
import { Link } from 'react-router-dom'
import { clinical,requirementLabel,stateLabel } from './client'
import { useAction,useClinical } from './hooks'
import { AnalysisChoiceField,ErrorNotice,FrameResult,SourcePlanStatus,type AnalysisChoice,type SourceStatus } from './Components'

interface NetInterface {interface:string;address:string;family:number;is_up:boolean|null;kind:string;supported:boolean;note:string}
interface ReceiverSettings {interfaces:NetInterface[];recommended:string|null;saved:{mode:'auto'|'manual';host:string;port:number|null}|null;saved_check:{valid:boolean;message?:string}|null}
const kindLabel:Record<string,string>={private:'區域網路',link_local:'169.254 自動位址',loopback:'僅限本機測試',other:'非私有網段',ipv6:'IPv6（本版不支援）'}

export function DemoPage() {
  const settings=useClinical<ReceiverSettings>('/clinical/receiver-settings'),defaults=useClinical<{sources:Record<string,SourceStatus>}>('/clinical/default-plans')
  const plans=useClinical<any[]>('/clinical/plans'),sessions=useClinical<any[]>('/clinical/demo-sessions',3000)
  const [addressMode,setAddressMode]=useState<'auto'|'manual'>('auto'),[host,setHost]=useState(''),[manual,setManual]=useState(''),[port,setPort]=useState('')
  const [choice,setChoice]=useState<AnalysisChoice>({mode:'default'}),[session,setSession]=useState(''),[pair,setPair]=useState<any>(),[selected,setSelected]=useState('')
  const batches=useClinical<any[]>(session?'/clinical/demo-batches?session_id='+session:'',1500);const action=useAction()
  // Remembered address is only a suggestion; the backend revalidates it on every start.
  useEffect(()=>{const s=settings.data;if(!s||host||manual)return
    if(s.saved&&s.saved_check?.valid){if(s.saved.mode==='manual'){setAddressMode('manual');setManual(s.saved.host)}else setHost(s.saved.host);if(s.saved.port)setPort(String(s.saved.port))}
    else if(s.recommended)setHost(s.recommended)},[settings.data,host,manual])
  const status=defaults.data?.sources?.network_demo
  const effectiveHost=addressMode==='manual'?manual.trim():host
  const blocked=choice.mode==='default'&&status&&!status.analyzable&&status.mode!=='preview_only'
  const items=batches.data?.flatMap(b=>b.items)||[];const frame=items.find(i=>i.id===selected)?.frame
  const current=sessions.data?.find(s=>s.id===session)
  function exportPair(){const blob=new Blob([JSON.stringify(pair,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='image-pairing.json';link.click();URL.revokeObjectURL(url)}
  const start=()=>action.run(async()=>{const p=await clinical('/clinical/demo-sessions',{host:effectiveHost,port:port?Number(port):null,address_mode:addressMode,analysis:choice});setPair(p);setSession(p.session_id);sessions.refresh();settings.refresh()})
  return <><div><p className="text-sm text-teal-700">A → B · 原始檔案與案例資料傳輸</p><h1 className="mt-1 text-2xl font-bold">真實圖片雙機示範</h1><p className="mt-2 text-slate-600">A 選圖並填寫每張的案例資料；B 驗證、建立對應示範案例並依模型區預設方案自動分析。批次只是傳輸容器，不代表同一位病人；示範資料不會寫入正式病人。</p></div><ErrorNotice message={action.error||sessions.error||batches.error||settings.error}/>
    <section className="space-y-5 rounded-2xl border bg-white p-6">
      <div className="grid gap-5 lg:grid-cols-2">
        <div><h2 className="mb-2 font-bold">1 B 的接收位址（本機網卡）</h2>
          <div className="mb-2 flex gap-4 text-sm"><label className="flex items-center gap-2"><input type="radio" checked={addressMode==='auto'} onChange={()=>setAddressMode('auto')}/>自動偵測</label><label className="flex items-center gap-2"><input type="radio" checked={addressMode==='manual'} onChange={()=>setAddressMode('manual')}/>手動輸入</label></div>
          {addressMode==='auto'?<div role="radiogroup" aria-label="偵測到的本機位址" className="max-h-56 space-y-1 overflow-auto">{settings.data?.interfaces.map(i=><label key={i.interface+i.address} className={`flex items-start gap-2 rounded-lg p-2 text-sm ${i.supported&&i.is_up!==false?'hover:bg-slate-50':'opacity-60'}`}><input type="radio" name="iface" disabled={!i.supported||i.is_up===false} checked={host===i.address} onChange={()=>setHost(i.address)}/><span><span className="font-mono">{i.address}</span> · {i.interface} · {i.is_up===false?'未連線':i.is_up?'已連線':'狀態未知'} · {kindLabel[i.kind]}<span className="block text-xs text-slate-600">{i.note}</span></span></label>)}
            {settings.data&&!settings.data.recommended&&!host&&<p className="text-sm text-amber-800">偵測到多個或沒有可用的區域網路位址，請選擇與 A 位於同一網路的網卡。</p>}</div>
          :<label className="block text-sm">B 的 IPv4 位址<input className="field" value={manual} onChange={e=>setManual(e.target.value)} placeholder="例如 192.168.1.20" inputMode="decimal"/><span className="text-xs text-slate-600">必須是 B 這台電腦網卡上的位址；不是 A 或超音波設備的位址。後端會核對。</span></label>}
          {effectiveHost==='127.0.0.1'&&<p className="mt-2 text-sm text-amber-800">127.0.0.1 僅供同機測試；雙機請選擇區域網路位址。</p>}
          {settings.data?.saved&&settings.data.saved_check&&!settings.data.saved_check.valid&&<p className="mt-2 text-sm text-amber-800">上次使用的位址 {settings.data.saved.host} 目前無法使用：{settings.data.saved_check.message}</p>}
          <details className="mt-2 text-sm"><summary className="cursor-pointer">進階：連接埠</summary><label className="mt-2 block">連接埠（留空＝自動配置）<input className="field" value={port} onChange={e=>setPort(e.target.value.replace(/\D/g,''))} placeholder="1024–65535" inputMode="numeric"/></label><p className="text-xs text-slate-600">指定時需確認未被占用，並於 B 的防火牆允許。此接收程序只提供圖片傳輸，不開放病人、研究或模型管理介面。</p></details>
        </div>
        <div><h2 className="mb-2 font-bold">2 分析方案</h2><SourcePlanStatus status={status} choice={choice.mode==='default'?undefined:choice}/>
          <details className="mt-3"><summary className="cursor-pointer text-sm">進階：本次改用其他模式</summary><div className="mt-2"><AnalysisChoiceField plans={plans.data||[]} value={choice} onChange={setChoice}/></div></details>
          <p className="mt-2 text-xs text-slate-500">協定邊界：此功能為 A 電腦 HTTPS 原始圖片傳輸。不代表已支援 DICOM、RTSP、廠商 SDK 或任意網路設備；超音波設備請用「設備接收」頁的 USB／UVC 擷取。</p>
        </div>
      </div>
      <button className="btn-primary" disabled={!effectiveHost||action.busy||!!blocked} onClick={start}>開始接收</button>
      {blocked&&<p role="alert" className="text-sm text-red-800">預設方案目前無法使用，未開始接收。</p>}
      <label className="block text-sm font-semibold">既有會話<select className="field mt-2" value={session} onChange={e=>{setSession(e.target.value);setPair(undefined);setSelected('')}}><option value="">選擇會話</option>{sessions.data?.map(s=><option key={s.id} value={s.id}>{s.id.slice(0,12)} · {stateLabel[s.state]} · {s.plan_mode==='preview_only'?'僅預覽':s.plan_name||'舊版會話'} · {new Date(s.created*1000).toLocaleString()}</option>)}</select></label>
      {current&&<p className="text-sm">此會話鎖定：{current.plan_mode==='preview_only'?'僅接收及預覽':current.plan_name?`${current.plan_name}（封存於 ${new Date(current.plan_created*1000).toLocaleString()}）`:'舊版會話（建立時的方案設定）'}{current.host?` · 位址 ${current.host}`:''}。模型區之後變更預設不影響此會話。</p>}
      {session&&<div className="flex flex-wrap gap-3"><button className="btn-secondary" disabled={action.busy} onClick={()=>action.run(async()=>setPair(await clinical('/clinical/demo-sessions/'+session+'/pair',{})))}>重新產生配對資料</button><button className="btn-secondary" disabled={action.busy||!effectiveHost} onClick={()=>action.run(async()=>{setPair(await clinical('/clinical/demo-sessions',{host:effectiveHost,port:port?Number(port):null,address_mode:addressMode,session_id:session}));sessions.refresh()})}>以目前位址恢復中斷會話</button><button className="btn-secondary" disabled={action.busy} onClick={()=>action.run(async()=>{await clinical('/clinical/demo-sessions/'+session+'/stop',{});setPair(undefined);sessions.refresh();batches.refresh()})}>結束會話並清理未保存影像</button></div>}
      {pair&&<div className="rounded-xl bg-teal-50 p-5"><p className="font-semibold">配對資料有效至 {new Date(pair.expires*1000).toLocaleTimeString()}，僅限一個發送端 · 接收位址 {pair.url}</p><p className="my-2 break-all font-mono text-sm">接收端指紋：{pair.fingerprint}</p><p className="text-sm">在 A 匯入配對檔，核對此指紋後配對。B 變更位址或重新開始接收時，憑證會更新，A 需匯入新的配對檔。{pair.requirements?.length?`本方案需要 A 填寫：${pair.requirements.map((r:string)=>requirementLabel[r]||r).join('、')}。`:''}</p><button className="btn-primary mt-3" onClick={exportPair}>下載配對檔</button></div>}
    </section>
    <div className="flex flex-wrap gap-3">{batches.data?.map(b=><a key={b.id} className="btn-secondary" href={'/api/clinical/demo-batches/'+b.id+'/summary'}>下載批次 {b.id.slice(0,8)} 完成摘要</a>)}</div>
    <div className="grid grid-cols-2 gap-4 md:grid-cols-5">{[['pending','待接收',['pending','receiving']],['needs_data','待補資料',['needs_data']],['analyzing','分析中／等待',['queued','verified','waiting','analyzing']],['completed','完成／僅預覽',['completed','received_only']],['failed','失敗／無法分析',['failed','unavailable']]].map(([key,label,states])=><div key={key as string} className="rounded-xl border bg-white p-4"><p className="text-sm text-slate-600">{label}</p><p className="mt-2 text-3xl font-bold">{items.filter(i=>(states as string[]).includes(i.status)).length}</p></div>)}</div>
    {items.some(i=>i.status==='needs_data')&&<p role="status" className="rounded-lg bg-amber-50 p-3 text-amber-900">有 {items.filter(i=>i.status==='needs_data').length} 張影像待補資料：不占用分析佇列，但仍計入 2 GB 暫存上限。補齊後會自動分析一次；結束會話時未保存的影像會被清理。</p>}
    <div className="grid gap-5 lg:grid-cols-[300px_1fr]"><aside className="max-h-[650px] overflow-auto rounded-xl border bg-white p-3">{!items.length&&<p className="p-4 text-slate-600">等待 A 傳送確認清單。</p>}{items.map(i=><button key={i.batch_id+i.id} onClick={()=>setSelected(i.id)} className={`my-1 w-full rounded-lg p-3 text-left ${i.id===selected?'bg-teal-50':'hover:bg-slate-50'}`}><span className="block font-semibold">{i.case_code||i.id.slice(0,12)}</span><span className="text-sm">{stateLabel[i.status]||i.status}</span>{i.missing_fields?.length>0&&<span className="block text-xs text-amber-800">缺：{i.missing_fields.map((m:string)=>requirementLabel[m]||m).join('、')}</span>}{i.error&&<span className="block text-xs text-amber-800">{i.error}</span>}</button>)}</aside><section>{frame?<><FrameResult key={frame.id} frame={frame} onSave={batches.refresh}/>{frame.status==='needs_data'&&<Link className="btn-primary mt-3 inline-block" to={`/clinical/exams?exam=${frame.exam_id}&frame=${frame.id}`}>補充資料</Link>}</>:<div className="rounded-xl border border-dashed p-12 text-center text-slate-600">選擇已接收的圖片，檢視原圖、案例與配對分析結果。</div>}</section></div>
  </>
}
