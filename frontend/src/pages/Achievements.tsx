import { useEffect, useState } from 'react'
import {
  Button, Card, Col, DatePicker, Descriptions, Empty, Form, Input, message, Modal, Popconfirm,
  Row, Select, Space, Statistic, Table, Tabs, Tag, Timeline, Typography, Upload,
} from 'antd'
import { DeleteOutlined, DownloadOutlined, EditOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate } from '../utils'
import type { Achievement } from '../types'

const TYPE_COLORS: Record<string, string> = { 论文: 'blue', 专利: 'green', 软件: 'purple', 获奖: 'gold', 其他: 'default' }
const STATUS_OPTIONS = ['已投稿', '已接收', '已发表', '申请中', '已授权', '开发中', '已发布', '进行中', '已完成']

export default function Achievements() {
  const nav = useNavigate()
  const { sub = 'list' } = useParams()
  const [list, setList] = useState<(Achievement & { synced?: boolean })[]>([])
  const [stats, setStats] = useState<{ by_type: Record<string, number>; total: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Achievement | null>(null)
  const [form] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    setLoading(true)
    api.get<Achievement[]>('/achievements', { params: { atype: typeFilter } })
      .then((r) => setList(r.data)).catch(() => message.error('加载失败')).finally(() => setLoading(false))
    api.get<{ by_type: Record<string, number>; total: number }>('/achievements/stats')
      .then((r) => setStats(r.data)).catch(() => {})
  }
  useEffect(load, [refreshKey, typeFilter])

  const openModal = (a?: Achievement) => {
    setEditing(a ?? null)
    form.setFieldsValue(a
      ? {
          atype: a.atype, title: a.title, status: a.status, date: a.date ? dayjs(a.date) : null,
          venue: a.venue, identifier: a.identifier, authors: a.authors, detail: a.detail, link: a.link, notes: a.notes,
        }
      : { atype: '专利', status: '申请中' })
    setModalOpen(true)
  }

  const save = () => {
    form.validateFields().then((v) => {
      const body = { ...v, date: v.date?.format('YYYY-MM-DD') ?? null }
      const req = editing ? api.put(`/achievements/${editing.id}`, body) : api.post('/achievements', body)
      req.then(() => {
        message.success('已保存')
        setModalOpen(false)
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  return (
    <Tabs activeKey={sub} onChange={(k) => nav(`/achievements/${k}`)} items={[
      {
        key: 'list',
        label: '成果列表',
        children: (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {stats && (
        <Row gutter={[16, 16]}>
          {Object.entries(stats.by_type).map(([t, n]) => (
            <Col xs={12} md={6} key={t} style={{ display: 'flex' }}>
              <Card size="small" hoverable style={{ width: '100%', ...(typeFilter === t ? { borderColor: '#1e3a5f' } : {}) }}
                onClick={() => setTypeFilter(typeFilter === t ? undefined : t)}>
                <Statistic title={t} value={n} />
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Card size="small" extra={
        <Space>
          <Button icon={<DownloadOutlined />} href="/api/achievements/cv-export">导出 CV 成果列表</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>新增成果</Button>
        </Space>
      }>
        <Table<(Achievement & { synced?: boolean })>
          rowKey={(r) => `${r.synced ? 's' : 'a'}-${r.id}`}
          loading={loading}
          dataSource={list}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 项` }}
          columns={[
            { title: '类型', dataIndex: 'atype', width: 90, render: (t: string) => <Tag color={TYPE_COLORS[t]}>{t}</Tag> },
            {
              title: '标题',
              dataIndex: 'title',
              ellipsis: true,
              render: (v, r) => (
                <Space>
                  {v}
                  {r.synced && <Tag color="blue">自动同步</Tag>}
                </Space>
              ),
            },
            { title: '状态', dataIndex: 'status', width: 100, render: (s: string) => s || '—' },
            { title: '日期', dataIndex: 'date', width: 110, render: (d: string | null) => fmtDate(d) },
            { title: '期刊/机构', dataIndex: 'venue', width: 160, ellipsis: true, render: (v) => v || '—' },
            { title: '编号', dataIndex: 'identifier', width: 150, ellipsis: true, render: (v) => v || '—' },
            {
              title: '附件',
              dataIndex: 'file_name',
              width: 90,
              render: (v, r) => r.synced ? '—' : (
                <Upload
                  showUploadList={false}
                  beforeUpload={(f) => {
                    const fd = new FormData()
                    fd.append('file', f)
                    api.post(`/achievements/${r.id}/attachment`, fd).then(() => {
                      message.success('附件已上传')
                      bump()
                    }).catch((e) => message.error(e.response?.data?.detail ?? '上传失败'))
                    return false
                  }}
                >
                  <Button size="small" type="link" title="上传附件（证书/文档）">
                    {v ? '✓ 替换' : '上传'}
                  </Button>
                </Upload>
              ),
            },
            {
              title: '操作',
              width: 150,
              render: (_, r) => r.synced ? (
                <span style={{ color: '#8a94a3', fontSize: 12 }}>由论文模块管理</span>
              ) : (
                <Space>
                  {r.file_name && <Button size="small" icon={<DownloadOutlined />} href={`/api/achievements/${r.id}/download`} title="下载附件" />}
                  <Button size="small" icon={<EditOutlined />} onClick={() => openModal(r)} />
                  <Popconfirm title="删除该成果？" onConfirm={() => api.delete(`/achievements/${r.id}`).then(() => bump())}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal title={editing ? '编辑成果' : '新增成果'} open={modalOpen} onOk={save} onCancel={() => setModalOpen(false)} width={620} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="atype" label="类型" rules={[{ required: true }]}>
            <Select options={['论文', '专利', '软件', '获奖', '其他'].map((t) => ({ value: t, label: t }))} />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}><Input /></Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={STATUS_OPTIONS.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="date" label="日期"><DatePicker style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="期刊/机构 / 编号">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="venue" noStyle><Input placeholder="期刊 / 机构" style={{ width: '55%' }} /></Form.Item>
              <Form.Item name="identifier" noStyle><Input placeholder="专利号 / 软著号 / DOI" style={{ width: '45%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="authors" label="作者"><Input placeholder="逗号分隔" /></Form.Item>
          <Form.Item name="link" label="链接"><Input addonBefore={<LinkOutlined />} /></Form.Item>
          <Form.Item name="detail" label="描述"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </Space>
        ),
      },
      {
        key: 'timeline',
        label: '成果时间线',
        children: (
          <Card size="small">
            {list.length === 0 ? (
              <Empty description="暂无成果" />
            ) : (
              <Timeline
                items={Object.entries(
                  [...list].sort((a, b) => String(b.date ?? '').localeCompare(String(a.date ?? '')))
                    .reduce<Record<string, (typeof list)[number][]>>((acc, a) => {
                      const year = (a.date ?? '').slice(0, 4) || '未注明年份'
                      acc[year] = acc[year] ?? []
                      acc[year].push(a)
                      return acc
                    }, {}),
                ).map(([year, items]) => ({
                  color: 'blue',
                  children: (
                    <div>
                      <Typography.Text strong style={{ fontSize: 14 }}>{year}</Typography.Text>
                      <div style={{ marginTop: 4 }}>
                        {items.map((a) => (
                          <div key={a.id} style={{ marginBottom: 4 }}>
                            <Tag color="blue" style={{ marginRight: 8 }}>{a.atype}</Tag>
                            {a.title}
                            {a.status && <Tag style={{ marginLeft: 8 }}>{a.status}</Tag>}
                          </div>
                        ))}
                      </div>
                    </div>
                  ),
                }))}
              />
            )}
          </Card>
        ),
      },
    ]} />
  )
}
