import {
  Activity, BrainCircuit, ChartNoAxesCombined, Database, FlaskConical, History, Image, Menu,
  Microscope, ScanLine, Settings, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

const navigation = [
  { to: '/', label: '儀表板', icon: ChartNoAxesCombined },
  { to: '/datasets', label: '資料集管理', icon: Database },
  { to: '/processing', label: '影像處理', icon: Image },
  { to: '/masks', label: '遮罩產生', icon: ScanLine },
  { to: '/features', label: '特徵擷取', icon: Microscope },
  { to: '/training', label: '模型訓練', icon: BrainCircuit },
  { to: '/training/monitor', label: '訓練監控', icon: Activity },
  { to: '/inference', label: 'AI 推論', icon: Sparkles },
  { to: '/models', label: '模型管理', icon: FlaskConical },
  { to: '/jobs', label: '歷史工作', icon: History },
  { to: '/settings', label: '系統設定', icon: Settings },
]

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-[#102f37] text-white">
      <div className="flex h-20 items-center gap-3 border-b border-white/10 px-5">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-clinical-400 text-[#0c3037] shadow-lg shadow-clinical-900/20"><Microscope className="h-6 w-6" /></div>
        <div><p className="font-bold tracking-wide">ISU AI</p><p className="text-xs text-clinical-200">影像研究工作台</p></div>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="主要導覽">
        {navigation.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/' || to === '/training'}
            onClick={onNavigate}
            className={({ isActive }) => `flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive ? 'bg-white text-[#15383f] shadow-sm' : 'text-slate-200 hover:bg-white/10 hover:text-white'}`}
          >
            <Icon className="h-[18px] w-[18px] shrink-0" />
            {label}
          </NavLink>
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
  useEffect(() => setMenuOpen(false), [location.pathname])
  return (
    <div className="min-h-screen bg-[#f4f7f8] text-slate-800">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 lg:block"><Sidebar /></aside>
      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-slate-950/50" aria-label="關閉導覽選單" onClick={() => setMenuOpen(false)} />
          <aside className="relative h-full w-[min(82vw,19rem)] shadow-2xl"><Sidebar onNavigate={() => setMenuOpen(false)} /><button className="absolute right-3 top-5 rounded-lg bg-white/10 p-2 text-white" onClick={() => setMenuOpen(false)} aria-label="關閉選單"><X className="h-5 w-5" /></button></aside>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex items-center gap-3"><button className="rounded-xl border border-slate-200 p-2 text-slate-600 lg:hidden" onClick={() => setMenuOpen(true)} aria-label="開啟導覽選單"><Menu className="h-5 w-5" /></button><div><p className="text-sm font-semibold text-ink">本機研究環境</p><p className="hidden text-xs text-slate-500 sm:block">影像處理、訓練與推論皆在此裝置執行</p></div></div>
          <div className="flex items-center gap-2 rounded-full bg-clinical-50 px-3 py-1.5 text-xs font-semibold text-clinical-800"><span className="h-2 w-2 rounded-full bg-emerald-500" />Local only</div>
        </header>
        <main className="mx-auto min-h-[calc(100vh-8rem)] max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8"><Outlet /></main>
        <footer className="border-t border-amber-200 bg-amber-50 px-4 py-3 text-center text-xs font-medium leading-5 text-amber-900 sm:px-6">
          本系統僅供研究使用，不構成醫療診斷，亦不可替代專業醫療人員的判斷。
        </footer>
      </div>
    </div>
  )
}
