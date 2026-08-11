import type { CSSProperties, ReactNode } from 'react'

/** 入场编排容器：页面内卡片按 --i 变量 stagger 入场（60ms 步进，上限 600ms） */
export default function Reveal({
  children,
  index = 0,
  style,
  className = '',
}: {
  children: ReactNode
  index?: number
  style?: CSSProperties
  className?: string
}) {
  return (
    <div
      className={`reveal-item ${className}`}
      style={{ ['--i' as string]: Math.min(index, 10), ...style } as CSSProperties}
    >
      {children}
    </div>
  )
}
