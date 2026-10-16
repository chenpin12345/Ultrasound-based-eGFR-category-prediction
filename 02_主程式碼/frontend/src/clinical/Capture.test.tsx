import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {MemoryRouter} from 'react-router-dom'
import {CapturePage} from './Capture'
import {clinical} from './client'

vi.mock('./client',()=>({clinical:vi.fn()}))
vi.mock('./RecordPicker',()=>({ClinicalRecordPicker:()=>null}))
vi.mock('./hooks',async importOriginal=>({
  ...await importOriginal<typeof import('./hooks')>(),
  useClinical:()=>({data:[{id:'fixture-plan',name:'隔離測試方案',profile:{mode:'prepared'}}],error:'',refresh:vi.fn()}),
}))
let stop:ReturnType<typeof vi.fn>,getUserMedia:ReturnType<typeof vi.fn>,media:MediaStream
beforeEach(()=>{
  stop=vi.fn()
  const track={stop,onended:null}
  media={getTracks:()=>[track],getVideoTracks:()=>[track]} as unknown as MediaStream
  getUserMedia=vi.fn().mockResolvedValue(media)
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia,enumerateDevices:vi.fn().mockResolvedValue([])}})
  vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue()
  vi.spyOn(HTMLVideoElement.prototype,'videoWidth','get').mockReturnValue(32)
  vi.spyOn(HTMLVideoElement.prototype,'videoHeight','get').mockReturnValue(24)
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({drawImage:vi.fn()} as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype,'toBlob').mockImplementation(callback=>callback(new Blob(['synthetic fixture'],{type:'image/png'})))
})
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.resetAllMocks()})
const open=()=>render(<MemoryRouter initialEntries={['/clinical/capture?exam=fixture-exam']}><CapturePage/></MemoryRouter>)

it('stops every media track when leaving the capture page',async()=>{
  const view=open();fireEvent.click(screen.getByRole('button',{name:'連接擷取設備'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'停止'})).toBeEnabled())
  view.unmount();expect(stop).toHaveBeenCalledOnce()
})

it('stops a late camera permission result after the page has been left',async()=>{
  let resolve!:(stream:MediaStream)=>void
  getUserMedia.mockImplementation(()=>new Promise<MediaStream>(done=>{resolve=done}))
  const view=open();fireEvent.click(screen.getByRole('button',{name:'連接擷取設備'}))
  view.unmount();await act(async()=>resolve(media))
  expect(stop).toHaveBeenCalledOnce()
})

it('aborts sampling and releases only its operation when leaving during AI analysis',async()=>{
  let finish!:(value:unknown)=>void
  vi.mocked(clinical).mockImplementation(path=>path.includes('/release?')?Promise.resolve({}):new Promise(done=>{finish=done}))
  const view=open();fireEvent.click(screen.getByRole('button',{name:'連接擷取設備'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'停止'})).toBeEnabled())
  fireEvent.change(screen.getByLabelText('分析方案'),{target:{value:'fixture-plan'}})
  fireEvent.click(screen.getByLabelText('AI 分析'))
  await waitFor(()=>expect(clinical).toHaveBeenCalledOnce())
  const call=vi.mocked(clinical).mock.calls[0]
  const operation=new URL(call[0],'http://localhost').searchParams.get('operation_id')
  expect(call[3]?.aborted).toBe(false)
  view.unmount()
  expect(call[3]?.aborted).toBe(true)
  expect(clinical).toHaveBeenLastCalledWith('/clinical/preview/release?operation_id='+operation,{})
  await act(async()=>finish({id:'stale',artifacts:[],result:{processing_ms:0,probabilities:[]}}))
  expect(stop).toHaveBeenCalledOnce();expect(clinical).toHaveBeenCalledTimes(2)
})
