import { Link, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import ClinicalHome from './pages/clinical/ClinicalHome'
import Worklist from './pages/clinical/Worklist'
import ExamWorkspace from './pages/clinical/ExamWorkspace'
import ReportEditor from './pages/clinical/ReportEditor'
import Acquisition from './pages/clinical/Acquisition'
import PatientsExams from './pages/clinical/PatientsExams'
import PatientDetail from './pages/clinical/PatientDetail'
import Reports from './pages/clinical/Reports'
import Overview from './pages/research/Overview'
import Datasets from './pages/research/Datasets'
import ImageDetail from './pages/research/ImageDetail'
import ImportReport from './pages/research/ImportReport'
import Annotation from './pages/research/Annotation'
import AnnotationEditor from './pages/research/AnnotationEditor'
import Pipelines from './pages/research/Pipelines'
import Preprocessing from './pages/research/Preprocessing'
import TemplateEditor from './pages/research/TemplateEditor'
import Features from './pages/research/Features'
import Training from './pages/research/Training'
import TrainingRun from './pages/research/TrainingRun'
import ExperimentDetail from './pages/research/ExperimentDetail'
import Registry from './pages/research/Registry'
import ModelDetail from './pages/research/ModelDetail'
import Analysis from './pages/research/Analysis'
import EgfrTraining from './pages/research/EgfrTraining'
import EgfrCompare, { EgfrCompareIndex } from './pages/research/EgfrCompare'
import MaskSets from './pages/research/MaskSets'
import Jobs from './pages/shared/Jobs'
import Trash from './pages/shared/Trash'
import Settings from './pages/shared/Settings'

function NotFound() {
  return (
    <div className="max-w-lg">
      <h1 className="text-[24px] font-bold">找不到這個頁面</h1>
      <p className="mt-2 text-ink-soft">
        網址可能已經改變。
        <Link to="/research" className="ml-1 text-steel underline">
          回到研究總覽
        </Link>
      </p>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/research" replace />} />
        <Route path="clinical">
          <Route index element={<ClinicalHome />} />
          <Route path="worklist" element={<Worklist />} />
          <Route path="exams/:examId" element={<ExamWorkspace />} />
          <Route path="exams/:examId/report" element={<ReportEditor />} />
          <Route path="acquisition" element={<Acquisition />} />
          <Route path="patients" element={<PatientsExams />} />
          <Route path="patients/:patientId" element={<PatientDetail />} />
          <Route path="reports" element={<Reports />} />
        </Route>
        <Route path="research">
          <Route index element={<Overview />} />
          <Route path="datasets" element={<Datasets />} />
          <Route path="datasets/images/:imageId" element={<ImageDetail />} />
          <Route path="datasets/imports/:importId" element={<ImportReport />} />
          <Route path="annotation" element={<Annotation />} />
          <Route path="annotation/:taskId" element={<AnnotationEditor />} />
          <Route path="pipelines" element={<Pipelines />} />
          <Route path="preprocessing" element={<Preprocessing />} />
          <Route path="preprocessing/templates/:templateId" element={<TemplateEditor />} />
          <Route path="features" element={<Features />} />
          <Route path="egfr" element={<EgfrTraining />} />
          <Route path="egfr/compare" element={<EgfrCompareIndex />} />
          <Route path="egfr/compare/:experimentId" element={<EgfrCompare />} />
          <Route path="egfr/models" element={<Registry key="egfr" task="egfr" />} />
          <Route path="segmentation" element={<Training key="segmentation" task="segmentation" />} />
          <Route path="segmentation/mask-sets" element={<MaskSets />} />
          <Route path="segmentation/models" element={<Registry key="segmentation" task="segmentation" />} />
          <Route path="grading" element={<Training key="grade" task="grade" />} />
          <Route path="grading/models" element={<Registry key="grade" task="grade" />} />
          <Route path="training" element={<Navigate to="/research/egfr" replace />} />
          <Route path="training/:runId" element={<TrainingRun />} />
          <Route path="experiments" element={<Navigate to="/research/grading" replace />} />
          <Route path="experiments/:experimentId" element={<ExperimentDetail />} />
          <Route path="models" element={<Navigate to="/research/egfr/models" replace />} />
          <Route path="models/:modelId" element={<ModelDetail />} />
          <Route path="analysis" element={<Analysis />} />
        </Route>
        <Route path="jobs" element={<Jobs />} />
        <Route path="trash" element={<Trash />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
