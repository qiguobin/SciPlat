import { useEffect, useState } from 'react'
import { Button, Input, Layout, Menu } from 'antd'
import {
  ApartmentOutlined,
  BookOutlined,
  BulbOutlined,
  CalendarOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  GlobalOutlined,
  PartitionOutlined,
  ProjectOutlined,
  RadarChartOutlined,
  SettingOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import QuickAdd from './QuickAdd'
import DataManager from './DataManager'
import NotificationCenter from './NotificationCenter'
import LlmSettings from './LlmSettings'
import StatusBar from './StatusBar'
import UpdateChecker from './UpdateChecker'
import { useAppStore } from '../store'

const MENU_GROUPS = [
  {
    key: 'research',
    label: '科研',
    type: 'group' as const,
    children: [
      { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
      { key: '/island', icon: <GlobalOutlined />, label: '科研岛' },
      { key: '/projects', icon: <FolderOpenOutlined />, label: '项目管理' },
      { key: '/papers', icon: <FileTextOutlined />, label: '论文管理' },
      { key: '/materials', icon: <DatabaseOutlined />, label: '科研材料',
        children: [
          { key: '/materials/list', label: '材料列表' },
          { key: '/materials/resources', label: '资源库存' },
        ] },
      { key: '/references', icon: <BookOutlined />, label: '文献库',
        children: [
          { key: '/references/list', label: '文献列表' },
          { key: '/references/network', label: '关联图谱' },
          { key: '/references/queue', label: '阅读队列' },
        ] },
    ],
  },
  {
    key: 'schedule',
    label: '日程',
    type: 'group' as const,
    children: [
      { key: '/schedule', icon: <CalendarOutlined />, label: '日程管理',
        children: [
          { key: '/schedule/calendar', label: '日历待办' },
          { key: '/schedule/kanban', label: '全局看板' },
          { key: '/schedule/meetings', label: '组会记录' },
        ] },
      { key: '/timeline', icon: <PartitionOutlined />, label: '全局时间线' },
      { key: '/ideas', icon: <BulbOutlined />, label: '灵感收集' },
    ],
  },
  {
    key: 'research2',
    label: '可视化',
    type: 'group' as const,
    children: [
      { key: '/canvas', icon: <ProjectOutlined />, label: '科研画布' },
      { key: '/tracking', icon: <RadarChartOutlined />, label: '科研追踪' },
    ],
  },
  {
    key: 'output',
    label: '成果',
    type: 'group' as const,
    children: [
      { key: '/achievements', icon: <TrophyOutlined />, label: '成果管理',
        children: [
          { key: '/achievements/list', label: '成果列表' },
          { key: '/achievements/timeline', label: '成果时间线' },
        ] },
    ],
  },
]

const PAGE_TITLES: Record<string, string> = {
  '/': '仪表盘',
  '/island': '科研岛',
  '/projects': '项目管理',
  '/papers': '论文管理',
  '/materials': '科研材料',
  '/references': '文献库',
  '/schedule': '日程管理',
  '/timeline': '全局时间线',
  '/ideas': '灵感收集',
  '/achievements': '成果管理',
  '/canvas': '科研画布',
  '/tracking': '科研追踪',
  '/search': '全局搜索',
}

export default function AppLayout() {
  const nav = useNavigate()
  const loc = useLocation()
  const [q, setQ] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [dataOpen, setDataOpen] = useState(false)
  const [llmOpen, setLlmOpen] = useState(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const theme = useAppStore((s) => s.theme)
  const toggleTheme = useAppStore((s) => s.toggleTheme)
  const root = '/' + (loc.pathname.split('/')[1] || '')
  const title = PAGE_TITLES[root] ?? 'SciPlat'
  // 二级菜单：选中当前路径，展开父级
  const [openKeys, setOpenKeys] = useState<string[]>(['/references', '/schedule', '/achievements'])

  // 微距视差：背景光晕跟随鼠标（--mx/--my 驱动，rAF 节流）
  useEffect(() => {
    let raf = 0
    const onMove = (e: MouseEvent) => {
      if (raf) return
      raf = window.requestAnimationFrame(() => {
        document.documentElement.style.setProperty('--mx', String(e.clientX / window.innerWidth))
        document.documentElement.style.setProperty('--my', String(e.clientY / window.innerHeight))
        raf = 0
      })
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => {
      window.removeEventListener('mousemove', onMove)
      if (raf) window.cancelAnimationFrame(raf)
    }
  }, [])

  // 启动自动检测更新：发现新版且当日未提示过 → 自动弹出（强制更新必弹）
  useEffect(() => {
    const KEY = 'sciplat-update-notified'
    api.get<{ has_update: boolean; mandatory: boolean }>('/update/check')
      .then((r) => {
        if (!r.data.has_update) return
        if (!r.data.mandatory && localStorage.getItem(KEY) === new Date().toDateString()) return
        if (!r.data.mandatory) localStorage.setItem(KEY, new Date().toDateString())
        setUpdateOpen(true)
      })
      .catch(() => { /* 网络不可达静默 */ })
  }, [])

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 受控折叠侧边栏：汉堡按钮切换同一侧边栏的收起/展开，不产生第二个侧边栏 */}
      <Layout.Sider
        theme="dark"
        width={232}
        className="app-sider"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        breakpoint="lg"
        collapsedWidth={0}
      >
        {!collapsed && (
          <>
            <div className="brand">
              <div className="seal">研</div>
              <div>
                <div className="brand-name">SciPlat</div>
                <div className="brand-sub">博士生科研管理平台</div>
              </div>
            </div>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={[root]}
              items={MENU_GROUPS}
              onClick={({ key }) => nav(key)}
              style={{ borderInlineEnd: 'none' }}
            />
            <div className="sider-footer">数据存储于本机</div>
            {/* 装饰主义：极淡 Bézier 曲线底纹（工艺美术精致感，5% 透明度） */}
            <svg className="sider-ornament" viewBox="0 0 232 160" fill="none" preserveAspectRatio="none" aria-hidden="true">
              <path d="M-20 140 C 60 100, 120 160, 252 90" stroke="rgba(148,163,184,0.5)" strokeWidth="1" />
              <path d="M-20 155 C 80 125, 140 175, 252 115" stroke="rgba(148,163,184,0.35)" strokeWidth="1" />
              <path d="M-20 170 C 100 150, 160 190, 252 140" stroke="rgba(52,211,153,0.4)" strokeWidth="0.8" />
              <circle cx="60" cy="118" r="1.5" fill="rgba(148,163,184,0.5)" />
              <circle cx="150" cy="152" r="1.5" fill="rgba(148,163,184,0.5)" />
              <circle cx="196" cy="112" r="1.2" fill="rgba(52,211,153,0.5)" />
            </svg>
          </>
        )}
      </Layout.Sider>

      <Layout>
        <Layout.Header className="app-header" style={{ height: 56, lineHeight: '56px' }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            title={collapsed ? '展开侧边栏' : '收起侧边栏'}
            onClick={() => setCollapsed((v) => !v)}
          />
          <div className="page-title">{title}</div>
          <Input.Search
            placeholder="全局搜索：项目 / 论文 / 材料 / 文献"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onSearch={(v) => v.trim() && nav(`/search?q=${encodeURIComponent(v.trim())}`)}
            style={{ maxWidth: 420, marginLeft: 'auto' }}
            allowClear
          />
          <Button type="text" icon={<SettingOutlined />} title="AI 设置（LLM）" onClick={() => setLlmOpen(true)} />
          <NotificationCenter />
          <Button type="text" icon={<DatabaseOutlined />} title="数据管理（备份/恢复）" onClick={() => setDataOpen(true)} />
          <Button
            type="text"
            title={theme === 'dark' ? '切换到亮色主题' : '切换到深空主题'}
            onClick={toggleTheme}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </Button>
        </Layout.Header>
        <Layout.Content className="app-content">
          <div className="page-wrap">
            {/* key=pathname 触发路由转场动画 */}
            <div key={loc.pathname} className="page-enter">
              <Outlet />
            </div>
          </div>
        </Layout.Content>
        {/* 底部状态栏：数据库 / 版本 / LLM / 错误监控 / 检查更新 */}
        <StatusBar
          onOpenData={() => setDataOpen(true)}
          onOpenLlm={() => setLlmOpen(true)}
          onOpenUpdate={() => setUpdateOpen(true)}
        />
      </Layout>

      <QuickAdd />
      <LlmSettings open={llmOpen} onClose={() => setLlmOpen(false)} />
      <DataManager open={dataOpen} onClose={() => setDataOpen(false)} />
      <UpdateChecker open={updateOpen} onClose={() => setUpdateOpen(false)} />
    </Layout>
  )
}
