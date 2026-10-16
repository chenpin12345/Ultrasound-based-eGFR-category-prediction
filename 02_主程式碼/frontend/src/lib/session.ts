export interface LocalPrincipal {
  id: string
  kind: 'local_system'
  display_name: string
  capabilities: string[]
  csrf: string
  session_id: string
  expires_at: number
}
let principal: LocalPrincipal | null = null
let initialization: Promise<LocalPrincipal> | undefined
export const sessionUser = () => principal
export function setSessionUser(value: LocalPrincipal | null) { principal = value }
export const csrfHeader = (): Record<string,string> => principal ? {'X-CSRF-Token': principal.csrf} : {}

export async function initializeLocalSession(): Promise<LocalPrincipal> {
  if (initialization) return initialization
  const initialize = async () => {
    const signal=AbortSignal.timeout(15_000)
    let response = await fetch('/api/local-session', {cache: 'no-store',signal})
    if (response.status === 401) {
      const challenge = await fetch('/api/local-session/challenge', {headers: {'X-Local-Init':'1'}, cache:'no-store',signal})
      if (!challenge.ok) throw new Error('無法初始化本機會話，請確認網站由本機網址開啟。')
      const value = await challenge.json() as {challenge:string}
      response = await fetch('/api/local-session', {method:'POST', headers:{'X-Local-Init':'1','Content-Type':'application/json'}, body:JSON.stringify(value),signal})
    }
    if (!response.ok) throw new Error('本機會話建立失敗，請重試；不會自動重送操作。')
    const value = await response.json() as LocalPrincipal
    if (value.kind !== 'local_system' || !value.session_id || !value.csrf || !Array.isArray(value.capabilities)) throw new Error('本機會話回應格式不正確。')
    principal = value
    window.dispatchEvent(new Event('local-session-ready'))
    return value
  }
  initialization = (navigator.locks ? navigator.locks.request('isu-local-session-init', initialize) : initialize())
  try { return await initialization } finally { initialization = undefined }
}

/** Only a read may be replayed. A failed mutation is returned for explicit user confirmation. */
export async function localFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  for (const [key,value] of Object.entries(csrfHeader())) headers.set(key,value)
  const response = await fetch(input, {...init, headers})
  if (response.status !== 401) return response
  try { await initializeLocalSession() }
  catch { window.dispatchEvent(new Event('local-session-expired')); return response }
  if (!init.method || ['GET','HEAD'].includes(init.method.toUpperCase())) {
    if (init.signal?.aborted) return response
    const nextHeaders = new Headers(init.headers)
    for (const [key,value] of Object.entries(csrfHeader())) nextHeaders.set(key,value)
    return fetch(input, {...init, headers:nextHeaders})
  }
  return response
}
