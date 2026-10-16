import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {MemoryRouter} from 'react-router-dom'
import {DemoPage} from './Demo'
import {ExamsPage} from './Exams'
import {ClinicalPlans} from './Admin'
import {clinical} from './client'

vi.mock('./client',async importOriginal=>({...await importOriginal<typeof import('./client')>(),clinical:vi.fn()}))
vi.mock('./RecordPicker',()=>({ClinicalRecordPicker:()=>null}))
vi.mock('../components/ModelSelector',()=>({ModelSelector:()=>null}))
const data:Record<string,unknown>={}
vi.mock('./hooks',async importOriginal=>({
  ...await importOriginal<typeof import('./hooks')>(),
  useClinical:(path:string)=>({data:path?data[path.split('?')[0]]:undefined,error:'',refresh:vi.fn()}),
}))
afterEach(()=>{cleanup();vi.resetAllMocks();for(const key of Object.keys(data))delete data[key]})

const plan={id:'plan-a',name:'方案 A',created:1790000000,profile:{mode:'prepared',width:32,height:24,validated_for_patient:false},classifier:{name:'c',architecture:'mobilenetv2_mlp',class_count:3,sha256:'a'.repeat(64)},segmenter:null,requirements:[{field:'age',label:'年齡'},{field:'has_diabetes',label:'糖尿病狀態（有／無）'}]}
const iface=(address:string,name:string,kind='private',up:boolean|null=true)=>({interface:name,address,family:4,is_up:up,kind,supported:kind!=='ipv6',note:kind==='link_local'?'169.254 自動位址':''})

function demoFixtures(analyzable=true){
  data['/clinical/receiver-settings']={interfaces:[iface('192.168.1.20','Ethernet'),iface('169.254.7.7','Wi-Fi','link_local'),iface('127.0.0.1','Loopback','loopback')],recommended:'192.168.1.20',saved:null,saved_check:null}
  data['/clinical/default-plans']={sources:{network_demo:{source:'network_demo',label:'圖片傳輸',mode:'plan',plan:analyzable?plan:null,analyzable,problems:analyzable?[]:['模型區尚未設定圖片傳輸的預設分析方案。'],setting:null}}}
  data['/clinical/plans']=[{...plan,summary:plan}];data['/clinical/demo-sessions']=[]
}

it('preselects the single LAN card, labels link-local and loopback, and starts with the default plan',async()=>{
  demoFixtures()
  vi.mocked(clinical).mockResolvedValue({session_id:'s1',fingerprint:'f',expires:1,url:'https://192.168.1.20:5000',requirements:['age']})
  render(<MemoryRouter><DemoPage/></MemoryRouter>)
  await waitFor(()=>expect(screen.getByRole('radio',{name:/192\.168\.1\.20/})).toBeChecked())
  expect(screen.getByRole('radio',{name:/169\.254\.7\.7.*169\.254 自動位址/})).not.toBeChecked()
  expect(screen.getByRole('radio',{name:/127\.0\.0\.1.*僅限本機測試/})).not.toBeChecked()
  expect(screen.getAllByText(/方案 A/).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button',{name:'開始接收'}))
  await waitFor(()=>expect(clinical).toHaveBeenCalledWith('/clinical/demo-sessions',{host:'192.168.1.20',port:null,address_mode:'auto',analysis:{mode:'default'}}))
  expect(await screen.findByText(/本方案需要 A 填寫：年齡/)).toBeInTheDocument()
})

it('manual address goes to the backend unchanged, and an unusable default blocks instead of downgrading',async()=>{
  demoFixtures(false)
  render(<MemoryRouter><DemoPage/></MemoryRouter>)
  fireEvent.click(screen.getByRole('radio',{name:'手動輸入'}))
  fireEvent.change(screen.getByLabelText(/B 的 IPv4 位址/),{target:{value:'10.0.0.99'}})
  expect(screen.getByRole('button',{name:'開始接收'})).toBeDisabled()
  expect(screen.getAllByRole('alert').map(a=>a.textContent).join(' ')).toMatch(/不會自動改用其他方案/)
  fireEvent.click(screen.getByRole('radio',{name:/僅接收及預覽（明確不分析）/}))
  vi.mocked(clinical).mockRejectedValue(new Error('此位址不屬於 B（本機）的任何網路介面。'))
  fireEvent.click(screen.getByRole('button',{name:'開始接收'}))
  await waitFor(()=>expect(clinical).toHaveBeenCalledWith('/clinical/demo-sessions',{host:'10.0.0.99',port:null,address_mode:'manual',analysis:{mode:'preview_only'}}))
  expect(await screen.findByText(/不屬於 B/)).toBeInTheDocument()
})

it('opens the transferred case with saved data, highlights only missing fields and saves through the backend',async()=>{
  data['/clinical/exams/e1']={id:'e1',kind:'demo',title:'CASE-A',side:'left',revision:1,payload:{case_code:'CASE-A',age:61,diabetes_status:'unknown',patient_name:'王小明'},diabetes_status:'unknown',
    frames:[],versions:[{revision:1}],transfer:{status:'needs_data',plan_mode:'plan',plan,missing_fields:['has_diabetes'],missing_now:['has_diabetes']}}
  data['/clinical/plans']=[]
  vi.mocked(clinical).mockResolvedValue({revision:2,resumed:1})
  render(<MemoryRouter initialEntries={['/clinical/exams?exam=e1&frame=f1']}><ExamsPage/></MemoryRouter>)
  expect(screen.getByRole('alert')).toHaveTextContent('待補資料：糖尿病狀態（有／無）')
  expect(screen.getByLabelText('年齡（僅此案例）')).toHaveValue(61)
  expect(screen.getByLabelText('糖尿病狀態')).toHaveValue('unknown')
  expect(screen.getByLabelText('糖尿病狀態').className).toMatch(/border-red-500/)
  expect(screen.getByLabelText('年齡（僅此案例）').className).not.toMatch(/border-red-500/)
  expect(screen.getByLabelText('姓名（示範顯示，未核實）')).toHaveValue('王小明')
  fireEvent.change(screen.getByLabelText('糖尿病狀態'),{target:{value:'no'}})
  fireEvent.click(screen.getByRole('button',{name:'保存案例資料'}))
  await waitFor(()=>expect(clinical).toHaveBeenCalledWith('/clinical/exams/e1/case?expected_revision=1',expect.objectContaining({title:'CASE-A',side:'left',age:61,diabetes:'no',patient_name:'王小明'}),'PUT'))
  expect(await screen.findByText(/已自動排入分析/)).toBeInTheDocument()
})

it('complete case data is shown read-only without asking to save or pick a plan again',()=>{
  data['/clinical/exams/e2']={id:'e2',kind:'demo',title:'CASE-B',side:'right',revision:1,payload:{age:45,has_diabetes:0},diabetes_status:'no',frames:[],versions:[],transfer:{status:'completed',plan_mode:'plan',plan,missing_fields:[],missing_now:[]}}
  data['/clinical/plans']=[]
  render(<MemoryRouter initialEntries={['/clinical/exams?exam=e2']}><ExamsPage/></MemoryRouter>)
  expect(screen.queryByRole('button',{name:'保存案例資料'})).toBeNull()
  expect(screen.getByText('無')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/重新分析/})).toBeNull()
})

