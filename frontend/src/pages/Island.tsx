import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, List, Progress, Space, Tag, Typography, message } from 'antd'
import { BookOutlined, BulbOutlined, CalendarOutlined, FileTextOutlined, FolderOpenOutlined, RadarChartOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { PAPER_STATUS, ProjectStatusTag } from '../components/StatusTag'
import EChart from '../components/EChart'
import type { Paper, Project, Todo } from '../types'

/** 科研岛：全景聚合页（项目/论文/文献/日程/追踪/灵感六分区） */
export default function Island() {
  const nav = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [phases, setPhases] = useState<Record<number, { done: number; total: number }>>({})
  const [papers, setPapers] = useState<Paper[]>([])
  const [refs, setRefs] = useState<{ id: number; title: string; year: number | null }[]>([])
  const [queue, setQueue] = useState<{ id: number; title: string }[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [ideas, setIdeas] = useState<{ id: number; content: string; status: string }[]>([])
  const [tracking, setTracking] = useState<{ id: number; title: string; link: string; published: string | null; is_new: boolean; source_id: number }[]>([])
  const [sourceNames, setSourceNames] = useState<Record<number, string>>({})
  const [burndown, setBurndown] = useState<{ label: string; remaining: number }[]>([])
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  useEffect(() => {
    api.get<Project[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
    api.get<{ project_id: number; done: number; total: number }[]>('/schedule/phases')
      .then((r) => {
        const m: Record<number, { done: number; total: number }> = {}
        r.data.forEach((p) => { m[p.project_id] = { done: p.done, total: p.total } })
        setPhases(m)
      }).catch(() => {})
    api.get<Paper[]>('/papers').then((r) => setPapers(r.data)).catch(() => {})
    api.get<{ id: number; title: string; year: number | null }[]>('/references')
      .then((r) => setRefs(r.data.slice(0, 5))).catch(() => {})
    api.get<{ id: number; title: string }[]>('/references/queue')
      .then((r) => setQueue(r.data.slice(0, 5))).catch(() => {})
    const today = new Date().toISOString().slice(0, 10)
    api.get<Todo[]>('/todos', { params: { date: today } })
      .then((r) => setTodos(r.data)).catch(() => {})
    api.get<{ id: number; content: string; status: string }[]>('/ideas')
      .then((r) => setIdeas(r.data.slice(0, 5))).catch(() => {})
    api.get<{ recent: { id: number; title: string; link: string; published: string | null; is_new: boolean; source_id: number }[] }>('/tracking/overview')
      .then((r) => setTracking(r.data.recent.slice(0, 5))).catch(() => {})
    api.get<{ id: number; name: string }[]>('/tracking/sources')
      .then((r) => {
        const names: Record<number, string> = {}
        r.data.forEach((s) => { names[s.id] = s.name })
        setSourceNames(names)
      }).catch(() => {})
    api.get<{ days: { label: string; remaining: number }[] }>('/schedule/burndown')
      .then((r) => setBurndown(r.data.days)).catch(() => {})
  }, [refreshKey])

  const paperCounts: Record<string, number> = {}
  papers.forEach((p) => { paperCounts[p.status] = (paperCounts[p.status] ?? 0) + 1 })

  const burndownOption = {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 32, right: 10, top: 12, bottom: 22 },
    xAxis: { type: 'category' as const, data: burndown.map((d) => d.label),
      axisLabel: { color: '#64748b', fontSize: 9 }, axisLine: { lineStyle: { color: '#1E293B' } }, axisTick: { show: false } },
    yAxis: { type: 'value' as const, minInterval: 1, splitLine: { lineStyle: { color: '#16233A' } }, axisLabel: { color: '#64748b', fontSize: 9 } },
    series: [{ type: 'line' as const, data: burndown.map((d) => d.remaining), smooth: true,
      symbol: 'circle', symbolSize: 4, lineStyle: { color: '#FBBF24', width: 2 },
      itemStyle: { color: '#FBBF24' }, animationDuration: 800 }],
  }

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        🏝 科研岛 <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>— 全景聚合 · 一览无余</Typography.Text>
      </Typography.Title>
      {/* 6 列固定网格：每卡通栏 6 列宽 × 3 行高，纵向排列 */}
      <div className="island-grid">
        {/* 项目岛 */}
        <div className="island-cell">
          <Card size="small" title={<span className="section-title"><FolderOpenOutlined style={{ marginRight: 6 }} />项目岛</span>}
            extra={<Button size="small" type="link" onClick={() => nav('/projects')}>全部 →</Button>}>
            {projects.length === 0 ? <Empty description="暂无项目" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
              <List size="small" dataSource={projects.slice(0, 5)} renderItem={(p) => {
                const ph = phases[p.id]
                return (
                  <List.Item onClick={() => nav(`/projects/${p.id}`)} style={{ cursor: 'pointer', paddingInline: 4 }}>
                    <Space direction="vertical" size={1} style={{ width: '100%' }}>
                      <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{p.title}</span>
                        <ProjectStatusTag status={p.status} />
                      </Space>
                      {ph && ph.total > 0 && <Progress percent={Math.round((ph.done / ph.total) * 100)} size="small" strokeColor="#38BDF8" style={{ margin: 0 }} />}
                    </Space>
                  </List.Item>
                )
              }} />
            )}
          </Card>
        </div>
        {/* 论文岛 */}
        <div className="island-cell">
          <Card size="small" title={<span className="section-title"><FileTextOutlined style={{ marginRight: 6 }} />论文岛</span>}
            extra={<Button size="small" type="link" onClick={() => nav('/papers')}>全部 →</Button>}>
            <Space wrap size={4} style={{ marginBottom: 8 }}>
              {Object.entries(PAPER_STATUS).map(([k, meta]) => (
                paperCounts[k] ? <Tag key={k} color={meta.color}>{meta.label} {paperCounts[k]}</Tag> : null
              ))}
            </Space>
            <List size="small" dataSource={papers.filter((p) => !['Accepted', 'Published'].includes(p.status)).slice(0, 4)}
              locale={{ emptyText: '暂无进行中论文' }}
              renderItem={(p) => (
                <List.Item onClick={() => nav(`/papers/${p.id}`)} style={{ cursor: 'pointer', paddingInline: 4 }}>
                  <Space size={6} style={{ minWidth: 0 }}>
                    <Tag color={PAPER_STATUS[p.status]?.color} style={{ fontSize: 10 }}>{PAPER_STATUS[p.status]?.label}</Tag>
                    <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</span>
                  </Space>
                </List.Item>
              )} />
          </Card>
        </div>
        {/* 文献岛 */}
        <div className="island-cell">
          <Card size="small" title={<span className="section-title"><BookOutlined style={{ marginRight: 6 }} />文献岛</span>}
            extra={<Button size="small" type="link" onClick={() => nav('/references/list')}>全部 →</Button>}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>最新入库</Typography.Text>
            <List size="small" dataSource={refs} renderItem={(r) => (
              <List.Item style={{ paddingInline: 4 }}>
                <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.year && <Tag style={{ fontSize: 10 }}>{r.year}</Tag>}{r.title}
                </span>
              </List.Item>
            )} />
            {queue.length > 0 && (
              <>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>阅读队列</Typography.Text>
                <List size="small" dataSource={queue} renderItem={(q) => (
                  <List.Item style={{ paddingInline: 4 }}>
                    <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <Tag color="green" style={{ fontSize: 10 }}>待读</Tag>{q.title}
                    </span>
                  </List.Item>
                )} />
              </>
            )}
          </Card>
        </div>
        {/* 日程岛 */}
        <div className="island-cell">
          <Card size="small" title={<span className="section-title"><CalendarOutlined style={{ marginRight: 6 }} />日程岛</span>}
            extra={<Button size="small" type="link" onClick={() => nav('/schedule/calendar')}>全部 →</Button>}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>今日待办（{todos.length}）</Typography.Text>
            <List size="small" dataSource={todos.slice(0, 4)} locale={{ emptyText: '今日无待办' }} renderItem={(t) => (
              <List.Item style={{ paddingInline: 4 }}>
                <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <Tag color={t.priority === '高' ? 'red' : t.priority === '中' ? 'orange' : 'default'} style={{ fontSize: 10 }}>{t.priority}</Tag>
                  {t.title}
                </span>
              </List.Item>
            )} />
            <div style={{ marginTop: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>本周燃尽</Typography.Text>
              <EChart option={burndownOption} height={110} />
            </div>
          </Card>
        </div>
        {/* 追踪岛 */}
        <div className="island-cell">
          <Card size="small" title={<span className="section-title"><RadarChartOutlined style={{ marginRight: 6 }} />追踪岛</span>}
            extra={<Button size="small" type="link" onClick={() => nav('/tracking')}>全部 →</Button>}>
            {tracking.length === 0 ? <Empty description="暂无追踪条目" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
              <List size="small" dataSource={tracking} renderItem={(item) => (
                <List.Item style={{ paddingInline: 4, cursor: 'pointer' }} onClick={() => item.link && window.open(item.link, '_blank')}>
                  <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.is_new && <Tag color="#FF005C" style={{ color: '#fff', borderColor: '#FF005C', fontSize: 10 }}>新</Tag>}
                    {sourceNames[item.source_id] && <Tag style={{ fontSize: 9 }}>{sourceNames[item.source_id].slice(0, 10)}</Tag>}
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
        </div>
        {/* 灵感岛 */}
        <div className="island-cell">
          <Card size="small" title={<span className="section-title"><BulbOutlined style={{ marginRight: 6 }} />灵感岛</span>}
            extra={<Button size="small" type="link" onClick={() => nav('/ideas')}>全部 →</Button>}>
            {ideas.length === 0 ? <Empty description="暂无灵感" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
              <List size="small" dataSource={ideas} renderItem={(i) => (
                <List.Item style={{ paddingInline: 4 }}>
                  <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <Tag color={i.status === '已转化' ? 'green' : 'gold'} style={{ fontSize: 10 }}>{i.status}</Tag>
                    {i.content}
                  </span>
                </List.Item>
              )} />
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
