/**
 * 後端 API 呼叫。不登入：第一次呼叫時自動建立本機工作階段並取得 CSRF token。
 * 寫入請求會帶上 CSRF token 與目前選擇的操作者（X-Operator）。
 */

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

let csrf: string | null = null
let sessionPromise: Promise<void> | null = null
let operatorName = ''

export const setOperatorHeader = (name: string) => {
  operatorName = name
}

async function initSession(): Promise<void> {
  const challenge = await fetch('/api/session/challenge', { headers: { 'X-Local-Init': '1' }, credentials: 'same-origin' })
  if (!challenge.ok) throw await toError(challenge)
  const { challenge: token } = await challenge.json()
  const res = await fetch('/api/session', {
    method: 'POST',
    headers: { 'X-Local-Init': '1', 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ challenge: token }),
  })
  if (!res.ok) throw await toError(res)
  csrf = (await res.json()).csrf
}

function ensureSession(): Promise<void> {
  if (csrf) return Promise.resolve()
  if (!sessionPromise) {
    sessionPromise = initSession().finally(() => {
      sessionPromise = null
    })
  }
  return sessionPromise
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json()
    const e = body?.error
    return new ApiError(res.status, e?.code ?? 'HTTP_ERROR', e?.message ?? `要求失敗（${res.status}）`, e?.details)
  } catch {
    return new ApiError(res.status, 'HTTP_ERROR', res.status === 0 ? '無法連線到後端，請確認已用 start.bat 啟動。' : `要求失敗（${res.status}）`)
  }
}

async function request<T>(method: string, url: string, body?: unknown, retried = false): Promise<T> {
  await ensureSession()
  const headers: Record<string, string> = {}
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET') {
    headers['X-CSRF-Token'] = csrf ?? ''
    if (operatorName) headers['X-Operator'] = encodeURIComponent(operatorName)
  }
  let res: Response
  try {
    res = await fetch(`/api${url}`, { method, headers, body: payload, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'NETWORK', '無法連線到後端，請確認已用 start.bat 啟動。')
  }
  if ((res.status === 401 || (res.status === 403 && method !== 'GET')) && !retried) {
    const err = await toError(res)
    if (err.code === 'SESSION_REQUIRED' || err.code === 'CSRF_REQUIRED') {
      csrf = null
      return request<T>(method, url, body, true)
    }
    throw err
  }
  if (!res.ok) throw await toError(res)
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? res.json() : res.blob()) as Promise<T>
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  put: <T>(url: string, body?: unknown) => request<T>('PUT', url, body ?? {}),
  patch: <T>(url: string, body?: unknown) => request<T>('PATCH', url, body ?? {}),
  upload: <T>(url: string, form: FormData) => request<T>('POST', url, form),
}

/** 影像檔的網址（同源，瀏覽器會自動帶工作階段 Cookie）。 */
export const imageUrl = (id: string, kind: 'model' | 'calc' | 'thumb' = 'model') => `/api/images/${id}/file?kind=${kind}`

/** 先確保工作階段存在（影像 <img> 直接讀網址，需要 Cookie 已建立）。 */
export const ready = () => ensureSession()
