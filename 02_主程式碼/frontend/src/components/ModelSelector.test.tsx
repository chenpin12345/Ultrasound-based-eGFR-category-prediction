import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ModelSelector } from './ModelSelector'
import { clearResourceCache } from '../lib/resourceCache'

afterEach(()=>{cleanup();clearResourceCache();vi.unstubAllGlobals()})
const json=(data:unknown)=>new Response(JSON.stringify(data),{headers:{'content-type':'application/json'}})
it('resolves a selected model beyond the first 200, pages and resets search without dropping selection',async()=>{
  const fetch=vi.fn(async(url:string)=>{
    if(url==='/api/models/m236')return json({id:'m236',name:'Selected 236',task:'classification',class_count:3,status:'ready',architecture:'resnet18'})
    const query=new URL(url,'http://localhost').searchParams
    return json({items:[{id:`m${query.get('offset')}`,name:`Page ${query.get('offset')}`,status:'ready',task:'classification'}],total:237,offset:Number(query.get('offset')),limit:50})
  })
  vi.stubGlobal('fetch',fetch)
  render(<ModelSelector label="模型" task="classification" classCount={3} value="m236" onChange={()=>{}}/>)
  await screen.findByRole('option',{name:'Selected 236（已選）'})
  expect(screen.getByRole('combobox')).toHaveValue('m236')
  fireEvent.click(screen.getByRole('button',{name:'模型下一頁'}))
  await screen.findByRole('option',{name:/Page 50/})
  fireEvent.change(screen.getByRole('textbox',{name:'模型搜尋'}),{target:{value:'specific'}})
  await waitFor(()=>expect(fetch.mock.calls.some(([url])=>url.includes('search=specific')&&url.includes('offset=0'))).toBe(true))
  expect(screen.getByRole('combobox')).toHaveValue('m236')
  expect(fetch.mock.calls.some(([url])=>url.includes('limit=200'))).toBe(false)
})
