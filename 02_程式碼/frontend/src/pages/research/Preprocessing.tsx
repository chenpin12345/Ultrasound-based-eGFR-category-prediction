import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { imageUrl } from '../../api/client'
import { useApi } from '../../api/hooks'
import type { ImageInfo, Template } from '../../api/types'
import { EmptyState, PageHeader, Panel, Table, Tabs } from '../../components/ui'
import { ImageGrid } from '../../components/ImageGrid'
import { ErrorNote, Loading } from '../../components/live'
import MaskDrafts from './MaskDrafts'

type Tab = 'layout' | 'deid' | 'masks'

const regions = [
  { name: '上方標頭', content: '病歷號、姓名、年齡、性別、日期、醫院', action: '讀出年齡與性別後遮蓋（原文立即丟棄）' },
  { name: '右側參數', content: '探頭、頻率、增益、DR', action: '讀出存成掃描參數後遮蓋' },
  { name: '左側', content: '深度尺、聚焦標記、灰階條', action: '換算每像素 mm 後遮蓋' },
  { name: '掃描區內', content: 'caliper 十字與虛線', action: '模型用影像修補；灰階計算用影像標為無效' },
  { name: '左下', content: 'Dist A／Dist B 量測值', action: '讀出腎長參考值後遮蓋' },
  { name: '右下', content: '人體示意圖、側別文字、影格編號', action: '判斷左右側後遮蓋' },
]

export default function Preprocessing() {
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(window.location.search).get('tab') as Tab) || 'layout')
  const templates = useApi<{ templates: Template[] }>('/templates')
  const residual = useApi<{ total: number; images: ImageInfo[] }>(tab === 'deid' ? '/images?status=pending_review&limit=60' : null, [tab])

  return (
    <>
      <PageHeader title="影像處理與遮罩" description="匯入時依機型版面遮蓋影像上的文字與標記；遮罩草稿用舊程式遮罩、MedSAM 與規則產生，再由人工確認。" />
      <Tabs
        label="處理內容"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'layout', label: '版面範本' },
          { id: 'deid', label: '去識別化檢查' },
          { id: 'masks', label: '遮罩草稿' },
        ]}
      />
      {tab === 'layout' && (
        <div className="space-y-5">
          <Panel title="版面範本（每種尺寸一份）" flush>
            <ErrorNote error={templates.error} />
            {templates.loading && !templates.data ? (
              <Loading />
            ) : (
              <Table
                head={['範本', '機型', '尺寸', '已匯入影像', '版本', '最後修改', '']}
                rows={(templates.data?.templates ?? []).map((t) => [
                  t.id,
                  t.machine,
                  `${t.width} × ${t.height}`,
                  t.images ?? 0,
                  `第 ${t.version} 版`,
                  `${t.updated_by}・${t.updated_at.slice(0, 10)}`,
                  <Link key="e" to={`/research/preprocessing/templates/${t.id}`} className="text-steel hover:underline">
                    編輯範本
                  </Link>,
                ])}
              />
            )}
          </Panel>
          <Panel title="影像上要處理的區域" flush>
            <Table minWidth={680} head={['區域', '內容', '處理方式']} rows={regions.map((r) => [r.name, r.content, r.action])} />
          </Panel>
          <p className="text-[13px] text-ink-faint">修改範本只影響之後匯入的影像。舊系統的固定裁切（只適用 Canon 1600×1200）不再使用。</p>
        </div>
      )}
      {tab === 'deid' && (
        <div className="space-y-4">
          <p className="text-[14px] text-ink-soft">
            匯入時會在去識別化後的影像再跑一次 OCR，出現個資格式的文字、讀不到深度尺或年齡的影像列在這裡。請逐張打開確認後設為可用或排除。
          </p>
          <ErrorNote error={residual.error} />
          {residual.loading && !residual.data ? (
            <Loading />
          ) : residual.data && residual.data.total ? (
            <>
              <ImageGrid
                items={residual.data.images.map((i) => ({
                  id: i.id,
                  to: `/research/datasets/images/${i.id}`,
                  src: imageUrl(i.id, 'thumb'),
                  caption: i.id,
                  sub: i.review_reasons.join('；'),
                  flag: i.deid_check === 'residual' ? '文字殘留' : undefined,
                }))}
              />
              <p className="text-[13px] text-ink-faint">共 {residual.data.total} 張待確認。</p>
            </>
          ) : (
            <EmptyState icon={ShieldCheck} title="沒有待確認的影像" body="匯入後如果有去識別化殘留或讀不到欄位的影像，會出現在這裡。" />
          )}
        </div>
      )}
      {tab === 'masks' && <MaskDrafts />}
    </>
  )
}
