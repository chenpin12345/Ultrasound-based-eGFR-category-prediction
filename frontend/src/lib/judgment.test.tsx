import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'
import { validBasic } from '../pages/JudgmentPage'

afterEach(() => vi.unstubAllGlobals())

it('requires explicit finite age and diabetes without guessing', () => {
  for (const age of ['', '-1', 'NaN', 'Infinity']) expect(validBasic({age, has_diabetes:'0'})).toBe(false)
  expect(validBasic({age:'52',has_diabetes:''})).toBe(false)
  expect(validBasic({age:'52',has_diabetes:'1'})).toBe(true)
})

it('normalizes nested binary judgment results and retains managed preview metadata', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({job_id:'job', results:{analysis_mode:'image_only', inference:{class_count:2,class_names:['<60','≥60'],items:[{file:'scan.png',predicted_index:1,confidence:.8, probabilities:[.2,.8],processed_url:'/api/jobs/job/files/image.png'}],summary:{counts:{'<60':0,'≥60':1}}}}}),{headers:{'content-type':'application/json'}})))
  const result = await api.getJobResults('job')
  expect(result.items?.[0].predicted_class).toBe('≥60')
  expect(result.items?.[0].probabilities).toHaveLength(2)
  expect(result.items?.[0].processed_url).toContain('/files/image.png')
  expect(result.analysis_mode).toBe('image_only')
  expect(result.statistics).toEqual({'<60':0,'≥60':1})
})
