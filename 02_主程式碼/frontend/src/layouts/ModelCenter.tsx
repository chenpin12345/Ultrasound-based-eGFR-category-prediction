import { useCallback } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { WorkspaceHeader } from '../components/WorkspaceHeader'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { requestJson } from '../lib/api'
import { Card, InlineNotice } from '../components/ui'

interface RegistrySummary {items:unknown[];total:number}
export function ModelCenterLayout() {
  return <div className="min-h-screen bg-slate-50 text-slate-800"><WorkspaceHeader/><nav className="border-b bg-white" aria-label="模型區導覽"><div className="mx-auto flex max-w-7xl flex-wrap gap-2 p-4">{[['','模型總覽'],['training','訓練監控'],['models','模型管理'],['evaluations','評估比較'],['clinical-plans','醫師分析方案']].map(([path,label])=><NavLink key={path} end={path===''} to={'/model-center'+(path?'/'+path:'')} className={({isActive})=>`rounded-lg px-4 py-3 text-sm font-semibold ${isActive?'bg-teal-800 text-white':'hover:bg-slate-100'}`}>{label}</NavLink>)}</div></nav><main className="mx-auto max-w-7xl space-y-6 px-4 py-6 md:px-8"><Outlet/></main></div>
}
export function ModelOverview() {
  const load=useCallback((signal?:AbortSignal)=>requestJson<RegistrySummary>('/models?limit=1',{signal}),[])
  const registry=useAsyncResource(load,true,'model-center-count')
  return <><div><p className="text-sm text-teal-700">共用模型庫與運算資源</p><h1 className="mt-2 text-2xl font-bold">模型總覽</h1><p className="mt-3 text-slate-600">管理權重、查看訓練工作及封存醫師分析方案。單張預測機率不是模型準確率。</p></div>{registry.error&&<InlineNotice tone="danger">{registry.error}</InlineNotice>}<Card className="p-6"><p className="text-sm text-slate-600">模型庫已登錄版本</p><p className="my-3 text-3xl font-semibold tabular-nums">{registry.data?.total??'—'}</p><Link className="btn-primary" to="/model-center/models">開啟模型管理</Link></Card><div className="grid gap-5 md:grid-cols-2"><Card className="p-6"><h2 className="font-bold">訓練監控</h2><p className="my-3 text-slate-600">查看進度、epoch、loss 與訓練產物。訓練設定仍在工作區。</p><Link className="btn-secondary" to="/model-center/training">查看訓練工作</Link></Card><Card className="p-6"><h2 className="font-bold">醫師分析方案</h2><p className="my-3 text-slate-600">保留確切權重及來源前處理設定。研究預設切換不改變封存方案。</p><Link className="btn-secondary" to="/model-center/clinical-plans">管理分析方案</Link></Card></div></>
}
