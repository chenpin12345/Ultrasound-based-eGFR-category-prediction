import { afterEach, expect, it, vi } from 'vitest'
import { initializeLocalSession, localFetch, setSessionUser } from './session'

const principal={id:'system',kind:'local_system',display_name:'本機操作',capabilities:['research.read'],csrf:'new-token',session_id:'s',expires_at:1234}
afterEach(()=>{vi.unstubAllGlobals();setSessionUser(null)})
it('initializes once, without account credentials',async()=>{
  const fetcher=vi.fn().mockResolvedValueOnce(new Response('{}',{status:401})).mockResolvedValueOnce(Response.json({challenge:'nonce'})).mockResolvedValueOnce(Response.json(principal))
  vi.stubGlobal('fetch',fetcher)
  const values=await Promise.all([initializeLocalSession(),initializeLocalSession()])
  expect(values[0]).toEqual(principal)
  expect(fetcher).toHaveBeenCalledTimes(3)
  expect(fetcher.mock.calls[2][1].body).toBe('{"challenge":"nonce"}')
})
it('never resubmits a failed mutation after session renewal',async()=>{
  const fetcher=vi.fn().mockResolvedValueOnce(new Response('{}',{status:401})).mockResolvedValueOnce(Response.json(principal))
  vi.stubGlobal('fetch',fetcher)
  expect((await localFetch('/api/clinical/reports',{method:'POST',body:'{}'})).status).toBe(401)
  expect(fetcher).toHaveBeenCalledTimes(2)
  expect(fetcher.mock.calls.filter(call=>call[0]==='/api/clinical/reports')).toHaveLength(1)
})
it('retries a safe read only once with the renewed token',async()=>{
  const fetcher=vi.fn().mockResolvedValueOnce(new Response('{}',{status:401})).mockResolvedValueOnce(Response.json(principal)).mockResolvedValueOnce(Response.json({items:[]}))
  vi.stubGlobal('fetch',fetcher)
  expect((await localFetch('/api/models')).status).toBe(200)
  expect(fetcher).toHaveBeenCalledTimes(3)
  expect(fetcher.mock.calls[2][1].headers.get('X-CSRF-Token')).toBe('new-token')
})
