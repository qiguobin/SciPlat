import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, DatePicker, Descriptions, Empty, Form, Input, InputNumber, List, message,
  Modal, Popconfirm, Progress, Row, Select, Space, Steps, Table, Tag, Timeline, Typography,
} from 'antd'
import {
  CopyOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, PlusOutlined, ReadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate, fmtSize } from '../utils'
import { MILESTONE_STATUS, ProjectStatusTag } from '../components/StatusTag'
import NotesPanel from '../components/NotesPanel'
import ProjectInsights from '../components/ProjectInsights'
import ExperimentExtras from '../components/ExperimentExtras'
import ProjectKanban from '../components/ProjectKanban'
import type { Experiment, Milestone, PhaseDetail, PhaseSuggestion, ProjectDetail, TimelinePoint } from '../types'

const TYPE_OPTIONS = ['学位课题', '基金', '课程', '其他']
const STATUS_OPTIONS = ['进行中', '暂停', '已完成', '已放弃']
const MILESTONE_STATUS_OPTIONS = Object.keys(MILESTONE_STATUS)
const PHASE_STATUS_OPTIONS = ['未开始', '进行中', '已完成', '延期']
const PHASE_STATUS_COLORS: Record<string, string> = { 未开始: 'default', 进行中: 'blue', 已完成: 'green', 延期: 'red' }

const TYPE_COLORS: Record<string, string> = {
  学位课题: 'blue', 基金: 'green', 课程: 'orange', 其他: 'default',
}

