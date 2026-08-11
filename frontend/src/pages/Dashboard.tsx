import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Checkbox, Col, Empty, List, Modal, Progress, Row, Select, Space, Statistic, Tag, Typography, message,
} from 'antd'
import {
  BookOutlined, CalendarOutlined,
  DatabaseOutlined, DownOutlined, EditOutlined, FileTextOutlined, FolderOpenOutlined,
  RadarChartOutlined, RightOutlined, TrophyOutlined,
} from '@ant-design/icons'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtSize } from '../utils'
import EChart from '../components/EChart'
import ProfileCard from '../components/ProfileCard'
import CountUp from '../components/CountUp'
import { PAPER_STATUS, ProjectStatusTag } from '../components/StatusTag'
import type { Paper, Project, Stats, Todo, WritingLog } from '../types'

/* ---------- 12 列固定网格卡片配置 ---------- */
interface DashCardConfig {
  key: string
  visible: boolean
  col: number
  row: number
  w: number
  h: number
  collapsed: boolean
}
const LAYOUT_KEY = 'sciplat-dash-layout-v3'

function defaultCards(): DashCardConfig[] {
  // 12 列固定布局（行高 120px）：学生卡 / 统计条通栏置顶，其余卡片 6 列宽 × 3 行高
  // 位置与尺寸完全固定（不可拖拽/缩放），布局弹窗仅控制显示与折叠 —— 杜绝重叠
  const defs: [string, number, number, number, number, boolean][] = [
    ['profile', 1, 1, 12, 1, true],
    ['stats', 1, 2, 12, 1, true],
    ['quickTasks', 1, 3, 6, 3, true], ['recentProjects', 7, 3, 6, 3, true],
    ['progressSummary', 1, 6, 6, 3, true], ['charts', 7, 6, 6, 3, true],
    ['activity', 1, 9, 6, 3, true], ['trend', 7, 9, 6, 3, true],
    ['tracking', 1, 12, 6, 3, true], ['recent', 7, 12, 6, 3, true],
    ['week', 1, 15, 6, 3, false], ['projectPie', 7, 15, 6, 3, false],
    ['deadlines', 1, 18, 6, 3, false], ['reading', 7, 18, 6, 3, false],
    ['todayQueue', 1, 21, 6, 3, false],
  ]
  return defs.map(([key, col, row, w, h, visible]) => ({ key, visible, col, row, w, h, collapsed: false }))
}

function loadLayout(): DashCardConfig[] {
  // v3：只持久化 visible / collapsed，位置尺寸永远以默认布局为准（旧坐标迁移逻辑整体移除）
  try {
    const raw = localStorage.getItem(LAYOUT_KEY)
    const saved = raw ? JSON.parse(raw) : {}
    return defaultCards().map((c) => ({
      ...c,
      visible: typeof saved[c.key]?.visible === 'boolean' ? saved[c.key].visible : c.visible,
      collapsed: typeof saved[c.key]?.collapsed === 'boolean' ? saved[c.key].collapsed : c.collapsed,
    }))
  } catch {
    return defaultCards()
  }
}

const CARD_LABELS: Record<string, string> = {
  profile: '学生信息卡', stats: '统计条', deadlines: '截止提醒', activity: '科研动态',
  week: '本周进展与写作', charts: '论文状态分布', trend: '写作趋势', projectPie: '项目状态分布',
  recent: '最近更新', reading: '阅读热榜', todayQueue: '今日待读', tracking: '科研动态追踪',
  recentProjects: '近期项目', quickTasks: '快速继续', progressSummary: '科研进度汇总',
}

const KIND_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  project: { label: '项目', color: '#38BDF8', icon: <FolderOpenOutlined /> },
  paper: { label: '论文', color: '#34D399', icon: <FileTextOutlined /> },
  material: { label: '材料', color: '#A78BFA', icon: <DatabaseOutlined /> },
  reference: { label: '文献', color: '#FBBF24', icon: <BookOutlined /> },
}

