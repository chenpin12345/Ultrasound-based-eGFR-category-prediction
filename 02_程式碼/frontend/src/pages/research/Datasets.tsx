import { useSearchParams } from 'react-router-dom'
import { PageHeader, Tabs } from '../../components/ui'
import ImportTab from './datasets/ImportTab'
import ImagesTab from './datasets/ImagesTab'
import PatientsTab from './datasets/PatientsTab'
import SplitsTab from './datasets/SplitsTab'
import { BatchesTab, VersionsTab } from './datasets/VersionsTab'

type Tab = 'import' | 'images' | 'patients' | 'splits' | 'versions' | 'batches'
const TABS: { id: Tab; label: string }[] = [
  { id: 'import', label: '匯入' },
  { id: 'images', label: '影像瀏覽' },
  { id: 'patients', label: '病人對照' },
  { id: 'splits', label: '資料切分' },
  { id: 'versions', label: '資料集版本' },
  { id: 'batches', label: '匯入紀錄' },
]

export default function Datasets() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? ''
  const requested = params.get('tab') as Tab | null
  const tab: Tab = requested && TABS.some((t) => t.id === requested) ? requested : 'images'

  return (
    <>
      <PageHeader title="資料集" description="匯入、影像、病人對照、資料切分與版本都在這裡。原始影像只讀不改；系統內只使用去識別化後的影像。" />
      <Tabs label="資料集內容" value={tab} onChange={(t) => setParams({ tab: t })} tabs={TABS} />
      {tab === 'import' && <ImportTab />}
      {tab === 'images' && <ImagesTab key={params.get('patient') ?? ''} initialStatus={status} patient={params.get('patient') ?? ''} />}
      {tab === 'patients' && <PatientsTab />}
      {tab === 'splits' && <SplitsTab />}
      {tab === 'versions' && <VersionsTab />}
      {tab === 'batches' && <BatchesTab />}
    </>
  )
}
