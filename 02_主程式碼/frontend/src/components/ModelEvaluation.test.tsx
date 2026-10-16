import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ModelEvaluation } from './ModelEvaluation'
import type { ModelEvaluationSummary } from '../types/api'

afterEach(cleanup)
const summary:ModelEvaluationSummary={selection:'latest_created_not_best',evaluation_id:'eval-1',status:'completed',reason:null,weight_sha256:'weight',configuration_sha256:'config',dataset_id:'data',dataset_name:'研究測試資料',split:'test',scope:'不是獨立臨床測試',sample_count:5,evaluated_sample_count:5,completed_at:'2026-10-09',metric_version:'v1',unit:'fraction',metrics:{accuracy:0,macro_f1:null}}
describe('sourced model evaluation summary',()=>{
  it('does not replace missing evaluations with zero',()=>{
    render(<ModelEvaluation/>);expect(screen.getByText(/尚未評估/)).toBeTruthy();expect(screen.queryByText('0.00%')).toBeNull()
  })
  it('keeps valid zero and undefined metrics distinct, with scope and source',()=>{
    render(<MemoryRouter><ModelEvaluation summary={summary} details/></MemoryRouter>)
    expect(screen.getByText('0.00%')).toBeTruthy();expect(screen.getByText('無法定義')).toBeTruthy()
    expect(screen.getByText(/不是最佳模型排名/)).toBeTruthy();expect(screen.getByText(/權重 SHA-256：weight/)).toBeTruthy()
    expect(screen.getByRole('link').getAttribute('href')).toBe('/model-center/evaluations/eval-1')
  })
})
