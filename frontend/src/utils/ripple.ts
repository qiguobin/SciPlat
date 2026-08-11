/** 全局点击波纹微反馈：button / 可点击卡片 / 统计栏触发 */
export function initRipple(): void {
  document.addEventListener('pointerdown', (e) => {
    const target = e.target as HTMLElement
    const el = target.closest('button, .hover-lift, .stat-col, .ant-card') as HTMLElement | null
    if (!el || el.classList.contains('no-ripple')) return
    const rect = el.getBoundingClientRect()
    const size = Math.max(rect.width, rect.height)
    const r = document.createElement('span')
    r.className = 'ripple'
    r.style.width = r.style.height = `${size}px`
    r.style.left = `${e.clientX - rect.left - size / 2}px`
    r.style.top = `${e.clientY - rect.top - size / 2}px`
    el.appendChild(r)
    setTimeout(() => r.remove(), 700)
  })
}
