import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import App from './App'
import { initRipple } from './utils/ripple'
import { initCursorGlow } from './utils/cursorGlow'
import { useAppStore, type ThemeMode } from './store'
import './index.css'

dayjs.locale('zh-cn')

const FONT_SANS =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif"
const FONT_MONO = "'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace"

// 深空霓虹（默认）
const darkTheme = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    colorPrimary: '#34D399',
    colorInfo: '#34D399',
    colorLink: '#34D399',
    colorSuccess: '#34D399',
    colorBgLayout: '#0B1120',
    colorBgContainer: '#0F172A',
    colorBgElevated: '#111C33',
    colorBorder: '#1E293B',
    colorBorderSecondary: '#16233A',
    colorText: '#E2E8F0',
    colorTextSecondary: '#94A3B8',
    colorTextTertiary: '#64748B',
    colorTextLightSolid: '#0B1120',
    borderRadius: 8,
    fontFamily: FONT_SANS,
    fontFamilyCode: FONT_MONO,
  },
  components: {
    Layout: { headerBg: 'rgba(11, 17, 32, 0.55)', siderBg: 'rgba(11, 17, 32, 0.45)' },
    Menu: {
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(52, 211, 153, 0.14)',
      darkItemColor: 'rgba(148, 163, 184, 0.85)',
      darkItemHoverColor: '#E2E8F0',
      itemBorderRadius: 8,
    },
    Card: { colorBgContainer: 'rgba(15, 23, 42, 0.72)' },
    Table: { headerBg: 'rgba(17, 28, 51, 0.8)', headerColor: '#94A3B8', borderColor: '#1E293B' },
    Modal: { contentBg: '#0F172A', headerBg: '#0F172A' },
    Tooltip: { colorBgSpotlight: '#111C33' },
  },
}

// 亮纸墨蓝（浅色）
const lightTheme = {
  token: {
    colorPrimary: '#1e3a5f',
    colorInfo: '#1e3a5f',
    colorLink: '#1e3a5f',
    colorBgLayout: '#f6f7f4',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: '#e4e7ec',
    colorBorderSecondary: '#e6e9f2',
    colorText: '#202a3a',
    colorTextSecondary: '#4a5568',
    colorTextTertiary: '#8a94a3',
    colorTextLightSolid: '#ffffff',
    borderRadius: 8,
    fontFamily: FONT_SANS,
    fontFamilyCode: FONT_MONO,
  },
  components: {
    Layout: { headerBg: 'rgba(255, 255, 255, 0.7)', siderBg: 'rgba(255, 255, 255, 0.6)' },
    Menu: {
      darkItemBg: 'transparent',
      darkSubMenuItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(30, 58, 95, 0.1)',
      darkItemColor: 'rgba(74, 85, 104, 0.85)',
      darkItemHoverColor: '#202a3a',
      itemBorderRadius: 8,
    },
    Table: { headerBg: '#f4f5f1', headerColor: '#4a5568', borderColor: '#e4e7ec' },
    Modal: { contentBg: '#ffffff', headerBg: '#ffffff' },
    Tooltip: { colorBgSpotlight: '#1f2937' },
  },
}

// 初始化主题 dataset（供 CSS 变量切换）
document.documentElement.dataset.theme = useAppStore.getState().theme

initRipple()
initCursorGlow()

function Root() {
  const theme = useAppStore((s) => s.theme)
  return (
    <ConfigProvider locale={zhCN} theme={theme === 'dark' ? darkTheme : lightTheme}>
      <App />
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)

export type { ThemeMode }
