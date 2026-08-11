import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Empty, Form, Input, InputNumber, List, message, Modal, Popconfirm, Select, Space, Tag, Typography, Upload,
} from 'antd'
import { DeleteOutlined, EditOutlined, FilePptOutlined, PlusOutlined, RobotOutlined, BookOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'

interface Meeting {
  id: number
  date: string
  topic: string
  summary: string
  qa_notes: string
  ppt_file_name: string | null
  project_id: number | null
  project_title: string
  meeting_type: string
  status: string
  attendees: string
  duration_min: number | null
  agenda: string
  reference_ids: number[]
  reference_titles: string[]
}

const MEETING_TYPES = ['组会', '进展汇报', '文献汇报', '开题', '中期', '预答辩']
const MEETING_STATUSES = ['已安排', '已召开', '已归档']

const TYPE_COLORS: Record<string, string> = {
  组会: 'blue', 进展汇报: 'cyan', 文献汇报: 'purple', 开题: 'orange', 中期: 'gold', 预答辩: 'red',
}
const STATUS_COLORS: Record<string, string> = { 已安排: 'default', 已召开: 'green', 已归档: 'default' }

/** 组会记录：关联项目/文献 + 元信息 + PPT + AI 纪要/问答式笔记 */
export default function GroupMeetingsPanel() {
  const nav = useNavigate()
  const [list, setList] = useState<Meeting[]>([])
  const [projects, setProjects] = useState<{ id: number; title: string }[]>([])
  const [refs, setRefs] = useState<{ id: number; title: string; year: number | null; jcr_quartile: string; cas_quartile: string }[]>([])
  const [projectFilter, setProjectFilter] = useState<number | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Meeting | null>(null)
  const [form] = Form.useForm()
  const [aiLoading, setAiLoading] = useState<{ id: number; kind: 'notes' | 'summary' } | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  useEffect(() => {
    api.get<Meeting[]>('/group-meetings', { params: projectFilter ? { project_id: projectFilter } : {} })
      .then((r) => setList(r.data)).catch(() => {})
  }, [refreshKey, projectFilter])

  useEffect(() => {
    api.get<{ id: number; title: string }[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
    api.get<{ id: number; title: string; year: number | null; jcr_quartile: string; cas_quartile: string }[]>('/references')
      .then((r) => setRefs(r.data)).catch(() => {})
  }, [refreshKey])

  const refOptions = useMemo(() => refs.map((r) => ({
    value: r.id,
    label: (
      <span>
        {r.title}
        <Tag style={{ fontSize: 10, marginLeft: 6 }}>{r.year ?? '?'}</Tag>
        {(r.jcr_quartile || r.cas_quartile) && (
          <Tag color="green" style={{ fontSize: 10 }}>{r.jcr_quartile || r.cas_quartile}</Tag>
        )}
      </span>
    ),
  })), [refs])

  const openModal = (m?: Meeting) => {
    setEditing(m ?? null)
    form.setFieldsValue(m
      ? {
          date: m.date, topic: m.topic, summary: m.summary,
          project_id: m.project_id ?? undefined, meeting_type: m.meeting_type,
          status: m.status, attendees: m.attendees, duration_min: m.duration_min,
          agenda: m.agenda, reference_ids: m.reference_ids,
        }
      : { date: new Date().toISOString().slice(0, 10), meeting_type: '组会', status: '已安排' })
    setModalOpen(true)
  }

  const save = () => {
    form.validateFields().then((v) => {
      const payload = { ...v, project_id: v.project_id ?? null, duration_min: v.duration_min ?? null, reference_ids: v.reference_ids ?? [] }
      const req = editing ? api.put(`/group-meetings/${editing.id}`, payload) : api.post('/group-meetings', payload)
      req.then(() => {
        message.success('已保存')
        setModalOpen(false)
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const saveQaNotes = (m: Meeting, notes: string) => {
    api.put(`/group-meetings/${m.id}`, { qa_notes: notes })
      .then(() => { message.success('笔记已保存'); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const runAi = (m: Meeting, kind: 'notes' | 'summary') => {
    setAiLoading({ id: m.id, kind })
    api.post(`/group-meetings/${m.id}/${kind === 'notes' ? 'ai-notes' : 'ai-summary'}`)
      .then((r) => {
        message.success(kind === 'notes' ? 'AI 问答式笔记已生成' : 'AI 会议纪要已生成')
        bump()
        setExpanded(m.id)
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '生成失败'))
      .finally(() => setAiLoading(null))
  }

  const uploadPpt = (m: Meeting, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    api.post(`/group-meetings/${m.id}/ppt`, fd)
      .then(() => { message.success('PPT 已上传'); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '上传失败'))
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>记录组会</Button>}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            placeholder="按项目筛选"
            allowClear
            style={{ width: 220 }}
            value={projectFilter ?? undefined}
            onChange={(v) => setProjectFilter(v ?? null)}
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            共 {list.length} 条 · 支持关联项目与文献，AI 纪要/问答自动带入文献摘要
          </Typography.Text>
        </Space>
        {list.length === 0 ? (
          <Empty description="还没有组会记录。每次组会后记录要点，AI 可自动生成纪要或问答式笔记。" />
        ) : (
          <List
            dataSource={list}
            renderItem={(m) => (
              <Card size="small" style={{ marginBottom: 12 }} key={m.id}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                  <Space wrap>
                    <Tag color="blue">{m.date}</Tag>
                    <Tag color={TYPE_COLORS[m.meeting_type] ?? 'default'}>{m.meeting_type}</Tag>
                    <Tag color={STATUS_COLORS[m.status] ?? 'default'}>{m.status}</Tag>
                    <Typography.Text strong>{m.topic || '组会'}</Typography.Text>
                    {m.project_title && <Tag color="cyan">📁 {m.project_title}</Tag>}
                    {m.duration_min && <Tag>{m.duration_min} 分钟</Tag>}
                    {m.ppt_file_name && <Tag color="purple" icon={<FilePptOutlined />}>PPT</Tag>}
                  </Space>
                  <Space>
                    <Button size="small" icon={<RobotOutlined />} loading={aiLoading?.id === m.id && aiLoading.kind === 'summary'}
                      onClick={() => runAi(m, 'summary')} title="基于主题/议程/要点/关联文献生成结构化纪要">
                      AI 纪要
                    </Button>
                    <Button size="small" icon={<RobotOutlined />} loading={aiLoading?.id === m.id && aiLoading.kind === 'notes'}
                      onClick={() => runAi(m, 'notes')}>
                      AI 问答笔记
                    </Button>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openModal(m)} />
                    <Popconfirm title="删除该组会记录？" onConfirm={() => api.delete(`/group-meetings/${m.id}`).then(() => bump())}>
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                </Space>
                {m.attendees && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    👥 参会人：{m.attendees}
                  </Typography.Text>
                )}
                {m.agenda && (
                  <Typography.Paragraph style={{ margin: '6px 0', fontSize: 12, color: '#5b6675', whiteSpace: 'pre-wrap' }}>
                    📋 议程：{m.agenda}
                  </Typography.Paragraph>
                )}
                {m.reference_ids.length > 0 && (
                  <Space size={2} wrap style={{ margin: '4px 0 6px' }}>
                    <BookOutlined style={{ color: '#A78BFA', fontSize: 12 }} />
                    {m.reference_ids.map((rid, i) => (
                      <Tag key={rid} color="purple" style={{ fontSize: 10, cursor: 'pointer' }} onClick={() => nav('/references/list')} title="关联文献（点击前往文献库）">
                        📚 {m.reference_titles[i]?.slice(0, 28) || `#${rid}`}
                      </Tag>
                    ))}
                  </Space>
                )}
                {m.summary && (
                  <Typography.Paragraph style={{ margin: '8px 0', whiteSpace: 'pre-wrap' }} type="secondary">
                    {m.summary}
                  </Typography.Paragraph>
                )}
                <Space style={{ marginBottom: 4 }}>
                  <Upload
                    accept=".ppt,.pptx,.pdf"
                    showUploadList={false}
                    beforeUpload={(f) => { uploadPpt(m, f); return false }}
                  >
                    <Button size="small" icon={<FilePptOutlined />}>{m.ppt_file_name ? '替换 PPT' : '上传 PPT'}</Button>
                  </Upload>
                  {m.ppt_file_name && (
                    <Button size="small" href={`/api/group-meetings/${m.id}/ppt`}>下载 PPT</Button>
                  )}
                  <Button size="small" type="link" onClick={() => setExpanded(expanded === m.id ? null : m.id)}>
                    {expanded === m.id ? '收起问答笔记' : '问答笔记'}
                  </Button>
                </Space>
                {expanded === m.id && (
                  <div>
                    <Input.TextArea
                      rows={10}
                      defaultValue={m.qa_notes}
                      style={{ fontFamily: 'var(--mono)', fontSize: 12 }}
                      onBlur={(e) => { if (e.target.value !== m.qa_notes) saveQaNotes(m, e.target.value) }}
                      placeholder="AI 问答式笔记（可编辑，失焦自动保存）"
                    />
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      点击「AI 问答笔记」基于要点与关联文献自动生成问题与答案框架；此处可手动编辑。
                    </Typography.Text>
                  </div>
                )}
              </Card>
            )
            }
          />
        )}
      </Card>

      <Modal title={editing ? '编辑组会' : '记录组会'} open={modalOpen} onOk={save} onCancel={() => setModalOpen(false)} width={640} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="date" label="日期" rules={[{ required: true }]}>
            <Input type="date" />
          </Form.Item>
          <Form.Item name="topic" label="主题"><Input placeholder="如：论文进展汇报 / 文献讨论" /></Form.Item>
          <Form.Item label="类型 / 状态">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="meeting_type" noStyle>
                <Select style={{ width: '50%' }} options={MEETING_TYPES.map((t) => ({ value: t, label: t }))} />
              </Form.Item>
              <Form.Item name="status" noStyle>
                <Select style={{ width: '50%' }} options={MEETING_STATUSES.map((s) => ({ value: s, label: s }))} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="project_id" label="关联项目">
            <Select allowClear placeholder="选择本次组会所属项目" options={projects.map((p) => ({ value: p.id, label: p.title }))} />
          </Form.Item>
          <Form.Item name="reference_ids" label="关联文献">
            <Select mode="multiple" allowClear placeholder="搜索并选择本次组会讨论的文献（AI 功能会自动带入文献摘要）"
              options={refOptions} optionFilterProp="label" maxTagCount={8} />
          </Form.Item>
          <Form.Item label="参会人 / 时长">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="attendees" noStyle>
                <Input placeholder="参会人，逗号分隔" style={{ width: '70%' }} />
              </Form.Item>
              <Form.Item name="duration_min" noStyle>
                <InputNumber placeholder="时长(分钟)" min={1} max={600} style={{ width: '30%' }} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="agenda" label="议程"><Input.TextArea rows={2} placeholder="本次组会议程：汇报人 / 主题 / 顺序…" /></Form.Item>
          <Form.Item name="summary" label="要点记录 / 纪要">
            <Input.TextArea rows={5} placeholder="本次组会要点、汇报内容、讨论结论…（可点击「AI 纪要」自动生成）" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
