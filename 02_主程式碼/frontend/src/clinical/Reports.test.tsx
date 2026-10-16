import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {transferableAbortController} from 'node:util'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {createMemoryRouter,Link,RouterProvider} from 'react-router-dom'
import {ReportsPage} from './Reports'
import {clinical} from './client'
import {publishClinicalChange} from './invalidation'

vi.mock('./client',()=>({clinical:vi.fn(),stateLabel:{draft:'草稿'}}))
vi.mock('./RecordPicker',()=>({ClinicalRecordPicker:()=>null}))
let current=1
beforeEach(()=>{
  // jsdom's signal and Node's native Request belong to different realms.
  // Use Node's real controller for the memory router (no network loaders).
  vi.stubGlobal('AbortController',class {constructor(){return transferableAbortController()}})
  current=1
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')}
  HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
  vi.mocked(clinical).mockImplementation(async(path,body)=>{
    if(path.endsWith('/pdf-artifacts'))return{variant:'original',items:[]}
    if(body)return{id:'report-1',version:++current}
    if(path==='/clinical/reports/report-1')return{id:'report-1',exam_id:'exam-1',state:'draft',current_version:current,versions:[{version:current,state:'draft',payload:{fields:{findings:'saved '+current},images:[],include_ai:false}}]}
    if(path==='/clinical/exams/exam-1')return{id:'exam-1',title:'測試檢查',kind:'demo',frames:[]}
    throw new Error('Unexpected request '+path)
  })
})
afterEach(()=>{cleanup();vi.resetAllMocks();vi.unstubAllGlobals()})
async function setup(url='/clinical/reports?report=report-1') {
  const router=createMemoryRouter([{path:'/clinical/reports',element:<><Link to="/away">離開報告</Link><ReportsPage/></>},{path:'/away',element:<h1>其他工作區</h1>}],{initialEntries:[url]})
  render(<RouterProvider router={router}/>)
  await waitFor(()=>expect(screen.getByLabelText('檢查所見')).not.toBeDisabled())
  fireEvent.change(screen.getByLabelText('檢查所見'),{target:{value:'尚未保存文字'}})
  return router
}
it('blocks navigation, supports staying and discarding without a write',async()=>{
  await setup()
  fireEvent.click(screen.getByText('離開報告'))
  expect(await screen.findByRole('dialog')).toHaveTextContent('報告尚未保存')
  fireEvent.click(screen.getByText('留在此頁'))
  expect(screen.getByLabelText('檢查所見')).toHaveValue('尚未保存文字')
  fireEvent.click(screen.getByText('離開報告'))
  fireEvent.click(screen.getByText('放棄變更並離開'))
  expect(await screen.findByRole('heading',{name:'其他工作區'})).toBeInTheDocument()
  expect(vi.mocked(clinical).mock.calls.filter(([,body])=>body)).toHaveLength(0)
})
it('saves one draft before proceeding to the original destination',async()=>{
  await setup()
  fireEvent.click(screen.getByText('離開報告'))
  fireEvent.click(screen.getByText('保存草稿並離開'))
  expect(await screen.findByRole('heading',{name:'其他工作區'})).toBeInTheDocument()
  const writes=vi.mocked(clinical).mock.calls.filter(([,body])=>body)
  expect(writes).toHaveLength(1)
  expect(writes[0][1]).toMatchObject({action:'draft',expected_version:1,fields:{findings:'尚未保存文字'}})
})
it('retains dirty text on background changes and refuses to overwrite a newer version',async()=>{
  await setup()
  current=2
  act(()=>publishClinicalChange())
  expect(await screen.findByText(/另一個操作已建立新報告版本/)).toBeInTheDocument()
  expect(screen.getByLabelText('檢查所見')).toHaveValue('尚未保存文字')
  expect(screen.getByText('保存草稿版本')).toBeDisabled()
  fireEvent.click(screen.getByText('離開報告'))
  expect(screen.getByText('保存草稿並離開')).toBeDisabled()
})
it('keeps the user on the report after a failed save and guards browser closing',async()=>{
  await setup('/clinical/reports?exam=exam-1')
  const event=new Event('beforeunload',{cancelable:true})
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  vi.mocked(clinical).mockRejectedValue(new Error('儲存測試失敗'))
  fireEvent.click(screen.getByText('離開報告'))
  fireEvent.click(screen.getByText('保存草稿並離開'))
  expect(await screen.findByText('儲存測試失敗')).toBeInTheDocument()
  expect(screen.getByLabelText('檢查所見')).toHaveValue('尚未保存文字')
})
