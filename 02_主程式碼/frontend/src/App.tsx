import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ClinicalLayout } from './clinical/Layout'
import { CapturePage } from './clinical/Capture'
import { DemoPage } from './clinical/Demo'
import { ExamsPage } from './clinical/Exams'
import { ReportsPage } from './clinical/Reports'
import { ClinicalPlans } from './clinical/Admin'
import { ClinicalMonitor } from './clinical/Monitor'
import { initializeLocalSession, LocalPrincipal } from './lib/session'
import { legacyTarget } from './lib/workspaces'
import { AppShell } from './layouts/AppShell'
import { ModelCenterLayout, ModelOverview } from './layouts/ModelCenter'
import { DashboardPage } from './pages/DashboardPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { ProcessingPage } from './pages/ProcessingPage'
import { MasksPage } from './pages/MasksPage'
import { FeaturesPage } from './pages/FeaturesPage'
import { TrainingPage } from './pages/TrainingPage'
import { TrainingMonitorPage } from './pages/TrainingMonitorPage'
import { InferencePage } from './pages/InferencePage'
import { JudgmentPage } from './pages/JudgmentPage'
import { ModelsPage } from './pages/ModelsPage'
import { ModelDetailPage } from './pages/ModelDetailPage'
import { EvaluationsPage, EvaluationDetailPage } from './pages/EvaluationsPage'
import { JobsPage } from './pages/JobsPage'
import { SettingsPage } from './pages/SettingsPage'

function LegacyRedirect() {
  const location=useLocation()
  return <Navigate to={legacyTarget(location.pathname,location.search,location.hash)} replace />
}
export function App() {
  const [principal,setPrincipal]=useState<LocalPrincipal>(),[error,setError]=useState('')
  const initialize=()=>{setError('');void initializeLocalSession().then(setPrincipal).catch(e=>setError((e as Error).message))}
  useEffect(()=>{
    let live=true
    void initializeLocalSession().then(value=>{if(live)setPrincipal(value)}).catch(e=>{if(live)setError((e as Error).message)})
    const expired=()=>{if(live)setError('本機會話需要重新初始化。未成功的操作不會自動重送。')}
    window.addEventListener('local-session-expired',expired)
    return()=>{live=false;window.removeEventListener('local-session-expired',expired)}
  },[])
  if(!principal)return <main className="mx-auto max-w-xl p-8"><h1 className="text-xl font-bold">開啟本機工作區</h1>{error?<><p role="alert" className="my-4 text-red-700">{error}</p><button className="btn-primary" onClick={initialize}>重新初始化</button></>:<p role="status" className="mt-4">正在建立受保護的本機會話…</p>}</main>
  return <>{error&&<div role="alert" className="border-b border-amber-300 bg-amber-50 p-3">{error}<button className="btn-secondary ml-3" onClick={initialize}>重新初始化</button></div>}<Routes>
    <Route path="/" element={<LegacyRedirect/>}/>
    <Route path="clinical" element={<ClinicalLayout/>}>
      <Route index element={<Navigate to="capture" replace/>}/>
      <Route path="capture" element={<CapturePage/>}/>
      <Route path="demo" element={<DemoPage/>}/>
      <Route path="exams" element={<ExamsPage/>}/>
      <Route path="reports" element={<ReportsPage/>}/>
      <Route path="monitor" element={<ClinicalMonitor/>}/>
    </Route>
    <Route path="model-center" element={<ModelCenterLayout/>}>
      <Route index element={<ModelOverview/>}/>
      <Route path="training" element={<TrainingMonitorPage/>}/>
      <Route path="training/:jobId" element={<TrainingMonitorPage/>}/>
      <Route path="models" element={<ModelsPage/>}/>
      <Route path="models/:modelId" element={<ModelDetailPage/>}/>
      <Route path="evaluations" element={<EvaluationsPage/>}/>
      <Route path="evaluations/:evaluationId" element={<EvaluationDetailPage/>}/>
      <Route path="clinical-plans" element={<ClinicalPlans/>}/>
    </Route>
    <Route path="research" element={<AppShell/>}>
      <Route index element={<DashboardPage/>}/>
      <Route path="datasets" element={<DatasetsPage/>}/>
      <Route path="processing" element={<ProcessingPage/>}/>
      <Route path="masks" element={<MasksPage/>}/>
      <Route path="features" element={<FeaturesPage/>}/>
      <Route path="training" element={<TrainingPage/>}/>
      <Route path="training/monitor" element={<LegacyRedirect/>}/>
      <Route path="training/:jobId" element={<LegacyRedirect/>}/>
      <Route path="models/*" element={<LegacyRedirect/>}/>
      <Route path="inference" element={<InferencePage/>}/>
      <Route path="ai-judgment" element={<JudgmentPage/>}/>
      <Route path="jobs" element={<JobsPage/>}/>
      <Route path="settings" element={<SettingsPage/>}/>
    </Route>
    {['login','bootstrap','select-workspace','admin/clinical','datasets','processing','masks','features','training','inference','ai-judgment','models','jobs','settings'].map(path=><Route key={path} path={path+'/*'} element={<LegacyRedirect/>}/>)}
    <Route path="*" element={<main className="p-8"><h1>找不到此頁面</h1><a className="underline" href="/research">返回工作區</a></main>}/>
  </Routes></>
}

