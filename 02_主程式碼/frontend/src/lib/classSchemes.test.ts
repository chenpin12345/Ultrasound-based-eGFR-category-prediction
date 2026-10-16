import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => vi.unstubAllGlobals())

it.each([
  ['eGFR < 60', 'eGFR ≥ 60'],
  ['eGFR < 30', 'eGFR 30–59', 'eGFR ≥ 60'],
  ['eGFR < 15', 'eGFR 15–29', 'eGFR 30–59', 'eGFR 60–89', 'eGFR ≥ 90'],
])('keeps model-specific ordered probability labels: %s', async (...labels: string[]) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: {
    class_names: labels, class_count: labels.length,
    items: [{ file: 'test.png', predicted_index: 0, probabilities: labels.map(() => 1 / labels.length) }],
  } }), { headers: { 'content-type': 'application/json' } })))
  const result = await api.getJobResults('job-1')
  const probabilities = result.items?.[0].probabilities
  expect(Array.isArray(probabilities) ? probabilities.map(p => p.class_name) : []).toEqual(labels)
  expect(result.items?.[0].predicted_class).toBe(labels[0])
})
