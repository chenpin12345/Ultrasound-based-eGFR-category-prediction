import { afterEach, expect, it, vi } from 'vitest'
import { clearResourceCache, FRESH_MS, invalidateResources, loadResource, resourceSnapshot, subscribeResource } from './resourceCache'
afterEach(() => { clearResourceCache(); vi.useRealTimers() })
it('shares requests and reuses data only while fresh', async () => {
  vi.useFakeTimers(); vi.setSystemTime(1000)
  const loader=vi.fn().mockResolvedValue(['model'])
  await Promise.all([loadResource('models',loader),loadResource('models',loader)])
  await loadResource('models',loader)
  expect(loader).toHaveBeenCalledTimes(1)
  vi.setSystemTime(1000+FRESH_MS+1); await loadResource('models',loader)
  expect(loader).toHaveBeenCalledTimes(2)
  await loadResource('models',loader,true); expect(loader).toHaveBeenCalledTimes(3)
})
it('keeps prior data on background errors and isolates keys', async () => {
  await loadResource('a',async()=>['a']); await loadResource('b',async()=>['b'])
  await loadResource('a',async()=>{throw new Error('offline')},true)
  expect(resourceSnapshot('a').data).toEqual(['a'])
  expect(resourceSnapshot('a').error).toBe('offline')
  expect(resourceSnapshot('b').data).toEqual(['b'])
})
it('discards an invalidated in-flight reply and notifies observers', async () => {
  let finish!: (value: string)=>void
  const unsubscribe=subscribeResource('x',vi.fn())
  const loader=vi.fn().mockImplementationOnce(()=>new Promise<string>(resolve=>{finish=resolve})).mockResolvedValue('new')
  const old=loadResource('x',loader)
  invalidateResources(false)
  await Promise.resolve(); await Promise.resolve()
  finish('old'); await old
  expect(resourceSnapshot('x').data).toBe('new')
  unsubscribe()
})
it('aborts only after the last consumer unmounts', async () => {
  const one=subscribeResource('x',()=>{}), two=subscribeResource('x',()=>{})
  let signal!: AbortSignal
  const pending=loadResource('x',s=>{signal=s; return new Promise(resolve=>s.addEventListener('abort',()=>resolve('late')))})
  one(); expect(signal.aborted).toBe(false)
  two(); expect(signal.aborted).toBe(true)
  await pending; expect(resourceSnapshot('x').data).toBeUndefined()
})
