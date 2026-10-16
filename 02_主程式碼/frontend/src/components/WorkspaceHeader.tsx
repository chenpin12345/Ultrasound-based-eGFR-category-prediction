import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { workspaces, workspaceOf } from '../lib/workspaces'
import { ReceiverStatus } from './ReceiverStatus'
import { ResourceStatus } from './ResourceStatus'

export function WorkspaceHeader({leading}: {leading?:ReactNode}) {
  const location=useLocation(), zone=workspaceOf(location.pathname)
  return <header className="sticky top-0 z-30 border-b border-slate-200 bg-white px-4 py-3 sm:px-6 lg:px-8">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">{leading}<div><p className="font-semibold text-ink">ISU AI · {zone.label}</p><p className="text-xs text-slate-600">本機模式 · 非個人身分驗證</p></div></div>
      <nav aria-label="切換工作區" className="flex flex-wrap items-center gap-2">
        {workspaces.filter(item=>item.id!==zone.id).map(item=><Link className="btn-secondary min-h-11" key={item.id} to={item.href}>{item.label}</Link>)}
        <Link className="btn-ghost min-h-11" to="/research/settings">系統設定</Link>
      </nav>
    </div><ReceiverStatus/><ResourceStatus/>
  </header>
}
