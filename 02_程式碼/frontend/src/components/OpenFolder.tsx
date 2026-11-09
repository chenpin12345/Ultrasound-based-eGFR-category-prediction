import { FolderOpen } from 'lucide-react'
import { api } from '../api/client'
import { useAction } from '../api/hooks'
import { Button } from './ui'

/** 在檔案總管開啟資料夾（後端只允許專案內、非受限區）。 */
export function OpenFolderButton({ kind, id = '', label = '開啟資料夾' }: { kind: string; id?: string; label?: string }) {
  const open = useAction(() => api.post<{ path: string }>('/system/open-folder', { kind, id }))
  return (
    <span className="inline-flex flex-col">
      <Button variant="secondary" icon={FolderOpen} disabled={open.busy} onClick={() => void open.run()} title="在檔案總管開啟">
        {label}
      </Button>
      {open.error && <span className="mt-1 text-[12px] text-alert">{open.error.message}</span>}
    </span>
  )
}
