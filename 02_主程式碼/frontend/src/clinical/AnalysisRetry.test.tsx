import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {AnalysisRetry} from './AnalysisRetry'
import {clinical} from './client'
vi.mock('./client',()=>({clinical:vi.fn()}))
afterEach(()=>{cleanup();vi.resetAllMocks()})

it('prevents duplicate submission and reports only completed analysis as success',async()=>{
  let resolve!:(value:unknown)=>void
  vi.mocked(clinical).mockImplementation(()=>new Promise(done=>{resolve=done}))
  const changed=vi.fn();render(<AnalysisRetry id="original-op" onChanged={changed}/>)
  fireEvent.click(screen.getByRole('button',{name:'使用同一方案重試分析'}))
  expect(screen.getByRole('button',{name:'正在執行新分析…'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'正在執行新分析…'}))
  expect(clinical).toHaveBeenCalledOnce()
  resolve({status:'completed',result:{}})
  await waitFor(()=>expect(changed).toHaveBeenCalledWith(expect.stringContaining('重試分析完成')))
  expect(clinical).toHaveBeenCalledWith('/clinical/monitor/operations/original-op/retry',{})
})

it('announces an unsuccessful new operation without success feedback or automatic retry',async()=>{
  vi.mocked(clinical).mockResolvedValue({status:'failed',result:{message:'模型來源不符'}})
  const changed=vi.fn();render(<AnalysisRetry id="original-op" onChanged={changed}/>)
  fireEvent.click(screen.getByRole('button',{name:'使用同一方案重試分析'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('模型來源不符')
  expect(changed).toHaveBeenCalledWith('')
  expect(clinical).toHaveBeenCalledOnce()
})

it('preserves a transport error without resending an uncertain write',async()=>{
  vi.mocked(clinical).mockRejectedValue(new Error('連線中斷，請查詢作業紀錄'))
  const changed=vi.fn();render(<AnalysisRetry id="original-op" onChanged={changed}/>)
  fireEvent.click(screen.getByRole('button',{name:'使用同一方案重試分析'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('不會自動重試')
  expect(changed).not.toHaveBeenCalled();expect(clinical).toHaveBeenCalledOnce()
})
