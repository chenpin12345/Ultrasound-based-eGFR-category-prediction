import {
  Activity,
  Boxes,
  BrainCircuit,
  GitCompare,
  Layers3,
  Database,
  FileText,
  FlaskConical,
  History,
  Home,
  Layers,
  LayoutDashboard,
  ListChecks,
  MonitorSmartphone,
  PenTool,
  ScanLine,
  Settings,
  Sparkles,
  Trash2,
  Users,
  Workflow,
  type LucideIcon,
} from 'lucide-react'

export type Workspace = 'clinical' | 'research'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

export interface NavGroup {
  title?: string
  items: NavItem[]
}

export const workspaces: { id: Workspace; label: string; home: string }[] = [
  { id: 'clinical', label: '臨床', home: '/clinical' },
  { id: 'research', label: '研究', home: '/research' },
]

export const navigation: Record<Workspace, NavGroup[]> = {
  clinical: [
    {
      items: [
        { to: '/clinical', label: '首頁', icon: Home, end: true },
        { to: '/clinical/worklist', label: '工作清單', icon: ListChecks },
        { to: '/clinical/acquisition', label: '影像接收', icon: MonitorSmartphone },
        { to: '/clinical/patients', label: '病人與檢查', icon: Users },
        { to: '/clinical/reports', label: '報告中心', icon: FileText },
      ],
    },
  ],
  research: [
    {
      title: '資料',
      items: [
        { to: '/research', label: '總覽', icon: LayoutDashboard, end: true },
        { to: '/research/datasets', label: '資料集', icon: Database },
        { to: '/research/annotation', label: '標註與回饋', icon: PenTool },
      ],
    },
    {
      title: 'eGFR 預測',
      items: [
        { to: '/research/egfr', label: 'eGFR 訓練', icon: BrainCircuit, end: true },
        { to: '/research/egfr/compare', label: 'eGFR 比較', icon: GitCompare },
        { to: '/research/egfr/models', label: 'eGFR 模型', icon: Boxes },
      ],
    },
    {
      title: '分割',
      items: [
        { to: '/research/segmentation', label: '分割訓練', icon: Activity, end: true },
        { to: '/research/segmentation/mask-sets', label: '遮罩組', icon: Layers3 },
        { to: '/research/segmentation/models', label: '分割模型', icon: Boxes },
      ],
    },
    {
      title: '回音分級',
      items: [
        { to: '/research/grading', label: '回音分級訓練', icon: FlaskConical, end: true },
        { to: '/research/features', label: '特徵擷取', icon: Layers },
        { to: '/research/grading/models', label: '回音分級模型', icon: Boxes },
      ],
    },
    {
      title: '流程與分析',
      items: [
        { to: '/research/pipelines', label: '流程執行', icon: Workflow },
        { to: '/research/preprocessing', label: '影像處理與遮罩', icon: ScanLine },
        { to: '/research/analysis', label: 'AI 分析', icon: Sparkles },
      ],
    },
  ],
}

export const footerNavigation: NavItem[] = [
  { to: '/jobs', label: '任務紀錄', icon: History },
  { to: '/trash', label: '回收桶', icon: Trash2 },
  { to: '/settings', label: '設定', icon: Settings },
]

export const workspaceFor = (pathname: string): Workspace | null => {
  if (pathname.startsWith('/clinical')) return 'clinical'
  if (pathname.startsWith('/research')) return 'research'
  return null
}
