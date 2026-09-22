import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, apiUrl, listItems, requestJson, unwrapPayload } from './api'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('API helpers', () => {
  it('times out reads including a stalled response body, without timing out job submission', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((_url, init) => Promise.resolve({
      ok: true, status: 200, headers: new Headers({'content-type':'application/json'}),
      json: () => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new DOMException('Aborted','AbortError')))),
    })))
    const read = expect(requestJson('/jobs')).rejects.toThrow('15 秒')
    await vi.advanceTimersByTimeAsync(15_001)
    await read
    let submissionSignal!: AbortSignal
    let finish!: (value: Response) => void
    vi.stubGlobal('fetch', vi.fn().mockImplementation((_url, init) => { submissionSignal = init.signal; return new Promise(resolve => { finish = resolve }) }))
    const submit = requestJson('/jobs', {method:'POST', body:'{}'})
    await vi.advanceTimersByTimeAsync(30_000)
    expect(submissionSignal.aborted).toBe(false)
    finish(new Response('{}', {headers:{'content-type':'application/json'}}))
    await submit
  })
  it('unwraps the standard data envelope and accepts direct responses', () => {
    expect(unwrapPayload({ data: { id: 'job-1' }, meta: { request_id: 'r1' } })).toEqual({ id: 'job-1' })
    expect(unwrapPayload({ id: 'job-2' })).toEqual({ id: 'job-2' })
  })

  it('normalizes arrays and paginated collection responses', () => {
    expect(listItems([{ id: 1 }])).toEqual([{ id: 1 }])
    expect(listItems({ items: [{ id: 2 }], total: 1 })).toEqual([{ id: 2 }])
    expect(listItems({ datasets: [{ id: 3 }] })).toEqual([{ id: 3 }])
  })

  it('keeps API URLs local and preserves explicit API paths', () => {
    expect(apiUrl('/health')).toMatch(/\/api\/health$/)
    expect(apiUrl('/api/jobs/1')).toBe('/api/jobs/1')
    expect(api.datasetSummaryDownloadUrl('dataset/1')).toBe('/api/datasets/dataset%2F1/summary?download=1')
  })

  it('renames a model through the PATCH contract and normalizes active state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: 'model/1', name: '新名稱', active: true,
    }), { status: 200, headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.renameModel('model/1', '新名稱')).resolves.toMatchObject({
      name: '新名稱', is_active: true, is_default: true,
    })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/models/model%2F1')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PATCH', body: JSON.stringify({ name: '新名稱' }) })
  })

  it('turns a backend error envelope into a typed Chinese-safe error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'INVALID_UPLOAD', message: '檔案格式不支援', request_id: 'req-1' },
    }), { status: 422, headers: { 'content-type': 'application/json' } })))
    await expect(requestJson('/datasets')).rejects.toMatchObject({
      message: '檔案格式不支援', code: 'INVALID_UPLOAD', status: 422, requestId: 'req-1',
    })
  })
})
