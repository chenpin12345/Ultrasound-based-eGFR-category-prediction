import { act, renderHook, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { useWorkflowJob, workflowLink } from './workflow'

afterEach(() => vi.unstubAllGlobals())
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

it('encodes source IDs in workflow navigation without initiating work', () => {
  expect(workflowLink('/features', 'data 1', 'job 1')).toBe('/features?dataset_id=data+1&source_job=job+1')
})

it('hands selected sources and unchanged operation parameters to the API', async () => {
  const fetch = vi.fn().mockImplementation((url: string) => Promise.resolve(url.includes('/workflow/source')
    ? response({ name: 'Source', image_count: 3, mask_count: 0, metadata_count: 3, has_features: false })
    : response({ id: 'created', kind: 'process', status: 'queued' })))
  vi.stubGlobal('fetch', fetch)
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={['/processing?dataset_id=data-1']}>{children}</MemoryRouter>
  const { result } = renderHook(() => useWorkflowJob('process'), { wrapper })
  await waitFor(() => expect(result.current.ready).toBe(true))
  expect(fetch.mock.calls.every(call => !call[1]?.method || call[1].method === 'GET')).toBe(true)
  const form = new FormData(); form.append('config', JSON.stringify({ steps: ['crop', 'rb'], preserve_originals: true })); form.append('name', 'Test')
  await act(async () => { await result.current.create(form) })
  const call = fetch.mock.calls.find(call => call[1]?.method === 'POST')!
  expect(JSON.parse(call[1].body)).toEqual({ kind: 'process', name: 'Test', input_sources: { images: { kind: 'dataset', id: 'data-1' } }, config: { steps: ['crop', 'rb'], preserve_originals: true } })
})

it('does not fallback to uploads for a missing selected source', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ error: { message: '來源已刪除' } }, 404)))
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={['/features?source_job=deleted']}>{children}</MemoryRouter>
  const { result } = renderHook(() => useWorkflowJob('features'), { wrapper })
  await waitFor(() => expect(result.current.sourceError).toBe('來源已刪除'))
  expect(result.current.ready).toBe(false)
  await expect(result.current.create(new FormData())).rejects.toThrow('有效的工作來源')
})
