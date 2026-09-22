import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useAsyncResource } from './useAsyncResource'
import { clearResourceCache, invalidateResources } from '../lib/resourceCache'
afterEach(() => { cleanup(); clearResourceCache() })
it('shares cached data across remounts and keeps it visible during refresh', async () => {
  let finish!: (value: string[]) => void
  const loader = vi.fn().mockResolvedValueOnce(['first']).mockImplementation(() => new Promise(resolve => { finish=resolve }))
  const one=renderHook(() => useAsyncResource(loader,true,'shared'))
  await waitFor(() => expect(one.result.current.data).toEqual(['first']))
  one.unmount()
  const two=renderHook(() => useAsyncResource(loader,true,'shared'))
  expect(two.result.current.loading).toBe(false)
  expect(two.result.current.data).toEqual(['first'])
  expect(loader).toHaveBeenCalledTimes(1)
  act(() => { invalidateResources(false) })
  expect(two.result.current.updating).toBe(true)
  expect(two.result.current.loading).toBe(false)
  expect(two.result.current.data).toEqual(['first'])
  await act(async () => finish(['updated']))
  expect(two.result.current.data).toEqual(['updated'])
})
it('never shows the previous dataset while a new key is loading', async () => {
  const loader=vi.fn().mockResolvedValueOnce(['dataset-a']).mockImplementation(() => new Promise(()=>{}))
  const hook=renderHook(({key}) => useAsyncResource(loader,true,key),{initialProps:{key:'dataset-a'}})
  await waitFor(() => expect(hook.result.current.data).toEqual(['dataset-a']))
  hook.rerender({key:'dataset-b'})
  expect(hook.result.current.data).toBeUndefined()
  expect(hook.result.current.loading).toBe(true)
})
