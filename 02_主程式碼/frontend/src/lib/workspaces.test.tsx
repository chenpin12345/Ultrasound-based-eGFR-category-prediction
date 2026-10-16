import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { legacyTarget, workspaceOf } from './workspaces'
import { WorkspaceHeader } from '../components/WorkspaceHeader'

vi.mock('../components/ReceiverStatus',()=>({ReceiverStatus:()=>null}))
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
describe('three workspace navigation',()=>{
  it.each([
    ['/models','/model-center/models'],
    ['/research/models/model-1','/model-center/models/model-1'],
    ['/training','/research/training'],
    ['/research/training/job-1','/model-center/training/job-1'],
    ['/training/monitor','/model-center/training'],
    ['/admin/clinical','/model-center/clinical-plans'],
    ['/login','/research'],
  ])('preserves query and hash from %s',(old,target)=>{
    expect(legacyTarget(old,'?dataset_id=d&model_id=m','#result')).toBe(target+'?dataset_id=d&model_id=m#result')
  })
  it.each(['/research','/model-center/models','/clinical/reports'])('shows exactly two other zones on %s',path=>{
    const close=vi.fn(),source=vi.fn(function(){return {close,onmessage:null}})
    vi.stubGlobal('EventSource',source)
    const view=render(<MemoryRouter initialEntries={[path]}><WorkspaceHeader/></MemoryRouter>)
    const zone=workspaceOf(path)
    const labels=['工作區','模型區','醫師工作區'].filter(label=>label!==zone.label)
    for(const label of labels) expect(screen.getByRole('link',{name:label})).toBeInTheDocument()
    expect(screen.queryByRole('link',{name:zone.label})).not.toBeInTheDocument()
    expect(screen.queryByText(/登出|登入帳號/)).not.toBeInTheDocument()
    expect(source).toHaveBeenCalledOnce()
    view.unmount();expect(close).toHaveBeenCalledOnce()
  })
})
