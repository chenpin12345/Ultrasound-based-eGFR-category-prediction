import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ClinicalRecordPicker } from './RecordPicker'
import { clinical } from './client'

vi.mock('./client',()=>({clinical:vi.fn(),stateLabel:{}}))
afterEach(()=>{cleanup();vi.resetAllMocks()})
it('resolves a selected patient beyond 500 and resets searchable paging',async()=>{
  vi.mocked(clinical).mockImplementation(async(path)=>{
    const params=new URL(path,'http://localhost').searchParams
    if(params.has('exact_id'))return {items:[{id:'p-536',code:'P536',name:'Fixture 536'}],total:1}
    return {items:[{id:`p-${params.get('offset')}`,name:`Page ${params.get('offset')}`}],total:537}
  })
  render(<ClinicalRecordPicker section="patients" label="病人" value="p-536" onChange={()=>{}}/>)
  await screen.findByRole('option',{name:'P536 · Fixture 536（已選）'})
  expect(screen.getByRole('combobox',{name:'病人'})).toHaveValue('p-536')
  fireEvent.click(screen.getByRole('button',{name:'病人下一頁'}))
  await screen.findByRole('option',{name:'Page 50'})
  fireEvent.change(screen.getByRole('textbox',{name:'病人搜尋'}),{target:{value:'fixture'}})
  await waitFor(()=>expect(vi.mocked(clinical).mock.calls.some(([path])=>path.includes('search=fixture')&&path.includes('offset=0'))).toBe(true))
  expect(screen.getByRole('combobox',{name:'病人'})).toHaveValue('p-536')
})
