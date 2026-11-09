import { useId } from 'react'

export interface OverlayState {
  kidney: boolean
  sinus: boolean
  reference: boolean
  lesion?: boolean
}

/**
 * 腎臟長軸切面的示意圖。介面預覽階段不顯示真實影像（原圖上方燒有病人個資）。
 */
export function UltrasoundSketch({
  side = 'right',
  overlays = { kidney: true, sinus: true, reference: true },
  caption = true,
}: {
  side?: 'right' | 'left'
  overlays?: OverlayState
  caption?: boolean
}) {
  const id = useId().replace(/:/g, '')
  const reference = side === 'right' ? '肝臟' : '脾臟'
  return (
    <figure className="relative overflow-hidden rounded-md bg-viewer">
      <svg viewBox="0 0 640 460" className="block h-auto w-full" role="img" aria-label={`${side === 'right' ? '右' : '左'}腎長軸示意圖`}>
        <defs>
          <radialGradient id={`tissue-${id}`} cx="50%" cy="0%" r="100%">
            <stop offset="0%" stopColor="#5B6266" />
            <stop offset="55%" stopColor="#3A4044" />
            <stop offset="100%" stopColor="#1C2225" />
          </radialGradient>
          <filter id={`speckle-${id}`}>
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" />
            <feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.22 0" />
          </filter>
          <clipPath id={`sector-${id}`}>
            <path d="M250 40 Q320 22 390 40 L600 420 Q320 470 40 420 Z" />
          </clipPath>
        </defs>

        <g clipPath={`url(#sector-${id})`}>
          <rect width="640" height="460" fill={`url(#tissue-${id})`} />
          {/* 參考器官：較亮的實質 */}
          <path d="M40 120 Q200 90 320 130 Q300 190 200 205 Q110 215 40 230 Z" fill="#6A7175" opacity="0.9" />
          {/* 腎臟：皮質 */}
          <ellipse cx="350" cy="275" rx="190" ry="88" transform="rotate(-12 350 275)" fill="#3F4548" />
          {/* 髓質錐體 */}
          {[0, 1, 2, 3, 4].map((i) => (
            <ellipse key={i} cx={235 + i * 58} cy={300 - i * 13 + (i % 2 ? -34 : 34)} rx="20" ry="14" fill="#2E3336" />
          ))}
          {/* 腎竇：最亮 */}
          <ellipse cx="352" cy="273" rx="110" ry="30" transform="rotate(-12 352 273)" fill="#9EA4A6" />
          <rect width="640" height="460" filter={`url(#speckle-${id})`} />
        </g>

        {overlays.reference && (
          <g>
            <rect x="150" y="150" width="46" height="34" fill="none" stroke="#E0B455" strokeWidth="2" strokeDasharray="5 4" />
            <text x="150" y="143" fill="#E0B455" fontSize="15">{reference} ROI</text>
          </g>
        )}
        {overlays.kidney && (
          <ellipse cx="350" cy="275" rx="190" ry="88" transform="rotate(-12 350 275)" fill="none" stroke="#5EC4D6" strokeWidth="2.5" />
        )}
        {overlays.sinus && (
          <ellipse cx="352" cy="273" rx="110" ry="30" transform="rotate(-12 352 273)" fill="none" stroke="#C792EA" strokeWidth="2" />
        )}
        {overlays.lesion && (
          <g>
            <circle cx="478" cy="232" r="16" fill="#15191B" />
            <circle cx="478" cy="232" r="22" fill="none" stroke="#E06C5A" strokeWidth="2" strokeDasharray="5 3" />
            <text x="504" y="214" fill="#E06C5A" fontSize="14">疑似囊腫</text>
          </g>
        )}

        {/* 深度尺 */}
        <g fill="#8C9599" fontSize="13">
          {[0, 5, 10].map((d, i) => (
            <text key={d} x="14" y={52 + i * 160}>
              {d}
            </text>
          ))}
        </g>
        <text x="620" y="446" fill="#8C9599" fontSize="14" textAnchor="end">
          {side === 'right' ? 'R-Kidney' : 'L-Kidney'}
        </text>
      </svg>
      {caption && (
        <figcaption className="absolute left-3 top-3 rounded bg-black/50 px-2 py-0.5 text-[12px] text-white/80">示意圖，非真實影像</figcaption>
      )}
    </figure>
  )
}
