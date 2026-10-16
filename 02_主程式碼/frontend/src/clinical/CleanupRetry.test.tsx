import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {CleanupRetry} from './CleanupRetry'
import {clinical} from './client'
vi.mock('./client',()=>({clinical:vi.fn()}))
beforeEach(()=>{
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')}
  HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
})
afterEach(()=>{cleanup();vi.resetAllMocks()})
it('requires reason and confirmation before retrying temporary deletion',async()=>{
  vi.mocked(clinical).mockResolvedValue({status:'completed'})
  const done=vi.fn();render(<CleanupRetry id="job-1" onChanged={done}/>)
  fireEvent.click(screen.getByRole('button',{name:'重試暫存清理'}))
  expect(clinical).not.toHaveBeenCalled()
  expect(screen.getByRole('button',{name:'確認重試清理'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('重試理由（必填）'),{target:{value:'已解除占用'}})
  fireEvent.click(screen.getByRole('button',{name:'確認重試清理'}))
  await waitFor(()=>expect(done).toHaveBeenCalledOnce())
  expect(clinical).toHaveBeenCalledWith('/clinical/monitor/cleanup/job-1/retry',{reason:'已解除占用'})
})
it('retains the reason and shows failure without automatic resubmission',async()=>{
  vi.mocked(clinical).mockRejectedValue(new Error('檔案仍被占用'))
  const done=vi.fn();render(<CleanupRetry id="job-2" onChanged={done}/>)
  fireEvent.click(screen.getByRole('button',{name:'重試暫存清理'}))
  fireEvent.change(screen.getByLabelText('重試理由（必填）'),{target:{value:'檢查後重試'}})
  fireEvent.click(screen.getByRole('button',{name:'確認重試清理'}))
  expect(await screen.findByText(/檔案仍被占用/)).toBeInTheDocument()
  expect(screen.getByLabelText('重試理由（必填）')).toHaveValue('檢查後重試')
  expect(clinical).toHaveBeenCalledOnce();expect(done).not.toHaveBeenCalled()
})