export default function ProjectDetail() {
  const nav = useNavigate()
  const pid = Number(location.pathname.split('/')[2])
  const [data, setData] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  // 里程碑
  const [milestoneModal, setMilestoneModal] = useState(false)
  const [editingMilestone, setEditingMilestone] = useState<Milestone | null>(null)
  const [msForm] = Form.useForm()
  // 时间线
  const [timelineModal, setTimelineModal] = useState(false)
  const [editingTimeline, setEditingTimeline] = useState<TimelinePoint | null>(null)
  const [tlForm] = Form.useForm()
  // 阶段
  const [phaseModal, setPhaseModal] = useState(false)
  const [editingPhase, setEditingPhase] = useState<PhaseDetail | null>(null)
  const [phForm] = Form.useForm()
  const [expModal, setExpModal] = useState(false)
  const [editingExp, setEditingExp] = useState<Experiment | null>(null)
  const [expPhaseId, setExpPhaseId] = useState<number | null>(null)
  const [expForm] = Form.useForm()
  const [refModal, setRefModal] = useState(false)
  const [refPhaseId, setRefPhaseId] = useState<number | null>(null)
  const [refForm] = Form.useForm()
  const [taskModal, setTaskModal] = useState(false)
  const [taskPhaseId, setTaskPhaseId] = useState<number | null>(null)
  const [taskForm] = Form.useForm()
  const [allRefs, setAllRefs] = useState<{ id: number; title: string }[]>([])
  const [allTodos, setAllTodos] = useState<{ id: number; title: string; date: string; status: string }[]>([])
  const [suggestions, setSuggestions] = useState<PhaseSuggestion[]>([])
  // 相关组会（项目联动）
  const [meetings, setMeetings] = useState<{ id: number; date: string; topic: string; meeting_type: string; status: string }[]>([])

  const load = () => {
    setLoading(true)
    api
      .get<ProjectDetail>(`/projects/${pid}`)
      .then((r) => setData(r.data))
      .catch(() => message.error('项目不存在'))
      .finally(() => setLoading(false))
    api.get<{ id: number; title: string }[]>('/references')
      .then((r) => setAllRefs(r.data)).catch(() => {})
    api.get<{ id: number; title: string; date: string; status: string }[]>('/todos')
      .then((r) => setAllTodos(r.data)).catch(() => {})
    api.get<{ suggestions: PhaseSuggestion[] }>(`/projects/${pid}/phase-suggestions`)
      .then((r) => setSuggestions(r.data.suggestions)).catch(() => {})
    api.get<{ id: number; date: string; topic: string; meeting_type: string; status: string }[]>(
      '/group-meetings', { params: { project_id: pid } },
    ).then((r) => setMeetings(r.data)).catch(() => {})
  }
  useEffect(load, [pid, refreshKey])

  const openMilestoneModal = (m?: Milestone) => {
    setEditingMilestone(m ?? null)
    msForm.setFieldsValue(
      m ? { title: m.title, due_date: dayjs(m.due_date), status: m.status, note: m.note,
            goal: m.goal, scope: m.scope, progress: m.progress }
        : { status: '未开始', note: '', progress: 0 },
    )
    setMilestoneModal(true)
  }

  const saveMilestone = () => {
    msForm.validateFields().then((v) => {
      const body = { ...v, due_date: v.due_date.format('YYYY-MM-DD') }
      const req = editingMilestone
        ? api.put(`/projects/milestones/${editingMilestone.id}`, body)
        : api.post(`/projects/${pid}/milestones`, body)
      req
        .then(() => {
          message.success('已保存')
          setMilestoneModal(false)
          bump()
        })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const openTimelineModal = (t?: TimelinePoint) => {
    setEditingTimeline(t ?? null)
    tlForm.setFieldsValue(
      t ? { title: t.title, point_date: dayjs(t.point_date), note: t.note } : { note: '' },
    )
    setTimelineModal(true)
  }

  const saveTimeline = () => {
    tlForm.validateFields().then((v) => {
      const body = { ...v, point_date: v.point_date.format('YYYY-MM-DD') }
      const req = editingTimeline
        ? api.put(`/projects/timeline/${editingTimeline.id}`, body)
        : api.post(`/projects/${pid}/timeline`, body)
      req
        .then(() => {
          message.success('已保存')
          setTimelineModal(false)
          bump()
        })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const exportZip = () => {
    window.open(`/api/projects/${pid}/export`, '_blank')
  }

  // ---------- 阶段操作 ----------
  const openPhaseModal = (ph?: PhaseDetail) => {
    setEditingPhase(ph ?? null)
    phForm.setFieldsValue(ph
      ? { name: ph.name, description: ph.description, status: ph.status,
          start_date: ph.start_date ? dayjs(ph.start_date) : null, end_date: ph.end_date ? dayjs(ph.end_date) : null }
      : { status: '未开始' })
    setPhaseModal(true)
  }

  const savePhase = () => {
    phForm.validateFields().then((v) => {
      const body = {
        ...v,
        start_date: v.start_date?.format('YYYY-MM-DD') ?? null,
        end_date: v.end_date?.format('YYYY-MM-DD') ?? null,
      }
      const req = editingPhase
        ? api.put(`/projects/phases/${editingPhase.id}`, body)
        : api.post(`/projects/${pid}/phases`, body)
      req.then(() => { message.success('已保存'); setPhaseModal(false); bump() })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const openExpModal = (ph: PhaseDetail, e?: Experiment) => {
    setExpPhaseId(ph.id)
    setEditingExp(e ?? null)
    expForm.setFieldsValue(e
      ? { title: e.title, date: dayjs(e.date), purpose: e.purpose, method: e.method, result: e.result,
          conclusion: e.conclusion, reflection: e.reflection, hypothesis: e.hypothesis, variables: e.variables,
          controls: e.controls, material_ids: e.material_ids ? e.material_ids.split(',').map(Number) : [] }
      : { date: dayjs() })
    setExpModal(true)
  }

  const saveExp = () => {
    expForm.validateFields().then((v) => {
      const body = {
        ...v,
        date: v.date.format('YYYY-MM-DD'),
        material_ids: (v.material_ids ?? []).join(','),
      }
      const req = editingExp
        ? api.put(`/projects/phases/experiments/${editingExp.id}`, body)
        : api.post(`/projects/phases/${expPhaseId}/experiments`, body)
      req.then(() => { message.success('已保存'); setExpModal(false); bump() })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const saveRefLink = () => {
    refForm.validateFields().then((v) => {
      api.post(`/projects/phases/${refPhaseId}/references`, { reference_id: v.reference_id })
        .then(() => { message.success('已关联'); setRefModal(false); bump() })
        .catch((e) => message.error(e.response?.data?.detail ?? '关联失败'))
    })
  }

  const saveTaskLink = () => {
    taskForm.validateFields().then((v) => {
      api.post(`/projects/phases/${taskPhaseId}/tasks`, { todo_id: v.todo_id })
        .then(() => { message.success('已关联'); setTaskModal(false); bump() })
        .catch((e) => message.error(e.response?.data?.detail ?? '关联失败'))
    })
  }

  if (loading || !data) return <Card loading={loading} />

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card
        title={
          <Space>
            <Typography.Text strong style={{ fontSize: 18 }}>{data.title}</Typography.Text>
            <Tag color={TYPE_COLORS[data.ptype] ?? 'default'}>{data.ptype}</Tag>
            <ProjectStatusTag status={data.status} />
          </Space>
        }
        extra={
          <Space>
            <Button icon={<DownloadOutlined />} onClick={exportZip}>
              导出材料包
            </Button>
            <Popconfirm
              title="从本项目复制为模板新建？"
              description="将复制全部阶段结构创建新项目（名称加「副本」）。"
              onConfirm={() => {
                api.post(`/projects/${pid}/copy-template`).then((r) => {
                  message.success(`已创建「${r.data.title}」`)
                  bump()
                  nav(`/projects/${r.data.id}`)
                }).catch((e) => message.error(e.response?.data?.detail ?? '复制失败'))
              }}
            >
              <Button icon={<CopyOutlined />}>复制为模板</Button>
            </Popconfirm>
            <Button onClick={() => nav('/projects')}>返回列表</Button>
          </Space>
        }
      >
        <Descriptions column={3} size="small">
          <Descriptions.Item label="起止时间">
            {fmtDate(data.start_date)} ~ {fmtDate(data.end_date)}
          </Descriptions.Item>
          <Descriptions.Item label="关联论文">{data.paper_count ?? 0} 篇</Descriptions.Item>
          <Descriptions.Item label="材料文件">{data.material_count ?? 0} 个</Descriptions.Item>
          <Descriptions.Item label="描述" span={3}>
            {data.description || '—'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="关键时间线（开题 / 中期 / 答辩…）"
        size="small"
        extra={
          <Button size="small" icon={<PlusOutlined />} onClick={() => openTimelineModal()}>
            添加节点
          </Button>
        }
      >
        {data.timeline_points.length === 0 ? (
          <Empty description="暂无时间线节点" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Timeline
            items={data.timeline_points.map((t) => ({
              children: (
                <Space>
                  <Typography.Text strong>{t.title}</Typography.Text>
                  <Typography.Text type="secondary">{t.point_date}</Typography.Text>
                  <Typography.Text type="secondary">{t.note}</Typography.Text>
                  <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openTimelineModal(t)} />
                  <Popconfirm title="删除该节点？" onConfirm={() => {
                    api.delete(`/projects/timeline/${t.id}`).then(() => bump())
                  }}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            }))}
          />
        )}
      </Card>

      <Card
        title="里程碑"
        size="small"
        extra={
          <Button size="small" icon={<PlusOutlined />} onClick={() => openMilestoneModal()}>
            添加里程碑
          </Button>
        }
      >
        <Table<Milestone>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data.milestones}
          columns={[
            { title: '标题', dataIndex: 'title', render: (v, m) => (
              <Space direction="vertical" size={0}>
                <span>{v}</span>
                {m.goal && <Typography.Text type="secondary" style={{ fontSize: 11 }}>🎯 {m.goal}</Typography.Text>}
              </Space>
            ) },
            { title: '截止日期', dataIndex: 'due_date', width: 120 },
            {
              title: '进度',
              dataIndex: 'progress',
              width: 150,
              render: (v: number) => <Progress percent={v} size="small" strokeColor="#34D399" style={{ margin: 0 }} />,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (s: string) => (
                <Tag color={MILESTONE_STATUS[s]?.color ?? 'default'}>{s}</Tag>
              ),
            },
            { title: '备注', dataIndex: 'note', ellipsis: true },
            {
              title: '操作',
              width: 140,
              render: (_, m) => (
                <Space>
                  <Button size="small" icon={<EditOutlined />} onClick={() => openMilestoneModal(m)} />
                  <Popconfirm title="删除该里程碑？" onConfirm={() => {
                    api.delete(`/projects/milestones/${m.id}`).then(() => bump())
                  }}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      {/* 研究阶段：时间链 */}
      <Card
        title={
          <Space>
            <span className="section-title">研究阶段（时间链）</span>
            <Tag>{data.phases.filter((ph) => ph.status === '已完成').length}/{data.phases.length} 完成</Tag>
          </Space>
        }
        size="small"
        extra={<Button size="small" icon={<PlusOutlined />} onClick={() => openPhaseModal()}>添加阶段</Button>}
      >
        <Progress
          percent={data.phases.length ? Math.round((data.phases.filter((ph) => ph.status === '已完成').length / data.phases.length) * 100) : 0}
          size="small"
          strokeColor="#1e3a5f"
          style={{ marginBottom: 16 }}
        />
        <Steps
          direction="vertical"
          size="small"
          items={data.phases.map((ph) => {
            const refTitles = new Map(allRefs.map((r) => [r.id, r.title]))
            const todoTitles = new Map(allTodos.map((t) => [t.id, t]))
            return {
              key: ph.id,
              status: ph.status === '已完成' ? 'finish' : ph.status === '进行中' ? 'process' : 'wait',
              title: (
                <Space>
                  <Typography.Text strong>{ph.name}</Typography.Text>
                  <Tag color={PHASE_STATUS_COLORS[ph.status]}>{ph.status}</Tag>
                  {ph.start_date && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{ph.start_date} ~ {ph.end_date ?? '至今'}</Typography.Text>}
                  {suggestions.filter((s) => s.phase_id === ph.id).map((s) => (
                    <Tag key={s.phase_id} color="green" style={{ cursor: 'pointer' }}
                      onClick={() => {
                        api.put(`/projects/phases/${ph.id}`, { status: '已完成' }).then(() => {
                          if (s.next_phase_id) api.put(`/projects/phases/${s.next_phase_id}`, { status: '进行中' })
                          message.success(`已应用：${s.suggestion}`)
                          bump()
                        })
                      }}
                    >
                      💡 {s.experiments} 实验 · 任务 {s.tasks_done}/{s.tasks_total} → {s.suggestion}
                    </Tag>
                  ))}
                  <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openPhaseModal(ph)} />
                  <Popconfirm title="删除该阶段？其下实验记录将一并删除。" onConfirm={() => api.delete(`/projects/phases/${ph.id}`).then(() => bump())}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
              description: (
                <div style={{ padding: '4px 0 12px' }}>
                  {ph.description && <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>{ph.description}</Typography.Paragraph>}

                  {/* 实验记录 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0 4px' }}>
                    <Typography.Text strong style={{ fontSize: 13 }}>实验记录（{ph.experiments.length}）</Typography.Text>
                    <Button size="small" type="link" icon={<PlusOutlined />} onClick={() => openExpModal(ph)}>添加</Button>
                  </div>
                  {ph.experiments.length === 0 ? (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无实验记录</Typography.Text>
                  ) : (
                    <List
                      size="small"
                      dataSource={ph.experiments}
                      renderItem={(e) => (
                        <Card size="small" style={{ marginBottom: 8 }}>
                          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                            <Space>
                              <Tag>{e.date}</Tag>
                              <Typography.Text strong>{e.title}</Typography.Text>
                            </Space>
                            <Space>
                              <Button size="small" icon={<EditOutlined />} onClick={() => openExpModal(ph, e)} />
                              <Popconfirm title="删除该实验记录？" onConfirm={() => api.delete(`/projects/phases/experiments/${e.id}`).then(() => bump())}>
                                <Button size="small" danger icon={<DeleteOutlined />} />
                              </Popconfirm>
                            </Space>
                          </Space>
                          <Descriptions column={1} size="small" style={{ marginTop: 6 }}>
                            {e.hypothesis && <Descriptions.Item label="假设">{e.hypothesis}</Descriptions.Item>}
                            {(e.variables || e.controls) && (
                              <Descriptions.Item label="变量/对照">
                                {[e.variables, e.controls].filter(Boolean).join(' ｜ ')}
                              </Descriptions.Item>
                            )}
                            {e.purpose && <Descriptions.Item label="目的">{e.purpose}</Descriptions.Item>}
                            {e.method && <Descriptions.Item label="方法">{e.method}</Descriptions.Item>}
                            {e.result && <Descriptions.Item label="结果">{e.result}</Descriptions.Item>}
                            {e.conclusion && <Descriptions.Item label="结论">{e.conclusion}</Descriptions.Item>}
                            {e.reflection && <Descriptions.Item label="复盘">{e.reflection}</Descriptions.Item>}
                            {e.material_ids && (
                              <Descriptions.Item label="关联材料">
                                {e.material_ids.split(',').map((mid) => {
                                  const m = data.materials.find((x) => x.id === Number(mid))
                                  return m ? <Tag key={mid}>{m.name}</Tag> : null
                                })}
                              </Descriptions.Item>
                            )}
                          </Descriptions>
                          <ExperimentExtras experiment={e} />
                        </Card>
                      )}
                    />
                  )}

                  {/* 文献证据 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0 4px' }}>
                    <Typography.Text strong style={{ fontSize: 13 }}>文献证据（{ph.reference_ids.length}）</Typography.Text>
                    <Button size="small" type="link" icon={<PlusOutlined />} onClick={() => { setRefPhaseId(ph.id); refForm.resetFields(); setRefModal(true) }}>关联文献</Button>
                  </div>
                  <Space wrap size={4}>
                    {ph.reference_ids.length === 0 && <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无关联文献</Typography.Text>}
                    {ph.reference_ids.map((rid) => (
                      <Tag key={rid} closable onClose={(e) => {
                        e.preventDefault()
                        api.delete(`/projects/phases/${ph.id}/references/${rid}`).then(() => bump())
                      }}>
                        {refTitles.get(rid) ?? `文献 #${rid}`}
                      </Tag>
                    ))}
                  </Space>

                  {/* 关联任务 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0 4px' }}>
                    <Typography.Text strong style={{ fontSize: 13 }}>关联任务（{ph.todo_ids.length}）</Typography.Text>
                    <Button size="small" type="link" icon={<PlusOutlined />} onClick={() => { setTaskPhaseId(ph.id); taskForm.resetFields(); setTaskModal(true) }}>关联待办</Button>
                  </div>
                  {ph.todo_ids.length === 0 ? (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无关联任务</Typography.Text>
                  ) : (
                    <List
                      size="small"
                      dataSource={ph.todo_ids}
                      renderItem={(tid) => {
                        const t = todoTitles.get(tid)
                        return (
                          <List.Item style={{ padding: '2px 0' }}
                            actions={[<Button key="d" size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => api.delete(`/projects/phases/${ph.id}/tasks/${tid}`).then(() => bump())} />]}>
                            <Space size={6}>
                              {t && <Tag color={t.status === '已完成' ? 'green' : 'default'}>{t.status}</Tag>}
                              {t?.title ?? `待办 #${tid}`}
                            </Space>
                          </List.Item>
                        )
                      }}
                    />
                  )}
                </div>
              ),
            }
          })}
        />
      </Card>

      {/* 项目看板（GitHub Projects 模式） */}
      <Card size="small" title={<span className="section-title">任务看板（拖拽流转）</span>}>
        <ProjectKanban projectId={pid} todoIds={data.phases.flatMap((ph) => ph.todo_ids)} />
      </Card>

      <Card title="关联论文" size="small">
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data.papers}
          onRow={(r) => ({ onClick: () => nav(`/papers/${r.id}`), style: { cursor: 'pointer' } })}
          columns={[
            { title: '标题', dataIndex: 'title' },
            { title: '类型', dataIndex: 'paper_type', width: 110 },
            { title: '目标期刊', dataIndex: 'target_journal', width: 160 },
            { title: '状态', dataIndex: 'status', width: 110 },
          ]}
          locale={{ emptyText: '暂无关联论文' }}
        />
      </Card>

      <Card title="科研材料" size="small">
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data.materials}
          onRow={(r) => ({ onClick: () => nav(`/materials?project_id=${pid}`), style: { cursor: 'pointer' } })}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '分类', dataIndex: 'category', width: 110 },
            { title: '文件', dataIndex: 'file_name', width: 200, ellipsis: true },
            { title: '大小', dataIndex: 'size', width: 90, render: (v: number) => fmtSize(v) },
          ]}
          locale={{ emptyText: '暂无材料，去材料页上传' }}
        />
      </Card>

      <Card
        title="相关组会"
        size="small"
        extra={<Button size="small" type="link" onClick={() => nav('/schedule/meetings')}>全部组会 →</Button>}
      >
        <List
          size="small"
          dataSource={meetings}
          locale={{ emptyText: '暂无关联组会，可在「日程 → 组会记录」中关联本项目' }}
          renderItem={(m) => (
            <List.Item onClick={() => nav('/schedule/meetings')} style={{ cursor: 'pointer', paddingInline: 2 }}>
              <Space size={6}>
                <Tag color="blue">{m.date}</Tag>
                <Tag>{m.meeting_type}</Tag>
                <span style={{ fontSize: 13 }}>{m.topic || '组会'}</span>
                <Tag color={m.status === '已召开' ? 'green' : 'default'}>{m.status}</Tag>
              </Space>
            </List.Item>
          )}
        />
      </Card>

      {/* 结项复盘与风险跟踪 */}
      <ProjectInsights projectId={pid} />

      <Card title="实验记录" size="small">
        <NotesPanel targetType="project" targetId={pid} />
      </Card>

      {/* 里程碑弹窗 */}
      <Modal
        title={editingMilestone ? '编辑里程碑' : '添加里程碑'}
        open={milestoneModal}
        onOk={saveMilestone}
        onCancel={() => setMilestoneModal(false)}
        destroyOnClose
      >
        <Form form={msForm} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="如：完成实验方案设计" />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={MILESTONE_STATUS_OPTIONS.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="goal" label="冲刺目标（🎯）"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="进度 / 范围">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="progress" noStyle><InputNumber min={0} max={100} style={{ width: '30%' }} /></Form.Item>
              <Form.Item name="scope" noStyle><Input placeholder="范围（交付内容）" style={{ width: '70%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 时间线弹窗 */}
      <Modal
        title={editingTimeline ? '编辑节点' : '添加时间线节点'}
        open={timelineModal}
        onOk={saveTimeline}
        onCancel={() => setTimelineModal(false)}
        destroyOnClose
      >
        <Form form={tlForm} layout="vertical">
          <Form.Item name="title" label="节点名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：开题报告 / 中期检查 / 预答辩" />
          </Form.Item>
          <Form.Item name="point_date" label="日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 阶段弹窗 */}
      <Modal
        title={editingPhase ? '编辑阶段' : '添加阶段'}
        open={phaseModal}
        onOk={savePhase}
        onCancel={() => setPhaseModal(false)}
        destroyOnClose
      >
        <Form form={phForm} layout="vertical">
          <Form.Item name="name" label="阶段名称" rules={[{ required: true, message: '请输入阶段名称' }]}>
            <Input placeholder="如：实验阶段" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={PHASE_STATUS_OPTIONS.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item label="起止时间">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="start_date" noStyle><DatePicker placeholder="开始" style={{ width: '50%' }} /></Form.Item>
              <Form.Item name="end_date" noStyle><DatePicker placeholder="结束" style={{ width: '50%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="description" label="阶段说明"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      {/* 实验记录弹窗 */}
      <Modal
        title={editingExp ? '编辑实验记录' : '添加实验记录'}
        open={expModal}
        onOk={saveExp}
        onCancel={() => setExpModal(false)}
        width={640}
        destroyOnClose
      >
        <Form form={expForm} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="如：baseline 模型训练" />
          </Form.Item>
          <Form.Item name="date" label="日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="hypothesis" label="假设（预注册）"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="变量 / 对照（预注册）">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="variables" noStyle><Input placeholder="自变量/因变量" style={{ width: '50%' }} /></Form.Item>
              <Form.Item name="controls" noStyle><Input placeholder="对照组设置" style={{ width: '50%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="purpose" label="实验目的"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="method" label="方法"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="result" label="结果"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="conclusion" label="结论"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="reflection" label="复盘 / 失败经验"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="material_ids" label="关联材料">
            <Select mode="multiple" placeholder="选择本项目材料" options={data?.materials.map((m) => ({ value: m.id, label: m.name }))} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 关联文献弹窗 */}
      <Modal
        title="关联文献证据"
        open={refModal}
        onOk={saveRefLink}
        onCancel={() => setRefModal(false)}
        destroyOnClose
      >
        <Form form={refForm} layout="vertical">
          <Form.Item name="reference_id" label="选择文献" rules={[{ required: true, message: '请选择文献' }]}>
            <Select showSearch optionFilterProp="label" options={allRefs.map((r) => ({ value: r.id, label: r.title }))} placeholder="搜索并选择文献" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 关联任务弹窗 */}
      <Modal
        title="关联待办任务"
        open={taskModal}
        onOk={saveTaskLink}
        onCancel={() => setTaskModal(false)}
        destroyOnClose
      >
        <Form form={taskForm} layout="vertical">
          <Form.Item name="todo_id" label="选择待办" rules={[{ required: true, message: '请选择待办' }]}>
            <Select showSearch optionFilterProp="label" options={allTodos.map((t) => ({ value: t.id, label: `${t.date} ${t.title}（${t.status}）` }))} placeholder="搜索并选择待办" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
