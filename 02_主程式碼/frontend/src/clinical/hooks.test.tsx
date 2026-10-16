import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { clinical } from './client'
import { useClinical } from './hooks'
import { publishClinicalChange } from './invalidation'

vi.mock('./client',()=>({clinical:vi.fn()}))
afterEach(()=>vi.resetAllMocks())

it('PDF invalidation clears artifact readers without unmounting a report draft',async()=>{
  vi.mocked(clinical).mockResolvedValue({id:'same'})
  const report=renderHook(()=>useClinical('/clinical/reports/report-1'))
  const pdf=renderHook(()=>useClinical('/clinical/reports/report-1/versions/1/pdf-artifacts'))
  await waitFor(()=>expect(report.result.current.data).toBeDefined())
  await waitFor(()=>expect(pdf.result.current.data).toBeDefined())
  vi.mocked(clinical).mockImplementation(()=>new Promise(()=>{}))
  act(()=>publishClinicalChange(true,'pdf'))
  expect(report.result.current.data).toBeDefined()
  expect(pdf.result.current.data).toBeUndefined()
})

it('clears revoked data immediately and ignores stale in-flight responses',async()=>{
  let late:(value:unknown)=>void=()=>{}
  vi.mocked(clinical).mockResolvedValueOnce({id:'first'}).mockImplementationOnce(()=>new Promise(resolve=>{late=resolve})).mockRejectedValue(new Error('已回收'))
  const {result}=renderHook(()=>useClinical<{id:string}>('/first'))
  await waitFor(()=>expect(result.current.data?.id).toBe('first'))
  act(()=>result.current.refresh())
  act(()=>publishClinicalChange(true))
  expect(result.current.data).toBeUndefined()
  await act(async()=>late({id:'stale'}))
  await waitFor(()=>expect(result.current.error).toBe('已回收'))
  expect(result.current.data).toBeUndefined()
})

it('never returns the previous case while another case is loading',async()=>{
  let resolveSecond:(value:unknown)=>void=()=>{}
  vi.mocked(clinical).mockImplementation((path)=>path==='/first'?Promise.resolve({id:'first'}):new Promise(resolve=>{resolveSecond=resolve}))
  const {result,rerender}=renderHook(({path})=>useClinical<{id:string}>(path),{initialProps:{path:'/first'}})
  await waitFor(()=>expect(result.current.data?.id).toBe('first'))
  rerender({path:'/second'})
  expect(result.current.data).toBeUndefined()
  await act(async()=>resolveSecond({id:'second'}))
  expect(result.current.data?.id).toBe('second')
  rerender({path:''})
  expect(result.current.data).toBeUndefined()
})

it('retains same-case data and exposes background update failure',async()=>{
  vi.mocked(clinical).mockResolvedValueOnce({id:'first'}).mockRejectedValueOnce(new Error('offline fixture'))
  const {result}=renderHook(()=>useClinical<{id:string}>('/first'))
  await waitFor(()=>expect(result.current.data?.id).toBe('first'))
  act(()=>result.current.refresh())
  expect(result.current.data?.id).toBe('first')
  await waitFor(()=>expect(result.current.error).toBe('offline fixture'))
  expect(result.current.data?.id).toBe('first')
})
