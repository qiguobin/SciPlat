import { useMemo } from 'react'
import type { HeatmapData } from '../types'

const LEVELS = ['#1E293B', '#134E4A', '#0F766E', '#34D399', '#A7F3D0']
const DAY_LABELS = ['一', '三', '五']

/** GitHub 风格科研活跃热力图（自绘 div 网格，无第三方依赖） */
export default function Heatmap({ data, title }: { data: HeatmapData; title?: string }) {
  const { cells, weeks } = useMemo(() => {
    const byDate = new Map(data.days.map((d) => [d.date, d.count]))
    const start = new Date(data.year, 0, 1)
    const end = new Date(data.year, 11, 31)
    // 对齐到周一开始
    const offset = (start.getDay() + 6) % 7
    type Cell = { date: string; count: number; level: number }
    const grid: Cell[] = []
    const cur = new Date(start)
    for (let i = 0; i < offset; i++) {
      grid.push({ date: '', count: 0, level: 0 })
    }
    while (cur <= end) {
      const iso = cur.toISOString().slice(0, 10)
      const count = byDate.get(iso) ?? 0
      const level = count === 0 ? 0 : count >= 8 ? 4 : count >= 5 ? 3 : count >= 2 ? 2 : 1
      grid.push({ date: iso, count, level })
      cur.setDate(cur.getDate() + 1)
    }
    const weekCount = Math.ceil(grid.length / 7)
    const weeksArr: Cell[][] = []
    for (let w = 0; w < weekCount; w++) {
      weeksArr.push(grid.slice(w * 7, (w + 1) * 7))
    }
    return { cells: grid, weeks: weeksArr }
  }, [data])

  if (weeks.length === 0) return null

  return (
    <div>
      {title && <div style={{ fontSize: 13, fontWeight: 600, color: '#202a3a', marginBottom: 8 }}>{title}</div>}
      <div style={{ display: 'flex', gap: 3, overflowX: 'auto' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginRight: 4 }}>
          {DAY_LABELS.map((l) => (
            <span key={l} style={{ height: 10, fontSize: 9, color: '#8a94a3', lineHeight: '10px' }}>{l}</span>
          ))}
        </div>
        {weeks.map((week, wi) => (
          <div key={wi} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {week.map((c, di) => (
              <div
                key={di}
                title={c.date ? `${c.date}：${c.count} 次科研活动` : ''}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: c.date ? LEVELS[c.level] : 'transparent',
                }}
              />
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 8, fontSize: 11, color: '#8a94a3' }}>
        少
        {LEVELS.map((c) => (
          <span key={c} style={{ width: 10, height: 10, borderRadius: 2, background: c, display: 'inline-block' }} />
        ))}
        多
        <span style={{ marginLeft: 'auto' }}>{data.year} 年</span>
      </div>
    </div>
  )
}