it('capture adopts the capture default once and only offers start-and-analyze when the case data is complete',async()=>{
  const {CapturePage}=await import('./Capture')
  data['/clinical/plans']=[{...plan,summary:plan}]
  data['/clinical/default-plans']={sources:{capture:{source:'capture',label:'設備擷取',mode:'plan',plan,analyzable:true,problems:[],setting:null}}}
  data['/clinical/exams/x1']={id:'x1',payload:{age:50}}
  const view=render(<MemoryRouter initialEntries={['/clinical/capture?exam=x1']}><CapturePage/></MemoryRouter>)
  expect(screen.getByLabelText('分析方案')).toHaveValue('plan-a')
  expect(screen.getByRole('button',{name:'開始接收與分析'})).toBeDisabled()
  expect(screen.getByRole('alert')).toHaveTextContent('糖尿病狀態（有／無）')
  view.unmount()
  data['/clinical/exams/x1']={id:'x1',payload:{age:50,has_diabetes:0}}
  render(<MemoryRouter initialEntries={['/clinical/capture?exam=x1']}><CapturePage/></MemoryRouter>)
  expect(screen.getByRole('button',{name:'開始接收與分析'})).toBeEnabled()
})

it('model center requires an explicit plan and compatibility evidence for the default',async()=>{
  data['/clinical/plans']=[{id:'plan-a',name:'方案 A',created:1790000000,profile:{mode:'prepared',evidence:'e',validated_for_patient:false},summary:plan},{id:'plan-u',name:'未確認',created:1,profile:{mode:'unknown',evidence:''},summary:{...plan,id:'plan-u',name:'未確認'}}]
  data['/clinical/default-plans']={sources:{network_demo:{source:'network_demo',label:'圖片傳輸',mode:null,plan:null,analyzable:false,problems:['模型區尚未設定圖片傳輸的預設分析方案。'],setting:null},
    capture:{source:'capture',label:'設備擷取',mode:null,plan:null,analyzable:false,problems:['x'],setting:null}},history:[]}
  vi.mocked(clinical).mockResolvedValue({id:'d1'})
  render(<MemoryRouter><ClinicalPlans/></MemoryRouter>)
  const select=screen.getByLabelText('圖片傳輸預設方案') as HTMLSelectElement
  expect([...select.options].map(o=>o.value)).toEqual(['','plan-a'])  // unknown-source plan hidden, nothing preselected
  expect(screen.getByLabelText('設備擷取預設方案').querySelectorAll('option')).toHaveLength(1)  // not validated for patients
  fireEvent.change(select,{target:{value:'plan-a'}})
  fireEvent.change(screen.getAllByLabelText(/相容依據/)[0],{target:{value:'來源尺寸 32×24，已完成前處理'}})
  fireEvent.click(screen.getAllByRole('button',{name:'設定為醫師端預設'})[0])
  await waitFor(()=>expect(clinical).toHaveBeenCalledWith('/clinical/default-plans',{source:'network_demo',mode:'plan',plan_id:'plan-a',evidence:'來源尺寸 32×24，已完成前處理'}))
})
