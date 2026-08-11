import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button, Card, Col, DatePicker, Form, Input, Modal, Row, Select, Space, Tag, Typography, message, Popconfirm,
} from 'antd'
import { EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate } from '../utils'
import { PROJECT_STATUS, ProjectStatusTag } from '../components/StatusTag'
import type { Project } from '../types'

const TYPE_OPTIONS = ['学位课题', '基金', '课程', '其他']
const STATUS_OPTIONS = Object.keys(PROJECT_STATUS)
const TYPE_COLORS: Record<string, string> = {
  学位课题: 'blue', 基金: 'green', 课程: 'orange', 其他: 'default',
}

export default function Projects() {
  const nav = useNavigate()
  const [list, setList] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [phaseOverview, setPhaseOverview] = useState<Record<number, { done: number; total: number; current: string }>>({})
  const [form] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    setLoading(true)
    api
      .get<Project[]>('/projects')
      .then((r) => setList(r.data))
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
    api.get<{ project_id: number; done: number; total: number; phases: { name: string; status: string }[] }[]>('/schedule/phases')
      .then((r) => {
        const m: Record<number, { done: number; total: number; current: string }> = {}
        r.data.forEach((p) => {
          const current = p.phases.find((ph) => ph.status === '进行中')?.name
            ?? (p.done === p.total ? '全部完成' : p.phases.find((ph) => ph.status === '未开始')?.name ?? '')
          m[p.project_id] = { done: p.done, total: p.total, current: current ?? '' }
        })
        setPhaseOverview(m)
      })
      .catch(() => {})
  }
  useEffect(load, [refreshKey])

  const openModal = (p?: Project) => {
    setEditing(p ?? null)
    form.setFieldsValue(
      p
        ? {
            title: p.title, ptype: p.ptype, status: p.status,
            start_date: p.start_date ? dayjs(p.start_date) : null,
            end_date: p.end_date ? dayjs(p.end_date) : null,
            description: p.description,
          }
        : { ptype: '学位课题', status: '进行中' },
    )
    setOpen(true)
  }

  const save = () => {
    form.validateFields().then((v) => {
      const body = {
        ...v,
        start_date: v.start_date?.format('YYYY-MM-DD') ?? null,
        end_date: v.end_date?.format('YYYY-MM-DD') ?? null,
      }
      const req = editing
        ? api.put(`/projects/${editing.id}`, body)
        : api.post('/projects', body)
      req
        .then(() => {
          message.success(editing ? '已更新' : '已创建')
          setOpen(false)
          bump()
        })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const remove = (p: Project) => {
    api.delete(`/projects/${p.id}`).then(() => {
      message.success('已删除')
      bump()
    })
  }

  const filtered = statusFilter ? list.filter((p) => p.status === statusFilter) : list

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Select
            placeholder="按状态筛选"
            allowClear
            style={{ width: 160 }}
            onChange={(v) => setStatusFilter(v)}
            options={STATUS_OPTIONS.map((s) => ({ value: s, label: s }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
            新建项目
          </Button>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        {filtered.map((p) => (
          <Col key={p.id} xs={24} sm={12} lg={8} xl={6} style={{ display: 'flex' }}>
            <Card
              hoverable
              className="hover-lift"
              style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}
              styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column' } }}
              onClick={() => nav(`/projects/${p.id}`)}
              title={
                <Space>
                  <Tag color={TYPE_COLORS[p.ptype] ?? 'default'}>{p.ptype}</Tag>
                  {p.title}
                </Space>
              }
              extra={<ProjectStatusTag status={p.status} />}
              actions={[
                <Button
                  key="view" type="text" icon={<EyeOutlined />}
                  onClick={(e) => { e.stopPropagation(); nav(`/projects/${p.id}`) }}
                >
                  查看
                </Button>,
                <Button
                  key="edit" type="text" icon={<EditOutlined />}
                  onClick={(e) => { e.stopPropagation(); openModal(p) }}
                >
                  编辑
                </Button>,
                <Popconfirm key="del" title="删除该项目？将同时删除其论文、材料与文件。" onConfirm={(e) => { e?.stopPropagation(); remove(p) }} onCancel={(e) => e?.stopPropagation()}>
                  <Button type="text" danger onClick={(e) => e.stopPropagation()}>
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <Space direction="vertical" size={4} style={{ width: '100%', flex: 1, display: 'flex' }}>
                <div>
                  <Typography.Text type="secondary">
                    {fmtDate(p.start_date)} ~ {fmtDate(p.end_date)}
                  </Typography.Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Typography.Text type="secondary" ellipsis style={{ display: 'block' }}>
                    {p.description || '暂无描述'}
                  </Typography.Text>
                </div>
                <div>
                  <Tag>{p.paper_count ?? 0} 论文</Tag>
                  <Tag>{p.material_count ?? 0} 材料</Tag>
                  <Tag>{p.milestone_count ?? 0} 里程碑</Tag>
                  {phaseOverview[p.id] && (
                    <Tag color="blue" style={{ marginTop: 4 }}>
                      {phaseOverview[p.id].current
                        ? `${phaseOverview[p.id].current} · ${phaseOverview[p.id].done}/${phaseOverview[p.id].total}`
                        : `阶段 ${phaseOverview[p.id].done}/${phaseOverview[p.id].total}`}
                    </Tag>
                  )}
                </div>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
      {filtered.length === 0 && (
        <Card>
          <div style={{ textAlign: 'center', color: '#8a94a3', padding: '40px 24px' }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>📁</div>
            还没有项目。创建第一个项目，开始整理你的科研进度。
          </div>
        </Card>
      )}

      <Modal
        title={editing ? '编辑项目' : '新建项目'}
        open={open}
        onOk={save}
        onCancel={() => setOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="如：基于深度学习的蛋白质结构预测研究" />
          </Form.Item>
          <Form.Item name="ptype" label="类型">
            <Select options={TYPE_OPTIONS.map((t) => ({ value: t, label: t }))} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="start_date" label="开始日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="end_date" label="结束日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={4} placeholder="研究目标、方法、进展概要……" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
