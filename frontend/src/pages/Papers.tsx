import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Button, Card, Col, Empty, Input, Popconfirm, Row, Segmented, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime } from '../utils'
import { PAPER_STATUS, PaperStatusTag } from '../components/StatusTag'
import PaperFormModal from '../components/PaperFormModal'
import type { Paper, Project } from '../types'

interface BoardCard {
  id: number
  title: string
  status: string
  target_journal: string
  journal_quartile: string
  journal_if: string
  review_weeks: number | null
  submitted_at: string | null
  expected_review_date: string | null
  days_left: number | null
  overdue: boolean
  review_rounds: number
  next_statuses: string[]
}
interface BoardGroup { key: string; label: string; statuses: string[]; cards: BoardCard[] }
interface BoardJournal { name: string; quartile: string; impact_factor: string; review_weeks: number | null; notes: string; in_use: boolean }
interface BoardData { overdue_count: number; groups: BoardGroup[]; journals: BoardJournal[] }

export default function Papers() {
  const nav = useNavigate()
  const [list, setList] = useState<Paper[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [scaleFilter, setScaleFilter] = useState<string | undefined>()
  const [projectFilter, setProjectFilter] = useState<number | undefined>()
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Paper | null>(null)
  const [view, setView] = useState<'list' | 'board'>('list')
  const [board, setBoard] = useState<BoardData | null>(null)
  const [boardLoading, setBoardLoading] = useState(false)
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    setLoading(true)
    api
      .get<Paper[]>('/papers', {
        params: {
          status: statusFilter,
          project_id: projectFilter,
          q: search || undefined,
          paper_scale: scaleFilter,
        },
      })
      .then((r) => setList(r.data))
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [refreshKey, statusFilter, projectFilter, search, scaleFilter])

  const loadBoard = () => {
    setBoardLoading(true)
    api.get<BoardData>('/papers/submission-board')
      .then((r) => setBoard(r.data))
      .catch(() => message.error('看板加载失败'))
      .finally(() => setBoardLoading(false))
  }
  useEffect(() => { if (view === 'board') loadBoard() }, [view, refreshKey])

  useEffect(() => {
    api.get<Project[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
  }, [])

  const remove = (p: Paper) => {
    api.delete(`/papers/${p.id}`).then(() => {
      message.success('已删除')
      bump()
    })
  }

  const changeStatus = (id: number, to: string) => {
    api.post(`/papers/${id}/status`, { to }).then(() => {
      message.success(`已更新为 ${PAPER_STATUS[to]?.label ?? to}`)
      bump()
    }).catch((e) => message.error(e.response?.data?.detail ?? '状态更新失败'))
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            <Input.Search
              placeholder="搜索标题 / 关键词 / 期刊"
              allowClear
              style={{ width: 260 }}
              onSearch={(v) => setSearch(v)}
            />
            <Select
              placeholder="按状态筛选"
              allowClear
              style={{ width: 150 }}
              onChange={(v) => setStatusFilter(v)}
              options={Object.entries(PAPER_STATUS).map(([value, s]) => ({ value, label: s.label }))}
            />
            <Select
              placeholder="论文规模"
              allowClear
              style={{ width: 110 }}
              onChange={(v) => setScaleFilter(v)}
              options={[
                { value: '大论文', label: '大论文' },
                { value: '小论文', label: '小论文' },
              ]}
            />
            <Select
              placeholder="按项目筛选"
              allowClear
              style={{ width: 200 }}
              onChange={(v) => setProjectFilter(v)}
              options={projects.map((p) => ({ value: p.id, label: p.title }))}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setModalOpen(true) }}>
              新建论文
            </Button>
          </Space>
          <Segmented
            value={view}
            onChange={(v) => setView(v as 'list' | 'board')}
            options={[
              { value: 'list', label: '列表' },
              { value: 'board', label: '投稿看板' },
            ]}
          />
        </Space>
      </Card>

      {view === 'list' ? (
        <Card size="small">
          <Table<Paper>
            rowKey="id"
            loading={loading}
            dataSource={list}
            onRow={(r) => ({ onClick: () => nav(`/papers/${r.id}`), style: { cursor: 'pointer' } })}
            columns={[
              { title: '标题', dataIndex: 'title', ellipsis: true },
              {
                title: '规模',
                dataIndex: 'paper_scale',
                width: 90,
                render: (v: string) => v === '大论文' ? <Tag color="purple">大论文</Tag> : <Tag>小论文</Tag>,
              },
              { title: '类型', dataIndex: 'paper_type', width: 100 },
              { title: '目标期刊', dataIndex: 'target_journal', width: 170, ellipsis: true, render: (v, r) => v || (r.journal_quartile || r.journal_if) || '—' },
              {
                title: '所属项目',
                dataIndex: 'project_title',
                width: 150,
                ellipsis: true,
                render: (v) => v || '—',
              },
              { title: '状态', dataIndex: 'status', width: 100, render: (s: string) => <PaperStatusTag status={s} /> },
              { title: '更新时间', dataIndex: 'updated_at', width: 150, render: (v) => fmtDateTime(v) },
              {
                title: '操作',
                width: 90,
                render: (_, r) => (
                  <Space onClick={(e) => e.stopPropagation()}>
                    <Button size="small" onClick={() => { setEditing(r); setModalOpen(true) }}>
                      编辑
                    </Button>
                    <Popconfirm title="删除该论文？将同时删除版本与审稿记录文件。" onConfirm={() => remove(r)}>
                      <Button size="small" danger>删除</Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {board && board.overdue_count > 0 && (
            <Alert type="warning" showIcon message={`${board.overdue_count} 篇论文审稿已超预期时间，点击卡片查看详情。`} />
          )}
          <Card size="small" loading={boardLoading}>
            {board && board.groups.every((g) => g.cards.length === 0) ? (
              <Empty description="还没有小论文。新建小论文后，投稿状态会在这里分组展示。" />
            ) : (
              <Row gutter={[12, 12]}>
                {board?.groups.map((g) => (
                  <Col key={g.key} xs={24} sm={12} lg={4}>
                    <div style={{ background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 10, minHeight: 160 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                        <span>{g.label}</span>
                        <Tag style={{ fontSize: 10 }}>{g.cards.length}</Tag>
                      </div>
                      {g.cards.length === 0 ? (
                        <div style={{ fontSize: 12, color: '#64748B' }}>—</div>
                      ) : g.cards.map((c) => (
                        <div key={c.id} onClick={() => nav(`/papers/${c.id}`)}
                          style={{ background: '#0F172A', borderRadius: 8, padding: 10, marginBottom: 10, cursor: 'pointer', border: '1px solid #1E293B' }}>
                          <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.4 }}>{c.title}</div>
                          <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
                            {c.target_journal || '—'}
                            {c.journal_quartile && <Tag color="green" style={{ marginLeft: 4, fontSize: 10 }}>{c.journal_quartile}</Tag>}
                            {c.journal_if && <span style={{ marginLeft: 4 }}>IF {c.journal_if}</span>}
                            {c.review_weeks && <span style={{ marginLeft: 4 }}>· {c.review_weeks}周</span>}
                          </div>
                          <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>
                            {c.submitted_at ? `提交 ${c.submitted_at}` : '未提交'}
                            {c.expected_review_date && ` · 预期 ${c.expected_review_date}`}
                            {c.overdue && c.days_left !== null && <Tag color="red" style={{ marginLeft: 4, fontSize: 10 }}>超时 {-c.days_left}天</Tag>}
                            {c.review_rounds > 0 && ` · ${c.review_rounds} 轮审稿`}
                          </div>
                          <Space size={2} wrap style={{ marginTop: 6 }} onClick={(e) => e.stopPropagation()}>
                            {c.next_statuses.map((s) => (
                              <Button key={s} size="small" onClick={() => changeStatus(c.id, s)}>
                                {PAPER_STATUS[s]?.label ?? s}
                              </Button>
                            ))}
                          </Space>
                        </div>
                      ))}
                    </div>
                  </Col>
                ))}
              </Row>
            )}
          </Card>
          <Card size="small" title="期刊对比（候选投稿期刊）"
            extra={<Typography.Text type="secondary" style={{ fontSize: 11 }}>期刊库在「新建/编辑论文」弹窗中维护</Typography.Text>}>
            <Table<BoardJournal>
              rowKey="name"
              size="small"
              pagination={false}
              dataSource={board?.journals ?? []}
              columns={[
                { title: '期刊', dataIndex: 'name', render: (v, r) => <span>{v}{r.in_use && <Tag color="blue" style={{ marginLeft: 6 }}>使用中</Tag>}</span> },
                { title: '分区', dataIndex: 'quartile', width: 80 },
                { title: '影响因子', dataIndex: 'impact_factor', width: 100 },
                { title: '审稿周期', dataIndex: 'review_weeks', width: 100, render: (v) => v ? `约 ${v} 周` : '—' },
                { title: '备注', dataIndex: 'notes', ellipsis: true },
              ]}
              locale={{ emptyText: '暂无期刊数据' }}
            />
          </Card>
        </Space>
      )}

      <PaperFormModal
        open={modalOpen}
        initial={editing}
        onClose={() => setModalOpen(false)}
        onSaved={() => {
          message.success('已保存')
          bump()
        }}
      />
    </Space>
  )
}
