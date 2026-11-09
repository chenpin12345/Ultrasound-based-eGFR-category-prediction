import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronLeft, ChevronRight, PenTool, X } from 'lucide-react'
import { api, imageUrl } from '../../api/client'
import { useAction, useApi } from '../../api/hooks'
import type { ImageInfo } from '../../api/types'
import { draftSourceLabel, type DraftItem } from '../../api/ml'
import type { Shape } from '../../components/AnnotationCanvas'
import { ImageWithMask } from '../../components/MaskOverlay'
import { Button, EmptyState, KeyValue, Panel, Pill, inputClass } from '../../components/ui'
import { ErrorNote, Loading } from '../../components/live'
import { useOperator } from '../../auth/operator'

const REJECT_REASONS = ['腎臟邊界錯誤', '腎竇分割錯誤', '肝／脾取錯區域', '不是腎臟長軸', '影像品質太差']
const labeledName: Record<string, string> = { kidney: '整顆腎', parenchyma: '腎實質', sinus: '腎竇', liver: '肝', spleen: '脾' }

/** 草稿確認：一次看一張，A 接受、R 退回、E 修改、←／→ 切換。 */
export default function DraftReview() {
  const { operator } = useOperator()
  const [onlyNeeded, setOnlyNeeded] = useState(false)
  const queue = useApi<{ total: number; items: DraftItem[] }>(`/annotation/drafts/queue?only_needed=${onlyNeeded}&limit=500`, [onlyNeeded])
  const [index, setIndex] = useState(0)
  const items = queue.data?.items ?? []
  const item = items[Math.min(index, Math.max(0, items.length - 1))]
  const image = useApi<ImageInfo>(item ? `/images/${item.image_id}` : null, [item?.image_id])
  const masks = useApi<{ latest: { shapes: Omit<Shape, 'id'>[] } | null }>(item ? `/annotation/masks/${item.image_id}` : null, [item?.mask_id])
  const [reason, setReason] = useState(REJECT_REASONS[0])
  const decide = useAction((id: number, decision: 'accept' | 'reject') => api.post(`/annotation/drafts/${id}/decision`, { decision, reason: decision === 'reject' ? reason : '' }))

  const act = useCallback(
    async (decision: 'accept' | 'reject') => {
      if (!item || decide.busy) return
      if (await decide.run(item.mask_id, decision)) await queue.reload() // 決定後這張離開佇列，同一位置顯示下一張
    },
    [item, decide, queue],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || e.ctrlKey || e.metaKey) return
      if (e.key === 'a' || e.key === 'A') void act('accept')
      else if (e.key === 'r' || e.key === 'R') void act('reject')
      else if (e.key === 'ArrowRight') setIndex((i) => Math.min(i + 1, items.length - 1))
      else if (e.key === 'ArrowLeft') setIndex((i) => Math.max(i - 1, 0))
      else if ((e.key === 'e' || e.key === 'E') && item) window.location.assign(`/research/annotation/mask?image=${item.image_id}`)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [act, items.length, item])

  if (queue.loading && !queue.data) return <Loading />
  const shapes = (masks.data?.latest?.shapes ?? []).map((s, i) => ({ ...s, id: i + 1 })) as Shape[]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-[14px] text-ink-soft">
          待確認 {queue.data?.total ?? 0} 張。接受＝這份草稿可以用（測試集需要）；修改會開啟標註編輯器並存成人工版本。
        </p>
        <label className="ml-auto inline-flex items-center gap-2 text-[14px]">
          <input type="checkbox" className="accent-steel" checked={onlyNeeded} onChange={(e) => { setOnlyNeeded(e.target.checked); setIndex(0) }} />
          只看「需要確認」的
        </label>
      </div>
      {!operator && <p className="text-[13px] text-amber">請先在右上角選擇操作者，確認紀錄才知道是誰確認的。</p>}
      <ErrorNote error={queue.error ?? decide.error} />
      {!item ? (
        <EmptyState icon={Check} title="沒有待確認的草稿" body="到「影像處理與遮罩 › 遮罩草稿」產生草稿，或所有草稿都確認完了。" />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <Panel flush>
            {image.data ? <ImageWithMask src={imageUrl(item.image_id, 'model')} width={image.data.width} height={image.data.height} shapes={shapes} /> : <Loading />}
          </Panel>
          <Panel title={`${Math.min(index, items.length - 1) + 1}／${items.length}・${item.image_id}`}>
            <KeyValue
              items={[
                ['來源', draftSourceLabel[item.source] ?? item.source],
                ['狀態', item.review === 'needed' ? '需要確認' : '自動檢查通過'],
                ['和舊遮罩重疊（IoU）', item.iou_vs_legacy == null ? '—' : item.iou_vs_legacy.toFixed(2)],
                ['已標結構', item.labeled.map((l) => labeledName[l] ?? l).join('、') || '—'],
                ['側別', image.data?.side === 'right' ? '右腎' : image.data?.side === 'left' ? '左腎' : '未知'],
              ]}
            />
            {item.reasons.length > 0 && (
              <ul className="mt-3 space-y-1 text-[13px] text-amber">
                {item.reasons.map((r) => (
                  <li key={r}>・{r}</li>
                ))}
              </ul>
            )}
            <div className="mt-4 grid grid-cols-2 gap-2">
              <Button variant="primary" icon={Check} disabled={decide.busy || !operator} onClick={() => void act('accept')}>
                接受（A）
              </Button>
              <Link to={`/research/annotation/mask?image=${item.image_id}`} className="inline-flex items-center justify-center gap-1.5 rounded-md border border-line px-3 py-2 text-[14px] hover:bg-paper">
                <PenTool className="h-4 w-4" aria-hidden />
                修改（E）
              </Link>
            </div>
            <div className="mt-3 flex gap-2">
              <select className={`${inputClass} min-w-0 flex-1`} value={reason} onChange={(e) => setReason(e.target.value)} aria-label="退回原因">
                {REJECT_REASONS.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <Button icon={X} disabled={decide.busy || !operator} onClick={() => void act('reject')}>
                退回（R）
              </Button>
            </div>
            <div className="mt-4 flex justify-between">
              <Button icon={ChevronLeft} disabled={index === 0} onClick={() => setIndex(index - 1)}>
                上一張
              </Button>
              <Pill>{item.review === 'needed' ? '需要確認' : '通過'}</Pill>
              <Button disabled={index >= items.length - 1} onClick={() => setIndex(index + 1)}>
                下一張
                <ChevronRight className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          </Panel>
        </div>
      )}
    </div>
  )
}
