import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {PdfPanel} from './PdfPanel'
import {clinical} from './client'
vi.mock('./client',()=>({clinical:vi.fn()}))
const ready={id:'pdf-1',version:1,template_version:2,variant:'original',status:'ready',sha256:'a'.repeat(64),created:1,error:null,url:'/api/clinical/pdf-artifacts/pdf-1'}
beforeEach(()=>{
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')}
  HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
})
afterEach(()=>{cleanup();vi.resetAllMocks()})
it('does not generate a PDF merely by opening the panel',async()=>{
  let items:typeof ready[]=[]
  vi.mocked(clinical).mockImplementation(async(_path,body)=>{if(body){items=[ready];return ready}return{variant:'original',items}})
  render(<PdfPanel reportId="report-1" version={1}/>)
  await waitFor(()=>expect(screen.getByRole('button',{name:'產生 PDF'})).toBeEnabled())
  expect(vi.mocked(clinical).mock.calls.every(([,body])=>body===undefined)).toBe(true)
  expect(screen.queryByTitle('報告 PDF 預覽')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'產生 PDF'}))
  expect(await screen.findByTitle('報告 PDF 預覽')).toHaveAttribute('src',ready.url)
})
it('requires confirmation and reason, then removes preview while keeping history',async()=>{
  let removed=false
  vi.mocked(clinical).mockImplementation(async(_path,body,method)=>{
    if(method==='DELETE'){removed=true;return{status:'deleted'}}
    return{variant:'original',items:[{...ready,status:removed?'deleted':'ready',url:removed?null:ready.url}]}
  })
  render(<PdfPanel reportId="report-1" version={1}/>)
  fireEvent.click(await screen.findByRole('button',{name:'刪除此 PDF 檔案'}))
  expect(screen.getByRole('button',{name:'確認刪除 PDF'})).toBeDisabled()
  fireEvent.change(screen.getByLabelText('PDF 刪除理由（必填）'),{target:{value:'Wrong output fixture'}})
  fireEvent.click(screen.getByRole('button',{name:'確認刪除 PDF'}))
  await waitFor(()=>expect(screen.queryByTitle('報告 PDF 預覽')).not.toBeInTheDocument())
  expect(vi.mocked(clinical).mock.calls.find(([, ,method])=>method==='DELETE')?.[1]).toEqual({expected_sha256:ready.sha256,reason:'Wrong output fixture'})
  expect(screen.getByRole('button',{name:'重新產生 PDF'})).toBeEnabled()
})
