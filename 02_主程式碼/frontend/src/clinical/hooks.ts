import { useCallback, useEffect, useState } from 'react'
import { clinical } from './client'
import { subscribeClinicalChanges } from './invalidation'
export function useClinical<T=any>(path:string, poll=0) {
  const [state,setState]=useState<{path:string;data?:T;error:string}>({path:'',error:''}),[version,setVersion]=useState(0)
  const refresh=useCallback(()=>setVersion(v=>v+1),[])
  useEffect(()=>{
    if(!path)return
    let live=true,controller:AbortController|undefined
    let timer:ReturnType<typeof setTimeout>|undefined,deadline:ReturnType<typeof setTimeout>|undefined
    const load=async()=>{
      controller=new AbortController()
      let timedOut=false
      deadline=setTimeout(()=>{timedOut=true;controller?.abort()},15000)
      try{
        const value=await clinical<T>(path,undefined,undefined,controller.signal)
        if(live)setState({path,data:value,error:''})
      }catch(e){
        if(live)setState(previous=>({path,data:previous.path===path?previous.data:undefined,error:timedOut?'讀取超過 15 秒，請重新整理或檢查本機服務。':(e as Error).message}))
      }finally{
        clearTimeout(deadline)
        if(live&&poll)timer=setTimeout(load,poll)
      }
    }
    void load()
    const unsubscribe=subscribeClinicalChanges((clear,scope)=>{
      if(scope==='pdf'&&!/\/pdf(?:-artifacts)?(?:\/|$|\?)/.test(path))return
      live=false;controller?.abort();clearTimeout(timer);clearTimeout(deadline)
      if(clear)setState({path,error:''})
      refresh()
    })
    return()=>{live=false;controller?.abort();clearTimeout(timer);clearTimeout(deadline);unsubscribe()}
  },[path,poll,version,refresh])
  // Synchronous identity check prevents even one render of the previous case.
  return {data:state.path===path?state.data:undefined,error:state.path===path?state.error:'',refresh}
}
export function useAction() {
  const [error,setError]=useState(''),[busy,setBusy]=useState(false)
  async function run(fn:()=>Promise<unknown>){setError('');setBusy(true);try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return {error,busy,run}
}
