import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {ResourceStatus} from './ResourceStatus'
import {clearResourceCache,invalidateResources,loadResource,subscribeResource} from '../lib/resourceCache'

afterEach(()=>{cleanup();clearResourceCache();vi.unstubAllGlobals()})
it('keeps a dated cached result with visible errors and an explicit safe-read retry',async()=>{
  const close=vi.fn();vi.stubGlobal('EventSource',vi.fn(function(){return {close,onmessage:null}}))
  const stop=subscribeResource('models',()=>{})
  const loader=vi.fn().mockResolvedValueOnce(['model']).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(['model'])
  await loadResource('models',loader)
  const view=render(<ResourceStatus/>),date=view.container.querySelector('time')?.dateTime
  expect(screen.getByRole('status',{name:'資料更新狀態'})).toHaveTextContent('已顯示資料最早讀取時間')
  await act(async()=>{invalidateResources(false);await Promise.resolve()})
  expect(screen.getByRole('status')).toHaveTextContent('更新失敗，暫時顯示上次資料：offline')
  expect(view.container.querySelector('time')?.dateTime).toBe(date)
  fireEvent.click(screen.getByRole('button',{name:'重試資料更新'}))
  await waitFor(()=>expect(screen.getByRole('status')).not.toHaveTextContent('更新失敗'))
  expect(loader).toHaveBeenCalledTimes(3)
  view.unmount();stop();expect(close).toHaveBeenCalledOnce()
})
it('hides inactive page data and closes its single subscription on exit',async()=>{
  const close=vi.fn(),source=vi.fn(function(){return {close,onmessage:null}});vi.stubGlobal('EventSource',source)
  await loadResource('inactive',async()=>['stale'])
  const view=render(<ResourceStatus/>);expect(screen.queryByRole('status')).not.toBeInTheDocument()
  let stop!:()=>void
  act(()=>{stop=subscribeResource('inactive',()=>{})});expect(screen.getByRole('status')).toBeInTheDocument()
  act(()=>stop());expect(screen.queryByRole('status')).not.toBeInTheDocument()
  view.unmount();expect(source).toHaveBeenCalledOnce();expect(close).toHaveBeenCalledOnce()
})
