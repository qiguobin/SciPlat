import { useEffect, useMemo, useState } from 'react'
import {
  Badge, Button, Calendar, Card, Checkbox, Col, Empty, Form, Input, List, message,
  Modal, Popconfirm, Progress, Row, Select, Space, Statistic, Tabs, Tag, Typography,
} from 'antd'
import {
  CheckOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, PlusOutlined, RobotOutlined, SendOutlined,
} from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import ReactMarkdown from 'react-markdown'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime } from '../utils'
import type { AdvisorMeeting, SchedulePhaseOverview, ScheduleSummary, Todo } from '../types'
import ProjectKanban from '../components/ProjectKanban'
import GroupMeetingsPanel from '../components/GroupMeetingsPanel'
import EChart from '../components/EChart'

const TODO_STATUS_COLORS: Record<string, string> = { 待办: 'default', 进行中: 'blue', 已完成: 'green' }
const PRIORITY_COLORS: Record<string, string> = { 高: 'red', 中: 'orange', 低: 'default' }
const PHASE_STATUS_COLORS: Record<string, string> = { 未开始: 'default', 进行中: 'blue', 已完成: 'green', 延期: 'red' }

export default function Schedule() {
  const nav = useNavigate()
  const { sub = 'calendar' } = useParams()
  const [selected, setSelected] = useState<Dayjs>(dayjs())
  const [todos, setTodos] = useState<Todo[]>([])
  const [monthTodos, setMonthTodos] = useState<Todo[]>([])
  const [projects, setProjects] = useState<{ id: number; title: string }[]>([])
  const [summary, setSummary] = useState<ScheduleSummary | null>(null)
  const [phases, setPhases] = useState<SchedulePhaseOverview[]>([])
  const [heatmap, setHeatmap] = useState<{ year: number; days: { date: string; count: number }[] } | null>(null)
  const [todoModal, setTodoModal] = useState(false)
  const [editing, setEditing] = useState<Todo | null>(null)
  const [todoForm] = Form.useForm()
  const [reportOpen, setReportOpen] = useState(false)
  const [report, setReport] = useState<ScheduleSummary | null>(null)
  const [reportPeriod, setReportPeriod] = useState<'week' | 'month'>('week')
  const [reportAiLoading, setReportAiLoading] = useState<'week' | 'month' | null>(null)
  const [meetings, setMeetings] = useState<AdvisorMeeting[]>([])
  const [meetingModal, setMeetingModal] = useState(false)
  const [editingMeeting, setEditingMeeting] = useState<AdvisorMeeting | null>(null)
  const [meetingForm] = Form.useForm()
  const [todoRates, setTodoRates] = useState<Record<number, { done: number; total: number; rate: number }>>({})
  const [burndown, setBurndown] = useState<{ date: string; label: string; remaining: number; done: number }[]>([])
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const loadDay = () => {
    api.get<Todo[]>('/todos', { params: { date: selected.format('YYYY-MM-DD') } })
      .then((r) => setTodos(r.data)).catch(() => {})
  }

  const loadAll = () => {
    const monthStart = selected.startOf('month').format('YYYY-MM-DD')
    const monthEnd = selected.add(1, 'month').startOf('month').format('YYYY-MM-DD')
    api.get<Todo[]>('/todos', { params: { start: monthStart, end: monthEnd } })
      .then((r) => setMonthTodos(r.data)).catch(() => {})
    api.get<ScheduleSummary>('/schedule/summary', { params: { period: 'week' } })
      .then((r) => setSummary(r.data)).catch(() => {})
    api.get<SchedulePhaseOverview[]>('/schedule/phases')
      .then((r) => {
        setPhases(r.data)
        // 每个项目的待办完成率
        Promise.all(r.data.map((p) => api.get<{ done: number; total: number; rate: number }>('/todos/stats', { params: { project_id: p.project_id } })))
          .then((results) => {
            const m: Record<number, { done: number; total: number; rate: number }> = {}
            r.data.forEach((p, i) => { m[p.project_id] = results[i].data })
            setTodoRates(m)
          })
          .catch(() => {})
      })
      .catch(() => {})
    api.get<{ year: number; days: { date: string; count: number }[] }>('/schedule/heatmap')
      .then((r) => setHeatmap(r.data)).catch(() => {})
    api.get<AdvisorMeeting[]>('/advisor-meetings')
      .then((r) => setMeetings(r.data)).catch(() => {})
    api.get<{ days: { date: string; label: string; remaining: number; done: number }[] }>('/schedule/burndown')
      .then((r) => setBurndown(r.data.days)).catch(() => {})
    api.get<{ id: number; title: string }[]>('/projects')
      .then((r) => setProjects(r.data)).catch(() => {})
  }
  useEffect(() => { loadAll() }, [selected, refreshKey])
  useEffect(loadDay, [selected, refreshKey])

  const dayCounts = useMemo(() => {
    const m = new Map<string, number>()
    monthTodos.forEach((t) => m.set(t.date, (m.get(t.date) ?? 0) + 1))
    return m
  }, [monthTodos])

  const openTodoModal = (t?: Todo) => {
    setEditing(t ?? null)
    todoForm.setFieldsValue(t
      ? { title: t.title, date: t.date, priority: t.priority, status: t.status, project_id: t.project_id ?? undefined, repeat: t.repeat, description: t.description }
      : { date: selected.format('YYYY-MM-DD'), priority: '中', status: '待办', repeat: 'none' })
    setTodoModal(true)
  }

  const saveTodo = () => {
    todoForm.validateFields().then((v) => {
      const req = editing ? api.put(`/todos/${editing.id}`, v) : api.post('/todos', v)
      req.then(() => {
        message.success('已保存')
        setTodoModal(false)
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const toggleTodo = (t: Todo, checked: boolean) => {
    api.patch(`/todos/${t.id}/status`, { status: checked ? '已完成' : '待办' })
      .then(() => bump()).catch(() => message.error('更新失败'))
  }

  const openReport = (period: 'week' | 'month') => {
    setReportPeriod(period)
    api.get<ScheduleSummary>('/schedule/report', { params: { period } })
      .then((r) => { setReport(r.data); setReportOpen(true) })
      .catch(() => message.error('生成失败'))
  }

  const openReportAi = (period: 'week' | 'month') => {
    setReportPeriod(period)
    setReportAiLoading(period)
    api.get<ScheduleSummary>('/schedule/report', { params: { period, ai: true } })
      .then((r) => {
        setReport(r.data)
        setReportOpen(true)
        if (!r.data.ai) message.info('LLM 未配置或调用失败，已使用模板周报')
      })
      .catch(() => message.error('生成失败'))
      .finally(() => setReportAiLoading(null))
  }

  const exportReportMd = () => {
    const blob = new Blob([report?.markdown ?? ''], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${report?.label ?? 'report'}.md`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const openTermReport = () => {
    const now = new Date()
    api.get<ScheduleSummary>('/schedule/term-report', { params: { year: now.getFullYear(), semester: now.getMonth() < 6 ? 1 : 2 } })
      .then((r) => { setReport(r.data); setReportOpen(true) })
      .catch(() => message.error('生成失败'))
  }

  const openMeetingMaterial = () => {
    api.get<ScheduleSummary>('/schedule/meeting-material')
      .then((r) => { setReport(r.data); setReportOpen(true) })
      .catch(() => message.error('生成失败'))
  }

  const saveMeeting = () => {
    meetingForm.validateFields().then((v) => {
      const req = editingMeeting ? api.put(`/advisor-meetings/${editingMeeting.id}`, v) : api.post('/advisor-meetings', v)
      req.then(() => {
        message.success('已保存')
        setMeetingModal(false)
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const convertAction = (m: AdvisorMeeting, idx: number) => {
    api.post(`/advisor-meetings/${m.id}/actions/${idx}/convert`)
      .then(() => { message.success('已转为今日待办'); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '转换失败'))
  }

  const pending = todos.filter((t) => t.status !== '已完成')
  const done = todos.filter((t) => t.status === '已完成')

  const burndownOption = useMemo(() => ({
    tooltip: { trigger: 'axis' as const },
    grid: { left: 40, right: 16, top: 16, bottom: 24 },
    xAxis: { type: 'category' as const, data: burndown.map((d) => d.label),
      axisLabel: { color: '#64748b', fontSize: 10 }, axisLine: { lineStyle: { color: '#1E293B' } }, axisTick: { show: false } },
    yAxis: { type: 'value' as const, minInterval: 1, splitLine: { lineStyle: { color: '#16233A' } },
      axisLabel: { color: '#64748b', fontSize: 10 } },
    series: [{
      type: 'line' as const, data: burndown.map((d) => d.remaining),
      smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#FBBF24', width: 2, shadowColor: 'rgba(251, 191, 36, 0.4)', shadowBlur: 8 },
      itemStyle: { color: '#FBBF24' },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: 'rgba(251, 191, 36, 0.25)' }, { offset: 1, color: 'rgba(251, 191, 36, 0.02)' }] } },
      animationDuration: 1000,
    }],
  }), [burndown])

  return (
    <>
      <Tabs
        activeKey={sub}
        onChange={(k) => nav(`/schedule/${k}`)}
        items={[
          {
            key: 'calendar',
            label: '待办日历',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {/* 本周/本月进展汇报卡 */}
                <Row gutter={[16, 16]}>
                  {summary && (
                    <Col xs={24} lg={14}>
                      <Card
                        size="small"
                        title={<span className="section-title">本周科研进展</span>}
                        extra={
                          <Space>
                            <Button size="small" onClick={() => openReport('week')}>生成周报</Button>
                            <Button size="small" onClick={() => openReport('month')}>生成月报</Button>
                            <Button size="small" icon={<RobotOutlined />} loading={reportAiLoading === 'week'} onClick={() => openReportAi('week')}>
                              AI 周报
                            </Button>
                            <Button size="small" icon={<RobotOutlined />} loading={reportAiLoading === 'month'} onClick={() => openReportAi('month')}>
                              AI 月报
                            </Button>
                            <Button size="small" onClick={() => openTermReport()}>学期总结</Button>
                            <Button size="small" onClick={() => openMeetingMaterial()}>组会材料</Button>
                          </Space>
                        }
                      >
                        <Row gutter={8}>
                          <Col span={5}><Statistic title="完成待办" value={summary.stats.todos_done} /></Col>
                          <Col span={5}><Statistic title="待办进行中" value={summary.stats.todos_pending} /></Col>
                          <Col span={5}><Statistic title="实验记录" value={summary.stats.experiments} /></Col>
                          <Col span={4}><Statistic title="新增文献" value={summary.stats.refs_added} /></Col>
                          <Col span={5}><Statistic title="写作字数" value={summary.stats.writing_total} /></Col>
                        </Row>
                        <div style={{ marginTop: 12 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>本周燃尽（剩余待办）</Typography.Text>
                          <EChart option={burndownOption} height={160} />
                        </div>
                      </Card>
                    </Col>
                  )}
                  {heatmap && (
                    <Col xs={24} lg={10}>
                      <Card size="small" title="科研活跃热力图">
                        <HeatmapMini days={heatmap.days} year={heatmap.year} />
                      </Card>
                    </Col>
                  )}
                </Row>

                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={14}>
                    <Card size="small" title="月度日历">
                      <Calendar
                        fullscreen={false}
                        value={selected}
                        onSelect={(d) => setSelected(d)}
                        cellRender={(d) => {
                          const n = dayCounts.get(d.format('YYYY-MM-DD'))
                          return n ? <Badge count={n} size="small" style={{ backgroundColor: '#1e3a5f' }} /> : null
                        }}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} lg={10}>
                    <Card
                      size="small"
                      title={`${selected.format('M月D日')} 待办`}
                      extra={<Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => openTodoModal()}>添加</Button>}
                    >
                      <List
                        size="small"
                        dataSource={pending}
                        locale={{ emptyText: '当天没有待办' }}
                        renderItem={(t) => (
                          <List.Item
                            actions={[
                              <Checkbox key="c" checked={false} onChange={(e) => toggleTodo(t, e.target.checked)} />,
                              <Button key="e" size="small" type="text" icon={<EditOutlined />} onClick={() => openTodoModal(t)} />,
                              <Popconfirm key="d" title="删除该待办？" onConfirm={() => api.delete(`/todos/${t.id}`).then(() => bump())}>
                                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                              </Popconfirm>,
                            ]}
                          >
                            <Space size={6}>
                              <Tag color={PRIORITY_COLORS[t.priority]}>{t.priority}</Tag>
                              {t.repeat !== 'none' && <Tag>♻ {t.repeat === 'weekly' ? '每周' : '每天'}</Tag>}
                              {t.title}
                            </Space>
                          </List.Item>
                        )}
                      />
                      {done.length > 0 && (
                        <>
                          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', margin: '8px 0 4px' }}>
                            已完成（{done.length}）
                          </Typography.Text>
                          <List
                            size="small"
                            dataSource={done}
                            renderItem={(t) => (
                              <List.Item
                                actions={[
                                  <Checkbox key="c" checked onChange={(e) => toggleTodo(t, e.target.checked)} />,
                                  <Popconfirm key="d" title="删除该待办？" onConfirm={() => api.delete(`/todos/${t.id}`).then(() => bump())}>
                                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                                  </Popconfirm>,
                                ]}
                              >
                                <span className="todo-done done" style={{ color: '#8a94a3' }}>{t.title}</span>
                                <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                                  {t.completed_at ? fmtDateTime(t.completed_at) : ''}
                                </Typography.Text>
                              </List.Item>
                            )}
                          />
                        </>
                      )}
                    </Card>
                  </Col>
                </Row>

                {/* 阶段总览 */}
                <Card size="small" title="项目阶段总览">
                  {phases.length === 0 ? (
                    <Empty description="暂无项目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  ) : (
                    <Row gutter={[16, 16]}>
                      {phases.map((p) => {
                        const rate = todoRates[p.project_id]
                        return (
                          <Col key={p.project_id} xs={24} md={12} lg={8} style={{ display: 'flex' }}>
                            <Card size="small" hoverable className="hover-lift" style={{ width: '100%' }}>
                              <div style={{ fontWeight: 600, marginBottom: 8 }}>{p.project_title}</div>
                              <Progress
                                percent={p.total ? Math.round((p.done / p.total) * 100) : 0}
                                size="small"
                                strokeColor="#1e3a5f"
                              />
                              <Space wrap size={4} style={{ marginTop: 8 }}>
                                {p.phases.map((ph) => (
                                  <Tag key={ph.id} color={PHASE_STATUS_COLORS[ph.status]}>{ph.name}</Tag>
                                ))}
                              </Space>
                              {rate && (
                                <div style={{ marginTop: 6, fontSize: 12, color: '#5b6675' }}>
                                  待办完成率：{rate.done}/{rate.total}（{rate.rate}%）
                                </div>
                              )}
                            </Card>
                          </Col>
                        )
                      })}
                    </Row>
                  )}
                </Card>
              </Space>
            ),
          },
          {
            key: 'kanban',
            label: '全局看板',
            children: (
              <Card size="small">
                <ProjectKanban />
              </Card>
            ),
          },
          {
            key: 'meetings',
            label: '组会记录',
            children: <GroupMeetingsPanel />,
          },
        ]}
      />

      {/* 待办弹窗 */}
      <Modal title={editing ? '编辑待办' : '添加待办'} open={todoModal} onOk={saveTodo} onCancel={() => setTodoModal(false)} destroyOnClose>
        <Form form={todoForm} layout="vertical">
          <Form.Item name="title" label="内容" rules={[{ required: true, message: '请输入待办内容' }]}>
            <Input placeholder="如：跑完 baseline 实验" />
          </Form.Item>
          <Form.Item name="date" label="日期" rules={[{ required: true }]}>
            <Input type="date" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="优先级 / 状态">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="priority" noStyle>
                <Select options={['高', '中', '低'].map((p) => ({ value: p, label: p }))} style={{ width: '50%' }} />
              </Form.Item>
              <Form.Item name="status" noStyle>
                <Select options={['待办', '进行中', '已完成'].map((s) => ({ value: s, label: s }))} style={{ width: '50%' }} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="repeat" label="重复">
            <Select options={[
              { value: 'none', label: '不重复' },
              { value: 'daily', label: '每天自动生成' },
              { value: 'weekly', label: '每周自动生成' },
            ]} />
          </Form.Item>
          <Form.Item name="project_id" label="关联项目">
            <Select allowClear placeholder="可选" options={projects.map((p) => ({ value: p.id, label: p.title }))} />
          </Form.Item>
          <Form.Item name="description" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 周报/月报弹窗 */}
      <Modal
        title={`${reportPeriod === 'week' ? '周报' : '月报'} · ${report?.label ?? ''}`}
        open={reportOpen}
        onCancel={() => setReportOpen(false)}
        footer={[
          <Button key="copy" icon={<CopyOutlined />}
            onClick={() => { navigator.clipboard.writeText(report?.markdown ?? ''); message.success('已复制，可粘贴给导师') }}>
            复制 Markdown
          </Button>,
          <Button key="export" icon={<DownloadOutlined />} onClick={exportReportMd}>导出 .md</Button>,
          <Button key="close" type="primary" onClick={() => setReportOpen(false)}>关闭</Button>,
        ]}
        width={640}
      >
        {report?.ai && <Tag color="green" style={{ marginBottom: 8 }}>🤖 AI 生成（数据来自平台记录）</Tag>}
        <div className="markdown-body" style={{ maxHeight: '60vh', overflow: 'auto', padding: 8 }}>
          <ReactMarkdown>{report?.markdown ?? ''}</ReactMarkdown>
        </div>
      </Modal>

      {/* 导师沟通弹窗 */}
      <Modal
        title={editingMeeting ? '编辑沟通记录' : '记录导师沟通'}
        open={meetingModal}
        onOk={saveMeeting}
        onCancel={() => setMeetingModal(false)}
        destroyOnClose
      >
        <Form form={meetingForm} layout="vertical">
          <Form.Item name="date" label="日期" rules={[{ required: true }]}>
            <Input type="date" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="topic" label="主题"><Input placeholder="如：组会 / 一对一讨论" /></Form.Item>
          <Form.Item name="summary" label="讨论纪要"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="action_items" label="导师意见（回车添加）">
            <Select mode="tags" placeholder="输入后回车" open={false} suffixIcon={null} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

function HeatmapMini({ days, year }: { days: { date: string; count: number }[]; year: number }) {
  const LEVELS = ['#ebedf0', '#d6e4d8', '#9fc7a4', '#5d9b66', '#2e6b3a']
  const byDate = new Map(days.map((d) => [d.date, d.count]))
  const cells: { date: string; level: number }[] = []
  const start = new Date(year, 0, 1)
  const end = new Date(year, 11, 31)
  const offset = (start.getDay() + 6) % 7
  for (let i = 0; i < offset; i++) cells.push({ date: '', level: 0 })
  const cur = new Date(start)
  while (cur <= end) {
    const iso = cur.toISOString().slice(0, 10)
    const c = byDate.get(iso) ?? 0
    cells.push({ date: iso, level: c === 0 ? 0 : c >= 8 ? 4 : c >= 5 ? 3 : c >= 2 ? 2 : 1 })
    cur.setDate(cur.getDate() + 1)
  }
  const weeks: typeof cells[] = []
  for (let w = 0; w < Math.ceil(cells.length / 7); w++) weeks.push(cells.slice(w * 7, (w + 1) * 7))
  return (
    <div style={{ display: 'flex', gap: 2, overflowX: 'auto' }}>
      {weeks.map((week, wi) => (
        <div key={wi} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {week.map((c, di) => (
            <div key={di} title={c.date ? `${c.date}：${byDate.get(c.date) ?? 0} 次` : ''}
              style={{ width: 9, height: 9, borderRadius: 2, background: c.date ? LEVELS[c.level] : 'transparent' }} />
          ))}
        </div>
      ))}
    </div>
  )
}
