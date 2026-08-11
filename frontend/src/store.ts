import { create } from 'zustand'

export type ThemeMode = 'dark' | 'light'

interface AppState {
  /** 全局刷新计数：任一页面发生数据变更后 bump，驱动相关页面重新拉取 */
  refreshKey: number
  bump: () => void
  /** 主题模式（localStorage 记忆，默认深空） */
  theme: ThemeMode
  toggleTheme: () => void
}

const THEME_KEY = 'sciplat-theme'

function initialTheme(): ThemeMode {
  try {
    return (localStorage.getItem(THEME_KEY) as ThemeMode) || 'dark'
  } catch {
    return 'dark'
  }
}

export const useAppStore = create<AppState>((set) => ({
  refreshKey: 0,
  bump: () => set((s) => ({ refreshKey: s.refreshKey + 1 })),
  theme: initialTheme(),
  toggleTheme: () => set((s) => {
    const next: ThemeMode = s.theme === 'dark' ? 'light' : 'dark'
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch { /* ignore */ }
    document.documentElement.dataset.theme = next
    return { theme: next }
  }),
}))
