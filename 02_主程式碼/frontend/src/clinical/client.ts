import { csrfHeader, localFetch } from '../lib/session'
import { publishClinicalChange } from './invalidation'
export async function clinical<T=any>(path: string, body?: unknown, method?: string, signal?: AbortSignal): Promise<T> {
  const response = await localFetch('/api'+path, {method: method || (body === undefined ? 'GET' : 'POST'),
    headers: {...csrfHeader(), ...(body instanceof Blob ? {} : {'Content-Type':'application/json'})},
    body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body), signal})
  if (response.status === 401 && !['/auth/login','/auth/bootstrap','/auth/status','/auth/me'].includes(path)) window.dispatchEvent(new Event('local-session-expired'))
  const value = await response.json()
  if (!response.ok) throw new Error(value.error?.message || '操作失敗，請稍後重試。')
  const verb=(method || (body===undefined?'GET':'POST')).toUpperCase()
  if(!['GET','HEAD'].includes(verb)&&/^\/clinical\/(lifecycle|patients|exams|reports|frames|pdf-artifacts|monitor\/(cleanup|operations))(\/|$)/.test(path))publishClinicalChange(path.startsWith('/clinical/lifecycle/')||path.startsWith('/clinical/monitor/cleanup/')||verb==='DELETE',/\/pdf(?:-artifacts)?(?:\/|$|\?)/.test(path)?'pdf':'all')
  return value as T
}
export const diabetesLabel: Record<string,string> = {yes:'有',no:'無',unknown:'未知'}
export const requirementLabel: Record<string,string> = {age:'年齡',has_diabetes:'糖尿病狀態（有／無）'}
export const stateLabel: Record<string,string> = {pending:'待傳送',receiving:'接收中',verified:'已接收驗證',queued:'已接收，等待分析',needs_data:'待補資料',received_only:'已接收（僅預覽）',waiting:'等待運算資源（可繼續）',analyzing:'分析中',completed:'完成',unavailable:'無法分析',failed:'失敗',cancelled:'取消',received:'已接收',draft:'草稿',confirmed:'已確認',void:'已作廢',paused:'暫停',running:'進行中',active:'接收中',interrupted:'已中斷',ended:'已結束'}
