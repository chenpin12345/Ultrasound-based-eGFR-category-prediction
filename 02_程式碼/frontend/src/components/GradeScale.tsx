export type Grade = 0 | 1 | 2 | 3

/** 回音分級：每一級用它代表的灰階亮度呈現，讓「越白越高級」一眼可見。 */
export const grades: { grade: Grade; label: string; fill: string; text: string }[] = [
  { grade: 0, label: '比參考器官黑', fill: '#2B2F31', text: '#F3F5F2' },
  { grade: 1, label: '與參考器官相近', fill: '#6E7376', text: '#FFFFFF' },
  { grade: 2, label: '比參考器官白', fill: '#B3B8BA', text: '#1B2A38' },
  { grade: 3, label: '明顯變白，接近腎竇', fill: '#ECEEEE', text: '#1B2A38' },
]

export function GradeChip({ grade, size = 'md' }: { grade: Grade; size?: 'sm' | 'md' }) {
  const g = grades[grade]
  const dim = size === 'sm' ? 'h-6 min-w-6 text-[12px]' : 'h-8 min-w-8 text-[14px]'
  return (
    <span
      className={`inline-flex items-center justify-center rounded border border-ink/15 px-1.5 font-bold ${dim}`}
      style={{ background: g.fill, color: g.text }}
      title={`Grade ${grade}：${g.label}`}
    >
      {grade}
    </span>
  )
}

export function GradeScale({
  probabilities,
  selected,
  confirmed = false,
  onSelect,
}: {
  probabilities?: number[]
  selected?: Grade
  confirmed?: boolean
  onSelect?: (grade: Grade) => void
}) {
  return (
    <div className="grid grid-cols-4 gap-1.5" role="radiogroup" aria-label="回音分級">
      {grades.map((g) => {
        const isSelected = selected === g.grade
        const p = probabilities?.[g.grade]
        return (
          <button
            key={g.grade}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onSelect?.(g.grade)}
            className={`flex flex-col overflow-hidden rounded-md border text-left transition-shadow ${
              isSelected ? (confirmed ? 'border-ink ring-2 ring-ink' : 'border-amber ring-2 ring-amber') : 'border-line hover:border-ink-faint'
            }`}
          >
            <span className="flex h-12 items-end px-2 pb-1 text-[18px] font-bold" style={{ background: g.fill, color: g.text }}>
              {g.grade}
            </span>
            <span className="bg-white px-2 py-1.5">
              <span className="block text-[12px] leading-snug text-ink-soft">{g.label}</span>
              {p !== undefined && (
                <span className="mt-1 block">
                  <span className="block h-1 rounded-full bg-paper-deep">
                    <span className="block h-1 rounded-full bg-ink-soft" style={{ width: `${Math.round(p * 100)}%` }} />
                  </span>
                  <span className="mt-0.5 block text-[12px] text-ink-faint">{Math.round(p * 100)}%</span>
                </span>
              )}
            </span>
          </button>
        )
      })}
    </div>
  )
}
