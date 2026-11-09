import { Link } from 'react-router-dom'

export interface GridItem {
  id: string
  to?: string
  caption: string
  sub?: string
  flag?: string
  selected?: boolean
  /** 去識別化縮圖的網址；沒有時用示意方塊。 */
  src?: string
}

/** 影像縮圖格。介面預覽階段不載入真實影像，縮圖以深色方塊代替。 */
export function ImageGrid({ items, onToggle }: { items: GridItem[]; onToggle?: (id: string) => void }) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
      {items.map((item) => {
        const body = (
          <>
            <span className="relative block aspect-[5/4] bg-viewer">
              {item.src ? (
                <img src={item.src} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-contain" />
              ) : (
                <svg viewBox="0 0 100 80" className="absolute inset-0 h-full w-full" aria-hidden>
                  <path d="M38 6 Q50 3 62 6 L94 74 Q50 82 6 74 Z" fill="#3A4044" />
                  <ellipse cx="54" cy="46" rx="26" ry="12" transform="rotate(-12 54 46)" fill="#4A5155" />
                  <ellipse cx="54" cy="46" rx="14" ry="4" transform="rotate(-12 54 46)" fill="#8D9497" />
                </svg>
              )}
              {item.flag && <span className="absolute left-1.5 top-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">{item.flag}</span>}
            </span>
            <span className="block px-2 py-1.5">
              <span className="block truncate text-[13px] font-medium">{item.caption}</span>
              {item.sub && <span className="block truncate text-[12px] text-ink-faint">{item.sub}</span>}
            </span>
          </>
        )
        const cls = `block overflow-hidden rounded-md border bg-white text-left ${item.selected ? 'border-steel ring-2 ring-steel' : 'border-line hover:border-ink-faint'}`
        return (
          <li key={item.id}>
            {onToggle ? (
              <button type="button" className={`w-full ${cls}`} aria-pressed={item.selected} onClick={() => onToggle(item.id)}>
                {body}
              </button>
            ) : item.to ? (
              <Link to={item.to} className={cls}>
                {body}
              </Link>
            ) : (
              <div className={cls}>{body}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
