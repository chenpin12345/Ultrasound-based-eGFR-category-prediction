import { useCallback, useEffect } from 'react'
import { api } from '../lib/api'
import { useAsyncResource } from './useAsyncResource'

// Selected IDs are resolved independently of the currently visible list page.
// Initial defaults are explicitly queried, never replaced by the first page's first item.
export function useModelChoice(id:string, setId:(id:string)=>void, task:'classification'|'segmentation', classCount?:number, defaultName?:string, analysisMode?:'mlp'|'image_only') {
  const query=new URLSearchParams({task,limit:'1',status:'ready'})
  if(classCount)query.set('class_count',String(classCount))
  if(analysisMode)query.set('analysis_mode',analysisMode)
  if(defaultName)query.set('exact_name',defaultName)
  else query.set('active','true')
  const key=query.toString()
  const loadDefault=useCallback((signal?:AbortSignal)=>api.modelPage(new URLSearchParams(key),signal),[key])
  const preferred=useAsyncResource(loadDefault,!id,`model-default:${key}`)
  useEffect(()=>{if(!id&&preferred.data?.items[0])setId(preferred.data.items[0].id)},[id,preferred.data,setId])
  const loadSelected=useCallback((signal?:AbortSignal)=>api.getModel(id,signal),[id])
  const resource=useAsyncResource(loadSelected,Boolean(id),`model-detail:${id}`)
  const raw=resource.data
  const selected=raw?.task===task&&(!classCount||raw.class_count===classCount)&&(!analysisMode||raw.architecture?.includes('mlp')===(analysisMode==='mlp'))&&['ready','completed'].includes(raw.status||'')?raw:undefined
  return {...resource, selected, loading:resource.loading||preferred.loading, error:resource.error||preferred.error}
}
