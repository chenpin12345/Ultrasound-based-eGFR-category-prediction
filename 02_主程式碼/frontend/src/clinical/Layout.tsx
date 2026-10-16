import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { WorkspaceHeader } from '../components/WorkspaceHeader'

export function ClinicalLayout() {
  const location=useLocation()
  return <div className="min-h-screen bg-[#f3f6f8] text-slate-800"><WorkspaceHeader/>
    <nav className="border-b bg-white" aria-label="醫師工作區導覽"><div className="mx-auto flex max-w-7xl flex-wrap gap-2 px-5 py-3">{[['capture','超音波設備接收'],['demo','真實圖片雙機示範'],['exams','病人與檢查'],['reports','報告中心'],['monitor','紀錄與作業監控']].map(([path,label])=><NavLink key={path} to={'/clinical/'+path} className={({isActive})=>`rounded-lg px-4 py-3 text-sm font-semibold ${isActive?'bg-teal-800 text-white':'hover:bg-slate-100'}`}>{label}</NavLink>)}</div></nav>
    <main key={location.pathname} className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><Outlet/></main><footer className="mx-auto max-w-7xl px-8 py-6 text-sm text-slate-600">研究用途原型 · AI 輔助資料由醫師判讀；示範案例與病人檢查分開保存。</footer></div>
}
