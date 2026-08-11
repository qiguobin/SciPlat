import { useEffect, useState } from 'react'
import {
  Button, Card, Empty, Form, Input, message, Modal, Popconfirm, Select, Space, Tag, List, Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime, splitTags } from '../utils'
import type { Idea } from '../types'

/** 灵感收集箱：快速捕获想法，一键转为待办或实验记录 */
export default function Ideas() {
  const [list, setList] = useState<Idea[]>([])
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [quick, setQuick] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Idea | null>(null)
  const [converting, setConverting] = useState<Idea | null>(null)
  const [projects, setProjects] = useState<{ id: number; title: string }[]>([])
  const [phases, setPhases] = useState<{ id: number; name: string }[]>([])
  const [convertForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    api.get<Idea[]>('/ideas', { params: { status: statusFilter } })
      .then((r) => setList(r.data)).catch(() => {})
    api.get<{ id: number; title: string }[]>('/projects')
      .then((r) => setProjects(r.data)).catch(() => {})
  }
  useEffect(load, [refreshKey, statusFilter])

  const quickAdd = () => {
    if (!quick.trim()) return
    api.post('/ideas', { content: quick.trim() }).then(() => {
      message.success('已收录灵感')
      setQuick('')
      bump()
    }).catch(() => message.error('保存失败'))
  }

  const loadPhases = (projectId?: number) => {
    if (!projectId) { setPhases([]); return }
    api.get(`/projects/${projectId}`).then((r) => {
      setPhases((r.data.phases ?? []).map((ph: { id: number; name: string }) => ({ id: ph.id, name: ph.name })))
    }).catch(() => setPhases([]))
  }

  const convert = (target: string) => {
    if (!converting) return
    const v = convertForm.getFieldsValue()
    api.post(`/ideas/${converting.id}/convert`, { target, date: v.date ?? undefined, priority: v.priority ?? '中', project_id: v.project_id ?? undefined, phase_id: v.phase_id ?? undefined })
      .then((r) => {
        message.success(target === 'todo' ? '已转为待办' : '已转为实验记录')
        setConverting(null)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '转化失败'))
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space style={{ width: '100%' }} wrap>
          <Input
            placeholder="快速捕获一个想法、问题或灵感，回车收录…"
            value={quick}
            onChange={(e) => setQuick(e.target.value)}
            onPressEnter={quickAdd}
            style={{ maxWidth: 460 }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={quickAdd}>收录</Button>
          <Select
            placeholder="按状态筛选"
            allowClear
            style={{ width: 140 }}
            onChange={(v) => setStatusFilter(v)}
            options={['待处理', '已转化', '搁置'].map((s) => ({ value: s, label: s }))}
          />
        </Space>
      </Card>

      <Card size="small">
        {list.length === 0 ? (
          <Empty description="还没有灵感。科研想法随手记在这里，之后可一键转为待办或实验记录。" />
        ) : (
          <List
            dataSource={list}
            renderItem={(i) => (
              <List.Item
                actions={[
                  <Button key="c" size="small" icon={<SendOutlined />} disabled={i.status === '已转化'} onClick={() => { setConverting(i); convertForm.setFieldsValue({ priority: '中' }) }}>
                    转化
                  </Button>,
                  <Button key="e" size="small" icon={<EditOutlined />} onClick={() => { setEditing(i); editForm.setFieldsValue({ content: i.content, tags: splitTags(i.tags), status: i.status }); setModalOpen(true) }} />,
                  <Popconfirm key="d" title="删除该灵感？" onConfirm={() => api.delete(`/ideas/${i.id}`).then(() => bump())}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>,
                ]}
              >
                <Space direction="vertical" size={2}>
                  <Typography.Text>{i.content}</Typography.Text>
                  <Space size={6}>
                    <Tag color={i.status === '已转化' ? 'green' : i.status === '搁置' ? 'default' : 'gold'}>{i.status}</Tag>
                    {splitTags(i.tags).map((t) => <Tag key={t}>{t}</Tag>)}
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>{fmtDateTime(i.created_at)}</Typography.Text>
                  </Space>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 编辑弹窗 */}
      <Modal title="编辑灵感" open={modalOpen} onOk={() => {
        editForm.validateFields().then((v) => {
          api.put(`/ideas/${editing!.id}`, { ...v, tags: (v.tags ?? []).join(',') }).then(() => {
            message.success('已保存')
            setModalOpen(false)
            bump()
          })
        })
      }} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form form={editForm} layout="vertical">
          <Form.Item name="content" label="内容" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="tags" label="标签"><Select mode="tags" open={false} suffixIcon={null} /></Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={['待处理', '已转化', '搁置'].map((s) => ({ value: s, label: s }))} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 转化弹窗 */}
      <Modal title="转化灵感" open={!!converting} onCancel={() => setConverting(null)} destroyOnClose
        footer={[
          <Button key="todo" type="primary" icon={<SendOutlined />} onClick={() => convert('todo')}>转为待办</Button>,
          <Button key="exp" icon={<SendOutlined />} onClick={() => convert('experiment')}>转为实验记录</Button>,
          <Button key="close" onClick={() => setConverting(null)}>取消</Button>,
        ]}
      >
        <div style={{ marginBottom: 12, color: '#4a5568' }}>{converting?.content}</div>
        <Form form={convertForm} layout="vertical">
          <Form.Item name="date" label="日期（默认今天）"><Input type="date" /></Form.Item>
          <Form.Item name="priority" label="优先级"><Select options={['高', '中', '低'].map((p) => ({ value: p, label: p }))} /></Form.Item>
          <Form.Item name="project_id" label="关联项目">
            <Select allowClear options={projects.map((p) => ({ value: p.id, label: p.title }))}
              onChange={(v) => { convertForm.setFieldValue('phase_id', undefined); loadPhases(v) }} />
          </Form.Item>
          <Form.Item name="phase_id" label="实验阶段（转为实验记录时必填）">
            <Select allowClear placeholder={projects.length ? '先选择关联项目' : '暂无项目'}
              options={phases.map((ph) => ({ value: ph.id, label: ph.name }))} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
