import { useState } from 'react'
import { Download } from 'lucide-react'
import { api } from '../api/client'
import { useAction, useApi } from '../api/hooks'
import { Button, Panel, Pill } from './ui'
import { ErrorNote, JobProgress } from './live'

interface Weight {
  name: string
  label: string
  license: string
  size: string
  use: string
  downloaded: { downloaded_at: string } | null
}

/** 預訓練權重（D2）：ImageNet 與 MedSAM。eGFR、分割、回音分級的訓練頁共用。 */
export function PretrainedPanel() {
  const weights = useApi<{ weights: Weight[] }>('/pretrained')
  const [downloadJob, setDownloadJob] = useState<string | null>(null)
  const download = useAction((name: string) => api.post<{ job_id: string }>(`/pretrained/${name}/download`))
  return (
    <Panel title="預訓練權重">
            <ul className="space-y-3">
              {weights.data?.weights.map((w) => (
                <li key={w.name} className="text-[14px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{w.label}</span>
                    {w.downloaded ? (
                      <Pill tone="ok">已下載</Pill>
                    ) : (
                      <Button
                        icon={Download}
                        disabled={download.busy || Boolean(downloadJob)}
                        onClick={async () => {
                          const r = await download.run(w.name)
                          if (r) setDownloadJob(r.job_id)
                        }}
                      >
                        下載
                      </Button>
                    )}
                  </div>
                  <p className="text-[12px] text-ink-faint">
                    {w.size}・{w.license}・{w.use}
                  </p>
                </li>
              ))}
            </ul>
            <ErrorNote error={download.error ?? weights.error} />
            {downloadJob && (
              <div className="mt-3">
                <JobProgress
                  jobId={downloadJob}
                  onDone={() => {
                    setDownloadJob(null)
                    void weights.reload()
                  }}
                />
              </div>
            )}
            <p className="mt-3 text-[12px] text-ink-faint">只下載一次，存在 04_模型\04_預訓練權重，之後離線使用。影像不會上傳。</p>
    </Panel>
  )
}

export function useWeights() {
  return useApi<{ weights: Weight[] }>('/pretrained')
}
