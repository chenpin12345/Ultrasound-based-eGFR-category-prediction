import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell, ChevronDown, Loader2, Menu, Search, UserRound, X } from 'lucide-react'
import { footerNavigation, navigation, workspaceFor, workspaces, type NavItem, type Workspace } from './navigation'
import { useOperator } from '../auth/operator'
import { api } from '../api/client'
import { usePolling } from '../api/hooks'
import type { Overview } from '../api/types'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center gap-3 rounded-md px-3 py-2 text-[14px] transition-colors',
    isActive ? 'bg-steel-wash font-semibold text-steel-dark' : 'text-ink-soft hover:bg-paper-deep hover:text-ink',
  ].join(' ')

function NavEntry({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const Icon = item.icon
  return (
    <NavLink to={item.to} end={item.end} className={linkClass} onClick={onNavigate}>
      <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
      {item.label}
    </NavLink>
  )
}

function Sidebar({ workspace, onNavigate }: { workspace: Workspace; onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5" aria-label="主要導覽">
        {navigation[workspace].map((group, index) => (
          <div key={group.title ?? index}>
            {group.title && <p className="mb-1 px-3 text-[13px] font-semibold text-ink-faint">{group.title}</p>}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavEntry key={item.to} item={item} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <nav className="space-y-0.5 border-t border-line px-3 py-3" aria-label="共用功能">
        {footerNavigation.map((item) => (
          <NavEntry key={item.to} item={item} onNavigate={onNavigate} />
        ))}
      </nav>
    </div>
  )
}

function WorkspaceSwitch({ current }: { current: Workspace }) {
  const navigate = useNavigate()
  return (
    <div className="flex rounded-md border border-line bg-paper p-0.5" role="tablist" aria-label="切換工作台">
      {workspaces.map((ws) => (
        <button
          key={ws.id}
          type="button"
          role="tab"
          aria-selected={current === ws.id}
          onClick={() => navigate(ws.home)}
          className={[
            'whitespace-nowrap rounded px-3 py-1.5 text-[14px] transition-colors sm:px-4',
            current === ws.id ? 'bg-white font-semibold text-ink shadow-[0_0_0_1px_#D3DCDB]' : 'text-ink-soft hover:text-ink',
          ].join(' ')}
        >
          {ws.label}
        </button>
      ))}
    </div>
  )
}

/** 頂部列的小型彈出選單：點外面或按 Esc 關閉。 */
function Popover({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: ReactNode; label: string }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <>
      <button className="fixed inset-0 z-40 cursor-default" aria-label="關閉" onClick={onClose} tabIndex={-1} />
      <div role="menu" aria-label={label} className="absolute right-0 top-full z-50 mt-2 w-[min(92vw,320px)] rounded-lg border border-line bg-white py-1 shadow-xl">
        {children}
      </div>
    </>
  )
}

export default function AppShell() {
  const location = useLocation()
  const { operator, people, setOperator } = useOperator()
  const [lastWorkspace, setLastWorkspace] = useState<Workspace>('research')
  const [menuOpen, setMenuOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [offline, setOffline] = useState(false)

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await api.get<Overview>('/overview'))
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])
  useEffect(() => {
    void loadOverview()
  }, [loadOverview, location.pathname])
  usePolling(loadOverview, 10000)

  useEffect(() => {
    const ws = workspaceFor(location.pathname)
    if (ws) setLastWorkspace(ws)
    setMenuOpen(false)
    setBellOpen(false)
    setUserOpen(false)
  }, [location.pathname])

  const workspace: Workspace = workspaceFor(location.pathname) ?? lastWorkspace
  const alerts = overview
    ? [
        { text: `${overview.images.pending_review ?? 0} 張影像待人工確認`, to: '/research/datasets?status=pending_review', show: (overview.images.pending_review ?? 0) > 0 },
        { text: `${overview.unmatched_images} 張影像還沒對到病人`, to: '/research/datasets?tab=patients', show: overview.unmatched_images > 0 },
        { text: `${overview.failed_jobs} 個背景工作失敗`, to: '/jobs', show: overview.failed_jobs > 0 },
        { text: `${overview.pending_feedback} 筆臨床回饋待審核`, to: '/research/annotation', show: overview.pending_feedback > 0 },
        { text: `醫師端：${overview.clinical?.pending_sign ?? 0} 份報告待簽核`, to: '/clinical/reports', show: (overview.clinical?.pending_sign ?? 0) > 0 },
        { text: `醫師端：${overview.clinical?.ready ?? 0} 筆檢查分析完成，等待確認`, to: '/clinical/worklist', show: (overview.clinical?.ready ?? 0) > 0 },
        { text: `醫師端：${overview.clinical?.needs_data ?? 0} 筆檢查待補資料`, to: '/clinical/worklist', show: (overview.clinical?.needs_data ?? 0) > 0 },
        { text: `醫師端：${overview.clinical?.layout_mismatch ?? 0} 筆檢查版面不符`, to: '/clinical/worklist', show: (overview.clinical?.layout_mismatch ?? 0) > 0 },
        { text: `醫師端：${overview.clinical?.failed ?? 0} 筆分析失敗或部分完成`, to: '/clinical/worklist', show: (overview.clinical?.failed ?? 0) > 0 },
      ].filter((a) => a.show)
    : []
  const operators = people.filter((p) => p.active)

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-white">
        <div className="flex h-14 items-center gap-2 px-4 sm:gap-3 lg:px-5">
          <button type="button" className="rounded-md p-2 text-ink-soft hover:bg-paper lg:hidden" onClick={() => setMenuOpen(true)} aria-label="開啟導覽選單">
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-baseline gap-2 lg:w-[212px]">
            <span className="whitespace-nowrap text-[16px] font-bold tracking-wide sm:text-[17px]">腎超工作台</span>
          </div>
          <div className="hidden sm:block">
            <WorkspaceSwitch current={workspace} />
          </div>
          <label className="ml-auto hidden max-w-xs flex-1 items-center gap-2 rounded-md border border-line bg-paper px-3 py-1.5 md:flex">
            <Search className="h-4 w-4 text-ink-faint" aria-hidden />
            <span className="sr-only">搜尋</span>
            <input type="search" placeholder="病人編號、影像編號" className="w-full bg-transparent text-[14px] placeholder:text-ink-faint focus:outline-none" />
          </label>
          <NavLink to="/jobs" className="ml-auto flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[13px] text-ink-soft hover:bg-paper md:ml-0" title="執行中的背景工作">
            <Loader2 className={`h-4 w-4 text-steel ${overview?.running_jobs ? 'animate-spin' : ''}`} aria-hidden />
            <span className="whitespace-nowrap">
              {overview?.running_jobs ?? 0}
              <span className="hidden xl:inline"> 個工作執行中</span>
            </span>
          </NavLink>

          <div className="relative">
            <button type="button" onClick={() => setBellOpen((v) => !v)} className="relative rounded-md p-2 text-ink-soft hover:bg-paper" aria-label={`提醒，${alerts.length} 則`} aria-expanded={bellOpen}>
              <Bell className="h-5 w-5" />
              {alerts.length > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-alert px-1 text-[10px] font-bold text-white">{alerts.length}</span>}
            </button>
            <Popover open={bellOpen} onClose={() => setBellOpen(false)} label="提醒">
              <p className="px-4 py-2 text-[13px] font-semibold text-ink-faint">需要處理的事</p>
              {alerts.length ? (
                alerts.map((a) => (
                  <Link key={a.text} to={a.to} role="menuitem" className="block px-4 py-2.5 text-[14px] hover:bg-paper">
                    {a.text}
                  </Link>
                ))
              ) : (
                <p className="px-4 py-2.5 text-[14px] text-ink-soft">目前沒有需要處理的事。</p>
              )}
            </Popover>
          </div>

          <div className="relative">
            <button type="button" onClick={() => setUserOpen((v) => !v)} className="flex items-center gap-2 rounded-md py-1 pl-1 pr-2 hover:bg-paper" aria-expanded={userOpen} aria-label="操作者選單">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-steel text-[13px] font-semibold text-white">{operator ? operator.slice(0, 1) : <UserRound className="h-4 w-4" />}</span>
              <span className="hidden text-left text-[13px] leading-tight sm:block">
                {operator || '尚未選擇操作者'}
                <span className="block text-ink-faint">本機</span>
              </span>
              <ChevronDown className="hidden h-4 w-4 text-ink-faint sm:block" aria-hidden />
            </button>
            <Popover open={userOpen} onClose={() => setUserOpen(false)} label="操作者選單">
              <p className="px-4 py-2 text-[13px] text-ink-faint">選擇操作者（記錄是誰做的，不是登入）</p>
              {operators.length ? (
                operators.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={operator === p.name}
                    onClick={() => {
                      setOperator(p.name)
                      setUserOpen(false)
                    }}
                    className={`flex w-full items-center justify-between px-4 py-2 text-left text-[14px] hover:bg-paper ${operator === p.name ? 'font-semibold text-steel-dark' : ''}`}
                  >
                    {p.name}
                    <span className="text-[12px] text-ink-faint">{p.kind === 'physician' ? '醫師' : '操作者'}</span>
                  </button>
                ))
              ) : (
                <p className="px-4 py-2 text-[14px] text-ink-soft">名單是空的。</p>
              )}
              <Link to="/settings?tab=people" role="menuitem" className="block border-t border-line px-4 py-2.5 text-[14px] text-steel hover:bg-paper">
                管理醫師與操作者名單
              </Link>
            </Popover>
          </div>
        </div>
        {overview?.clinical?.receiver_active && (
          <p className="flex items-center gap-3 border-t border-ok/20 bg-ok-wash px-4 py-1 text-[13px] text-ok lg:px-5">
            雙機接收進行中
            <Link to="/clinical/acquisition" className="underline">查看網址與配對碼</Link>
            <button type="button" className="underline" onClick={() => void api.post('/clinical/receiver/stop').then(loadOverview)}>停止接收</button>
          </p>
        )}
        {offline && (
          <p className="border-t border-alert/20 bg-alert-wash px-4 py-1 text-[13px] text-alert lg:px-5">無法連線到後端。請用 start.bat 啟動系統；目前畫面上的資料可能不是最新的。</p>
        )}
      </header>

      <div className="flex">
        <aside className="sticky top-[57px] hidden h-[calc(100vh-57px)] w-[244px] shrink-0 border-r border-line bg-paper lg:block">
          <Sidebar workspace={workspace} />
        </aside>

        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="導覽選單">
            <button className="absolute inset-0 bg-ink/40" aria-label="關閉選單" onClick={() => setMenuOpen(false)} />
            <aside className="relative h-full w-[min(82vw,280px)] bg-paper shadow-xl">
              <div className="flex h-14 items-center justify-between border-b border-line px-4">
                <WorkspaceSwitch current={workspace} />
                <button className="ml-auto rounded-md p-2 text-ink-soft" onClick={() => setMenuOpen(false)} aria-label="關閉選單">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="h-[calc(100%-56px)]">
                <Sidebar workspace={workspace} onNavigate={() => setMenuOpen(false)} />
              </div>
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
