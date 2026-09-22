import {
  Activity, BrainCircuit, ChartNoAxesCombined, Database, FlaskConical, History, Image, Menu,
  Microscope, ScanLine, Settings, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { WorkflowBar } from '../components/Workflow'
import { ResourceStatus } from '../components/ResourceStatus'
import { workflowLink, workflowSteps } from '../lib/workflow'

const navigation = [
  { to: '/', label: '研究總覽', icon: ChartNoAxesCombined },
  { to: '/datasets', label: '資料集管理', icon: Database },
  { to: '/processing', label: '影像處理', icon: Image },
  { to: '/masks', label: '遮罩產生', icon: ScanLine },
  { to: '/features', label: '特徵擷取', icon: Microscope },
  { to: '/training', label: '模型訓練', icon: BrainCircuit },
  { to: '/training/monitor', label: '訓練監控', icon: Activity },
  { to: '/inference', label: 'AI 推論', icon: Sparkles },
  { to: '/ai-judgment', label: 'AI判斷', icon: BrainCircuit },
  { to: '/models', label: '模型管理', icon: FlaskConical },
  { to: '/jobs', label: '歷史工作', icon: History },
  { to: '/settings', label: '系統設定', icon: Settings },
]

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const [params] = useSearchParams()
  const datasetId = params.get('dataset_id') || ''
  return (
    <div className="flex h-full flex-col bg-[#142D45] text-white">
      <div className="flex h-20 items-center gap-3 border-b border-white/10 px-5">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-clinical-400 text-[#0c3037] shadow-lg shadow-clinical-900/20"><Microscope className="h-6 w-6" /></div>
        <div><p className="font-bold tracking-wide">ISU AI</p><p className="text-xs text-clinical-200">影像研究工作台</p></div>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="主要導覽">
        {navigation.map(({ to, label, icon: Icon }, index) => (
          <Fragment key={to}>
          {[1, 9, 11].includes(index) && <p className="pb-2 pl-3 pt-5 text-[11px] font-semibold tracking-widest text-slate-400">{index === 1 ? '分析與訓練流程' : index === 9 ? '工作與模型' : '系統'}</p>}
          <NavLink
            key={to}
            to={workflowLink(to, datasetId)}
            end={to === '/' || to === '/training'}
            onClick={onNavigate}
            className={({ isActive }) => `flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive ? 'bg-[#E6F7F8] text-[#075D66] shadow-sm' : 'text-slate-200 hover:bg-white/10 hover:text-white'}`}
          >
            <Icon className="h-[18px] w-[18px] shrink-0" />
            {label}
          </NavLink>
          </Fragment>
        ))}
      </nav>
      <div className="m-3 rounded-xl border border-clinical-300/20 bg-clinical-300/10 p-3 text-xs leading-5 text-clinical-100">
        <div className="mb-1 flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4" />資料留在本機</div>
        不含雲端分析或第三方追蹤。
      </div>
    </div>
  )
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const [params] = useSearchParams()
  const menuButton = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLElement>(null)
  const main = useRef<HTMLElement>(null)
  useEffect(() => setMenuOpen(false), [location.pathname])
  useEffect(() => { main.current?.focus({ preventScroll: true }) }, [location.pathname])
  useEffect(() => {
    if (!menuOpen) return
    const nodes = () => [...(panel.current?.querySelectorAll<HTMLElement>('a[href],button:not([disabled])') || [])]
    nodes()[0]?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); menuButton.current?.focus() }
      if (event.key !== 'Tab') return
      const items = nodes(); const first = items[0]; const last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', keydown)
    return () => { window.removeEventListener('keydown', keydown); document.body.style.overflow = previous }
  }, [menuOpen])
  const contextKey = location.pathname === '/training' ? location.pathname : `${location.pathname}:${params.get('dataset_id') || ''}:${params.get('source_job') || ''}:${params.get('input') || ''}`
  const isWorkflowPage = workflowSteps.some(([path]) => path === location.pathname)
  return (
    <div className="min-h-screen bg-[#F3F7FB] text-slate-800">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-white focus:p-3">跳至主要內容</a>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 lg:block"><Sidebar /></aside>
      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="主要導覽選單">
          <button className="absolute inset-0 bg-slate-950/50" aria-label="關閉導覽選單" onClick={() => setMenuOpen(false)} />
          <aside ref={panel} className="relative h-full w-[min(82vw,19rem)] shadow-2xl"><Sidebar onNavigate={() => setMenuOpen(false)} /><button className="absolute right-3 top-5 rounded-lg bg-white/10 p-2 text-white" onClick={() => { setMenuOpen(false); menuButton.current?.focus() }} aria-label="關閉選單"><X className="h-5 w-5" /></button></aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex items-center gap-3"><button ref={menuButton} aria-expanded={menuOpen} className="rounded-xl border border-slate-200 p-2 text-slate-600 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="開啟導覽選單"><Menu className="h-5 w-5" /></button><div><p className="text-sm font-semibold text-ink">本機研究環境</p><p className="hidden text-xs text-slate-500 sm:block">影像處理、訓練與推論皆在此裝置執行</p></div></div>
          <div className="flex items-center gap-2 rounded-full bg-clinical-50 px-3 py-1.5 text-xs font-semibold text-clinical-800"><span className="h-2 w-2 rounded-full bg-emerald-500" />Local only</div>
        </header>
        <main ref={main} id="main-content" tabIndex={-1} className="mx-auto min-h-[calc(100vh-8rem)] max-w-[1840px] px-4 py-6 outline-none sm:px-6 lg:px-8"><ResourceStatus />{isWorkflowPage && <WorkflowBar />}<div key={contextKey}><Outlet /></div></main>
        <footer className="border-t border-amber-200 bg-amber-50 px-4 py-3 text-center text-xs font-medium leading-5 text-amber-900 sm:px-6">
          本系統僅供研究使用，不構成醫療診斷，亦不可替代專業醫療人員的判斷。
        </footer>
      </div>
    </div>
  )
}