function StatCol({ label, value, suffix, hint, onClick }: {
  label: string; value: number; suffix?: string; hint?: string; onClick?: () => void
}) {
  return (
    <div className="stat-col" onClick={onClick}>
      <div className="stat-label">{label}</div>
      <div className="stat-value"><CountUp value={value} />{suffix && <span className="stat-suffix">{suffix}</span>}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

interface PhaseOverview { project_id: number; done: number; total: number; current: string }
const PRIO_ORDER: Record<string, number> = { 高: 0, 中: 1, 低: 2 }

export default function Dashboard() {
  const nav = useNavigate()
  const [stats, setStats] = useState<Stats | null>(null)
  const [activity, setActivity] = useState<Todo[]>([])
  const [writing, setWriting] = useState<WritingLog[]>([])
  const [readingTop, setReadingTop] = useState<{ id: number; title: string; minutes: number }[]>([])
  const [todayQueue, setTodayQueue] = useState<{ id: number; title: string }[]>([])
  const [weekSummary, setWeekSummary] = useState<{ stats: { todos_done: number; experiments: number; refs_added: number; writing_total: number } } | null>(null)
  const [writingTrend, setWritingTrend] = useState<{ date: string; words: number }[]>([])
  const [cards, setCards] = useState<DashCardConfig[]>(loadLayout)
  const [layoutOpen, setLayoutOpen] = useState(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [phases, setPhases] = useState<PhaseOverview[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [papers, setPapers] = useState<Paper[]>([])
  const [milestonesMap, setMilestonesMap] = useState<Record<number, { title: string; due_date: string }[]>>({})
  const [tracking, setTracking] = useState<{
    active_sources: number; week_new: number
    recent: { id: number; title: string; link: string; published: string | null; is_new: boolean; source_id: number }[]
    sourceNames: Record<number, string>
  }>({ active_sources: 0, week_new: 0, recent: [], sourceNames: {} })
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  useEffect(() => {
    api.get<Stats>('/stats').then((r) => setStats(r.data)).catch(() => {})
    api.get<Todo[]>('/todos/activity', { params: { days: 7 } }).then((r) => setActivity(r.data)).catch(() => {})
    const today = new Date().toISOString().slice(0, 10)
    api.get<WritingLog[]>('/writing-logs', { params: { start: today, end: today } })
      .then((r) => setWriting(r.data)).catch(() => {})
    api.get<{ stats: { todos_done: number; experiments: number; refs_added: number; writing_total: number } }>(
      '/schedule/summary', { params: { period: 'week' } },
    ).then((r) => setWeekSummary(r.data)).catch(() => {})
    const start14 = new Date(); start14.setDate(start14.getDate() - 13)
    api.get<WritingLog[]>('/writing-logs', {
      params: { start: start14.toISOString().slice(0, 10), end: new Date(Date.now() + 86400000).toISOString().slice(0, 10) },
    }).then((r) => {
      const byDay = new Map<string, number>()
      r.data.forEach((w) => byDay.set(w.date, (byDay.get(w.date) ?? 0) + w.word_count))
      const days: { date: string; words: number }[] = []
      for (let i = 13; i >= 0; i--) {
        const d = new Date(); d.setDate(d.getDate() - i)
        const key = d.toISOString().slice(0, 10)
        days.push({ date: key.slice(5), words: byDay.get(key) ?? 0 })
      }
      setWritingTrend(days)
    }).catch(() => {})
    api.get<{ id: number; title: string; queue_date: string | null }[]>('/references/queue')
      .then((r) => setTodayQueue(r.data.filter((x) => !x.queue_date || x.queue_date <= today).slice(0, 6)))
      .catch(() => {})
    Promise.all([
      api.get<{ minutes: Record<string, number> }>('/references/reading-stats'),
      api.get<{ id: number; title: string }[]>('/references'),
    ]).then(([st, refs]) => {
      const minutes = st.data.minutes
      setReadingTop(refs.data
        .filter((r) => (minutes[r.id] ?? 0) > 0)
        .sort((a, b) => (minutes[b.id] ?? 0) - (minutes[a.id] ?? 0))
        .slice(0, 5)
        .map((r) => ({ id: r.id, title: r.title, minutes: minutes[r.id] ?? 0 })))
    }).catch(() => {})
    api.get<Project[]>('/projects').then((r) => {
      setProjects(r.data)
      // 科研进度汇总：拉取进行中项目的里程碑节点
      const running = r.data.filter((p) => p.status === '进行中').slice(0, 3)
      if (running.length > 0) {
        Promise.all(running.map((p) => api.get<{ milestones: { title: string; due_date: string }[] }>(`/projects/${p.id}`)))
          .then((res) => {
            const m: Record<number, { title: string; due_date: string }[]> = {}
            running.forEach((p, i) => {
              m[p.id] = (res[i].data.milestones ?? [])
                .sort((a, b) => a.due_date.localeCompare(b.due_date))
                .slice(0, 2)
            })
            setMilestonesMap(m)
          }).catch(() => {})
      }
    }).catch(() => {})
    api.get<{ project_id: number; done: number; total: number; phases: { name: string; status: string }[] }[]>('/schedule/phases')
      .then((r) => setPhases(r.data.map((p) => ({
        project_id: p.project_id, done: p.done, total: p.total,
        current: p.phases.find((ph) => ph.status === '进行中')?.name ?? '',
      })))).catch(() => {})
    api.get<Todo[]>('/todos').then((r) => setTodos(r.data)).catch(() => {})
    api.get<Paper[]>('/papers').then((r) => setPapers(r.data)).catch(() => {})
    api.get<{
      active_sources: number; week_new: number
      recent: { id: number; title: string; link: string; published: string | null; is_new: boolean; source_id: number }[]
    }>('/tracking/overview').then((r) => {
      setTracking((prev) => ({ ...prev, ...r.data }))
      api.get<{ id: number; name: string }[]>('/tracking/sources')
        .then((src) => {
          const names: Record<number, string> = {}
          src.data.forEach((s) => { names[s.id] = s.name })
          setTracking((prev) => ({ ...prev, sourceNames: names }))
        }).catch(() => {})
    }).catch(() => {})
  }, [refreshKey])

  /* ---------- 布局操作（仅 visible / collapsed） ---------- */
  const saveCards = (next: DashCardConfig[]) => {
    setCards(next)
    try {
      const saved: Record<string, { visible: boolean; collapsed: boolean }> = {}
      next.forEach((c) => { saved[c.key] = { visible: c.visible, collapsed: c.collapsed } })
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(saved))
    } catch { /* ignore */ }
  }
  const updateCard = (key: string, patch: Partial<DashCardConfig>) => {
    saveCards(cards.map((c) => (c.key === key ? { ...c, ...patch } : c)))
  }

  const resetLayout = () => {
    localStorage.removeItem(LAYOUT_KEY)
    setCards(defaultCards())
    message.success('布局已重置为默认')
  }

  /* ---------- 图表 ---------- */
  const paperOption = useMemo<EChartsOption>(() => {
    if (!stats) return {} as EChartsOption
    const names = Object.keys(PAPER_STATUS)
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { left: 36, right: 10, top: 18, bottom: 40 },
      xAxis: { type: 'category' as const, data: names.map((n) => PAPER_STATUS[n].label),
        axisLabel: { interval: 0, rotate: 30, fontSize: 9, color: '#94a3b8' },
        axisLine: { lineStyle: { color: '#1E293B' } }, axisTick: { show: false } },
      yAxis: { type: 'value' as const, minInterval: 1, splitLine: { lineStyle: { color: '#16233A' } },
        axisLabel: { color: '#64748b', fontSize: 9 } },
      series: [{ type: 'bar' as const, data: names.map((n) => stats.papers.by_status[n] ?? 0),
        itemStyle: { color: '#34D399', borderRadius: [3, 3, 0, 0], shadowColor: 'rgba(52,211,153,0.4)', shadowBlur: 6 },
        barMaxWidth: 18, animationDuration: 800 }],
    }
  }, [stats])

  const projectOption = useMemo<EChartsOption>(() => {
    if (!stats) return {} as EChartsOption
    return {
      tooltip: { trigger: 'item' as const },
      legend: { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 10 } },
      color: ['#34D399', '#38BDF8', '#A78BFA', '#FBBF24', '#64748B'],
      series: [{ type: 'pie' as const, radius: ['42%', '66%'], center: ['50%', '42%'],
        data: Object.entries(stats.projects.by_status).map(([name, value]) => ({ name, value })),
        label: { formatter: '{b} {c}', color: '#94a3b8', fontSize: 10 },
        itemStyle: { borderColor: '#0F172A', borderWidth: 2 } }],
    }
  }, [stats])

  const writingOption = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' as const },
    grid: { left: 36, right: 10, top: 14, bottom: 22 },
    xAxis: { type: 'category' as const, data: writingTrend.map((d) => d.date),
      axisLabel: { color: '#64748b', fontSize: 9, interval: 1 },
      axisLine: { lineStyle: { color: '#1E293B' } }, axisTick: { show: false } },
    yAxis: { type: 'value' as const, splitLine: { lineStyle: { color: '#16233A' } },
      axisLabel: { color: '#64748b', fontSize: 9 } },
    series: [{ type: 'line' as const, data: writingTrend.map((d) => d.words), smooth: true,
      symbol: 'circle', symbolSize: 4,
      lineStyle: { color: '#34D399', width: 2, shadowColor: 'rgba(52,211,153,0.5)', shadowBlur: 8 },
      itemStyle: { color: '#34D399' },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: 'rgba(52,211,153,0.3)' }, { offset: 1, color: 'rgba(52,211,153,0.02)' }] } },
      animationDuration: 1000 }],
  }), [writingTrend])

  if (!stats) return <Card loading />

  const paperStatus = stats.papers.by_status
  const phaseMap = new Map(phases.map((p) => [p.project_id, p]))
  const todoByProject = (pid: number | null) => todos.filter((t) => t.project_id === pid)
  // 快速继续：所有未完成任务（待办 + 进行中），按优先级排序（新建待办默认为「待办」状态）
  const inProgress = todos.filter((t) => t.status !== '已完成')
    .sort((a, b) => (PRIO_ORDER[a.priority] ?? 1) - (PRIO_ORDER[b.priority] ?? 1))
  const highPriority = todos.filter((t) => t.priority === '高' && t.status !== '已完成')
  const activePapers = papers.filter((p) => !['Accepted', 'Published'].includes(p.status))

  /* ---------- 卡片渲染 ---------- */
  const renderCard = (key: string) => {
    switch (key) {
      case 'profile': return <ProfileCard />
      case 'stats': return (
        <Card size="small" bodyStyle={{ padding: 0 }}>
          <div className="stat-strip">
            <StatCol label="科研项目" value={stats.projects.total} hint={`${stats.projects.by_status['进行中'] ?? 0} 进行中`} onClick={() => nav('/projects')} />
            <StatCol label="论文" value={stats.papers.total} hint={`${paperStatus['Under Review'] ?? 0} 审稿中`} onClick={() => nav('/papers')} />
            <StatCol label="文献" value={stats.references.total} hint={`${stats.references.read['已读'] ?? 0} 已读`} onClick={() => nav('/references')} />
            <StatCol label="材料" value={stats.materials.total} suffix={stats.materials.total_size ? `/ ${fmtSize(stats.materials.total_size)}` : ''} onClick={() => nav('/materials')} />
          </div>
        </Card>
      )
      case 'recentProjects': {
        const recent = [...projects].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 4)
        return (
          <Card size="small" title={<span className="section-title">近期项目</span>}>
            {recent.length === 0 ? <Empty description="暂无项目" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
              <List size="small" dataSource={recent} renderItem={(p) => {
                const ph = phaseMap.get(p.id)
                return (
                  <List.Item onClick={() => nav(`/projects/${p.id}`)} style={{ cursor: 'pointer', paddingInline: 2 }}>
                    <Space direction="vertical" size={1} style={{ width: '100%' }}>
                      <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</span>
                        <ProjectStatusTag status={p.status} />
                      </Space>
                      {ph && ph.total > 0 && (
                        <Progress percent={Math.round((ph.done / ph.total) * 100)} size="small" strokeColor="#34D399" style={{ margin: 0 }} />
                      )}
                    </Space>
                  </List.Item>
                )
              }} />
            )}
          </Card>
        )
      }
      case 'quickTasks': {
        const top3 = inProgress.slice(0, 3)
        return (
          <Card size="small" title={<span className="section-title">快速继续</span>}>
            {top3.length === 0 ? <Empty description="暂无进行中任务" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
              <List size="small" dataSource={top3} renderItem={(t) => (
                <List.Item style={{ paddingInline: 2 }} actions={[
                  <Checkbox key="c" onChange={(e) => {
                    api.patch(`/todos/${t.id}/status`, { status: e.target.checked ? '已完成' : '进行中' }).then(() => bump())
                  }} />,
                ]}>
                  <Space size={4} style={{ minWidth: 0 }}>
                    <Tag color={t.priority === '高' ? 'red' : t.priority === '中' ? 'orange' : 'default'} style={{ fontSize: 10 }}>{t.priority}</Tag>
                    <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
                  </Space>
                </List.Item>
              )} />
            )}
          </Card>
        )
      }
      case 'progressSummary': {
        const running = projects.filter((p) => p.status === '进行中')
        return (
          <Card size="small" title={<span className="section-title">科研进度汇总</span>}>
            <List size="small" split={false}>
              {highPriority.length > 0 && (
                <List.Item style={{ paddingInline: 2 }}>
                  <Space wrap size={4}>
                    <Tag color="red">高优待办</Tag>
                    {highPriority.slice(0, 3).map((t) => (
                      <Tag key={t.id} color="red" style={{ cursor: 'pointer' }} onClick={() => api.patch(`/todos/${t.id}/status`, { status: '已完成' }).then(() => bump())}>
                        {t.title}
                      </Tag>
                    ))}
                  </Space>
                </List.Item>
              )}
              {running.slice(0, 3).map((p) => {
                const ph = phaseMap.get(p.id)
                const ptodos = todoByProject(p.id)
                const current = ptodos.find((t) => t.status === '进行中')
                const next = ptodos.filter((t) => t.status === '待办').sort((a, b) => a.date.localeCompare(b.date))[0]
                const ms = milestonesMap[p.id] ?? []
                const pct = ph && ph.total > 0 ? Math.round((ph.done / ph.total) * 100) : 0
                return (
                  <List.Item key={p.id} style={{ paddingInline: 2 }}>
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{p.title}</span>
                        <Tag color="blue" style={{ fontSize: 10 }}>{ph?.current || '阶段准备'}</Tag>
                      </Space>
                      <Progress percent={pct} size="small" strokeColor="#34D399" style={{ margin: 0 }} />
                      {ms.length > 0 && (
                        <Space size={6} wrap style={{ fontSize: 11 }}>
                          {ms.map((m) => (
                            <Tag key={m.title} style={{ fontSize: 10 }}>
                              🎯 {m.title} · {m.due_date}
                            </Tag>
                          ))}
                        </Space>
                      )}
                      <Space size={8} wrap style={{ fontSize: 12 }}>
                        {current && <Tag color="orange" style={{ fontSize: 11 }}>当前：{current.title}</Tag>}
                        {next && <Tag color="green" style={{ fontSize: 11 }}>下一步：{next.title}</Tag>}
                      </Space>
                    </Space>
                  </List.Item>
                )
              })}
              {activePapers.slice(0, 3).map((p) => (
                <List.Item key={p.id} style={{ paddingInline: 2 }} onClick={() => nav(`/papers/${p.id}`)}>
                  <Space size={6} style={{ minWidth: 0 }}>
                    <Tag color={PAPER_STATUS[p.status]?.color} style={{ fontSize: 10, flexShrink: 0 }}>
                      {PAPER_STATUS[p.status]?.label}
                    </Tag>
                    <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</span>
                  </Space>
                </List.Item>
              ))}
            </List>
          </Card>
        )
      }
      case 'deadlines': return stats.deadlines.length > 0 ? (
        <Card size="small" title={<span className="section-title"><CalendarOutlined style={{ color: '#fbbf24', marginRight: 6 }} />截止提醒</span>}>
          <List size="small" dataSource={stats.deadlines.slice(0, 5)} renderItem={(d) => (
            <List.Item onClick={() => nav(d.link)} style={{ cursor: 'pointer', paddingInline: 2 }}>
              <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                <Tag color={d.days_left <= 7 ? 'red' : 'orange'} style={{ fontSize: 10 }}>
                  {d.days_left < 0 ? `超时 ${-d.days_left}天` : d.days_left === 0 ? '今天' : `${d.days_left}天`}
                </Tag>
                {d.title}
              </span>
            </List.Item>
          )} />
        </Card>
      ) : null
      case 'activity': return (
        <Card size="small" title={<span className="section-title">科研动态</span>}>
          {activity.length === 0 ? <Empty description="暂无动态" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
            <List size="small" dataSource={activity.slice(0, 5)} renderItem={(t) => (
              <List.Item style={{ paddingInline: 2 }}>
                <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <Tag color={t.status === '已完成' ? 'green' : 'default'} style={{ fontSize: 10 }}>{t.status === '已完成' ? '完成' : '新增'}</Tag>
                  {t.title}
                </span>
              </List.Item>
            )} />
          )}
        </Card>
      )
      case 'week': return (
        <Card size="small" title={<span className="section-title">本周进展</span>} onClick={() => nav('/schedule')} hoverable>
          <Row gutter={4}>
            <Col span={6}><Statistic title="完成" value={weekSummary?.stats.todos_done ?? 0} /></Col>
            <Col span={6}><Statistic title="实验" value={weekSummary?.stats.experiments ?? 0} /></Col>
            <Col span={6}><Statistic title="文献" value={weekSummary?.stats.refs_added ?? 0} /></Col>
            <Col span={6}><Statistic title="字数" value={weekSummary?.stats.writing_total ?? 0} /></Col>
          </Row>
        </Card>
      )
      case 'charts': return (
        <Card size="small" title={<span className="section-title">论文状态</span>}><EChart option={paperOption} height={150} /></Card>
      )
      case 'trend': return (
        <Card size="small" title={<span className="section-title">写作趋势</span>}><EChart option={writingOption} height={150} /></Card>
      )
      case 'projectPie': return (
        <Card size="small" title={<span className="section-title">项目分布</span>}><EChart option={projectOption} height={150} /></Card>
      )
      case 'tracking': return (
        <Card size="small" title={
          <span className="section-title"><RadarChartOutlined style={{ color: '#34D399', marginRight: 6 }} />科研追踪
            <Tag color="green" style={{ marginLeft: 6 }}>{tracking.active_sources}</Tag></span>
        } extra={<Button size="small" type="link" onClick={() => nav('/tracking')}>管理 →</Button>}>
          {tracking.recent.length === 0 ? <Empty description="暂无条目" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
            <List size="small" dataSource={tracking.recent.slice(0, 4)} renderItem={(item) => (
              <List.Item style={{ paddingInline: 2, cursor: 'pointer' }} onClick={() => item.link && window.open(item.link, '_blank')}>
                <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.is_new && <Tag color="#FF005C" style={{ color: '#fff', borderColor: '#FF005C', fontSize: 10 }}>新</Tag>}
                  {tracking.sourceNames[item.source_id] && <Tag style={{ fontSize: 9 }}>{tracking.sourceNames[item.source_id].slice(0, 12)}</Tag>}
                  {item.title}
                </span>
                <Button size="small" type="link" style={{ fontSize: 11, flexShrink: 0 }} onClick={(e) => {
                  e.stopPropagation()
                  api.post(`/tracking/items/${item.id}/to-library`).then(() => { message.success('已入库'); bump() })
                }}>入库</Button>
              </List.Item>
            )} />
          )}
        </Card>
      )
      case 'recent': return (
        <Card size="small" title={<span className="section-title">最近更新</span>}>
          {stats.recent.length === 0 ? <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
            <List size="small" dataSource={stats.recent.slice(0, 5)} renderItem={(item) => {
              const meta = KIND_META[item.kind] ?? { label: item.kind, color: '#64748b', icon: null }
              const link = item.kind === 'project' ? `/projects/${item.id}` : item.kind === 'paper' ? `/papers/${item.id}` : `/${item.kind === 'material' ? 'materials' : 'references'}`
              return (
                <List.Item onClick={() => nav(link)} style={{ cursor: 'pointer', paddingInline: 2 }}>
                  <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <Tag style={{ fontSize: 10 }}>{meta.label}</Tag>{item.title}
                  </span>
                </List.Item>
              )
            }} />
          )}
        </Card>
      )
      case 'reading': return readingTop.length > 0 ? (
        <Card size="small" title={<span className="section-title">阅读热榜</span>}>
          <List size="small" dataSource={readingTop} renderItem={(item, i) => (
            <List.Item style={{ paddingInline: 2 }}>
              <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                <Tag style={{ fontSize: 10 }}>{i + 1}</Tag>{item.title}
              </span>
            </List.Item>
          )} />
        </Card>
      ) : null
      case 'todayQueue': return todayQueue.length > 0 ? (
        <Card size="small" title={<span className="section-title">今日待读</span>}>
          <List size="small" dataSource={todayQueue} renderItem={(item) => (
            <List.Item onClick={() => nav('/references')} style={{ cursor: 'pointer', paddingInline: 2 }}>
              <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</span>
            </List.Item>
          )} />
        </Card>
      ) : null
      default: return null
    }
  }

  return (
    <div>
      {/* 顶栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          12 列固定网格 · 卡片位置与尺寸固定 · 布局弹窗可开关/折叠
        </Typography.Text>
        <Space>
          <Button size="small" icon={<TrophyOutlined />} onClick={() => {
            const now = new Date()
            api.get<{ markdown: string; label: string }>('/schedule/term-report', {
              params: { year: now.getFullYear(), semester: now.getMonth() < 6 ? 1 : 2 },
            }).then((r) => {
              navigator.clipboard.writeText(r.data.markdown)
              message.success(`已复制 ${r.data.label} 学期总结`)
            }).catch(() => message.error('生成失败'))
          }}>学期总结</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setLayoutOpen(true)}>布局</Button>
        </Space>
      </div>

      {/* 12 列固定网格 */}
      <div className="dash-grid-3">
        {cards.filter((c) => c.visible).map((c) => {
          const content = renderCard(c.key)
          if (!content) return null
          return (
            <div
              key={c.key}
              className={`dash-cell ${c.collapsed ? 'collapsed' : ''}`}
              style={{ gridColumn: `${c.col} / span ${c.w}`, gridRow: `${c.row} / span ${c.h}` }}
            >
              {content}
              <span
                className="dash-collapse-btn" style={{ position: 'absolute', top: 8, right: 28, zIndex: 6 }}
                onClick={() => updateCard(c.key, { collapsed: !c.collapsed })} title={c.collapsed ? '展开' : '折叠'}>
                {c.collapsed ? <DownOutlined /> : <RightOutlined />}
              </span>
            </div>
          )
        })}
      </div>

      {/* 布局设置弹窗：仅显示 / 折叠 */}
      <Modal title="仪表盘布局" open={layoutOpen} onCancel={() => setLayoutOpen(false)}
        footer={<Space><Button danger onClick={resetLayout}>重置为默认</Button><Button type="primary" onClick={() => setLayoutOpen(false)}>完成</Button></Space>}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          卡片位置与尺寸固定（学生信息 / 统计条通栏置顶，其余卡片 6 列宽 × 3 行高），此处仅控制显示 / 隐藏与折叠。
        </Typography.Paragraph>
        <List dataSource={cards} renderItem={(c) => (
          <List.Item actions={[
            <Button key="f" size="small" icon={c.collapsed ? <DownOutlined /> : <RightOutlined />}
              onClick={() => updateCard(c.key, { collapsed: !c.collapsed })}>
              {c.collapsed ? '展开' : '折叠'}
            </Button>,
            <Checkbox key="v" checked={c.visible} onChange={(e) => updateCard(c.key, { visible: e.target.checked })}>
              显示
            </Checkbox>,
          ]}>
            <span style={{ fontWeight: 600, color: c.visible ? undefined : '#64748B' }}>
              {CARD_LABELS[c.key] ?? c.key}
              <Tag style={{ marginLeft: 6, fontSize: 10, fontFamily: 'var(--mono)' }}>{c.w}×{c.h}</Tag>
            </span>
          </List.Item>
        )} />
      </Modal>
    </div>
  )
}
