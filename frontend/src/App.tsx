import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './layouts/AppShell'
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
import { JobsPage } from './pages/JobsPage'
import { SettingsPage } from './pages/SettingsPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="datasets" element={<DatasetsPage />} />
        <Route path="processing" element={<ProcessingPage />} />
        <Route path="masks" element={<MasksPage />} />
        <Route path="features" element={<FeaturesPage />} />
        <Route path="training" element={<TrainingPage />} />
        <Route path="training/monitor" element={<TrainingMonitorPage />} />
        <Route path="training/:jobId" element={<TrainingMonitorPage />} />
        <Route path="inference" element={<InferencePage />} />
        <Route path="ai-judgment" element={<JudgmentPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
