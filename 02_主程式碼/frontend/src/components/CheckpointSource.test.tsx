import {cleanup,render,screen} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import {CheckpointSource} from './CheckpointSource'
afterEach(cleanup)
it('separates best, last and fold records without claiming an evaluation',()=>{
  render(<CheckpointSource source={{status:'verified_record',reason:'不是獨立評估',sample_count:12,split_counts:{train:8,val:4},selection:{metric:'validation_loss',direction:'minimize',best_epoch:1,value:.2,selected_fold:0},best_epoch_record:{epoch:1,metrics:{val_accuracy:.7}},last_epoch_record:{epoch:4,metrics:{val_accuracy:.9}},cross_validation:{aggregate:{mean:.8}}}}/>)
  expect(screen.getByText('選中的最佳 checkpoint')).toBeInTheDocument()
  expect(screen.getByText('Epoch 4')).toBeInTheDocument()
  expect(screen.getByText('此處不是最佳權重成績。')).toBeInTheDocument()
  expect(screen.getByText(/各 fold 與歷史聚合/)).toBeInTheDocument()
})
it('does not fill missing historical checkpoint metrics with zero',()=>{
  render(<CheckpointSource source={{status:'unverified',reason:'歷史來源不完整'}}/>)
  expect(screen.getByText('Checkpoint 來源尚未核實')).toBeInTheDocument()
  expect(screen.queryByText('選中的最佳 checkpoint')).not.toBeInTheDocument()
})
