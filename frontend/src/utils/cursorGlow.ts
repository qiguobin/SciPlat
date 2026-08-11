/** 按钮光晕跟随：鼠标悬停时以指针为中心的光晕，随移动变化（事件委托 + rAF 节流） */
export function initCursorGlow(): void {
  let current: HTMLElement | null = null
  let raf = 0

  const apply = (el: HTMLElement, x: number, y: number) => {
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--gx', `${((x - rect.left) / rect.width) * 100}%`)
    el.style.setProperty('--gy', `${((y - rect.top) / rect.height) * 100}%`)
  }

  const onMove = (e: MouseEvent) => {
    const target = e.target as HTMLElement
    const el = target.closest('button, .hover-lift, .stat-col, .ant-card') as HTMLElement | null
    if (raf) return
    raf = window.requestAnimationFrame(() => {
      raf = 0
      if (el && el !== current) {
        if (current) current.classList.remove('cursor-glow')
        current = el
        el.classList.add('cursor-glow')
      }
      if (el && current === el) apply(el, e.clientX, e.clientY)
    })
  }

  const onLeave = () => {
    if (current) {
      current.classList.remove('cursor-glow')
      current = null
    }
  }

  document.addEventListener('pointermove', onMove, { passive: true })
  document.addEventListener('pointerleave', onLeave)
}
