import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Empty, Form, Input, List, message, Modal as ModalComponent, Popconfirm, Select, Space, Switch, Tag, Typography,
} from 'antd'
import { DeleteOutlined, LinkOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate } from '../utils'
import { trackerTldr } from '../utils/tldr'

interface TrackingSource {
  id: number
  name: string
  stype: string
  query: string
  active: boolean
  item_count: number
  last_fetched_at: string | null
  last_error: string
}

interface TrackingItem {
  id: number
  source_id: number
  title: string
  authors: string[]
  abstract: string
  link: string
  published: string | null
  is_new: boolean
}

const STYPE_LABELS: Record<string, string> = {
  arxiv_keyword: 'arXiv 关键词', arxiv_category: 'arXiv 分类', rss: 'RSS 源',
}

/** 科研动态追踪：arXiv + RSS 双源订阅，最新论文流 */
export default function TrackingPage() {
  const [sources, setSources] = useState<TrackingSource[]>([])
  const [items, setItems] = useState<TrackingItem[]>([])
  const [sourceFilter, setSourceFilter] = useState<number | undefined>()
  const [fetching, setFetching] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [form] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    api.get<TrackingSource[]>('/tracking/sources').then((r) => setSources(r.data)).catch(() => {})
    api.get<TrackingItem[]>('/tracking/items', { params: { source_id: sourceFilter, days: 14, limit: 40 } })
      .then((r) => setItems(r.data)).catch(() => {})
  }
  useEffect(load, [refreshKey, sourceFilter])

  const manualFetch = () => {
    setFetching(true)
    api.post('/tracking/fetch', {})
      .then((r) => {
        message.success(`抓取完成：新增 ${r.data.new_items ?? 0} 条`)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '抓取失败'))
      .finally(() => setFetching(false))
  }

  const addSource = () => {
    form.validateFields().then((v) => {
      api.post('/tracking/sources', v).then(() => {
        message.success('订阅已添加')
        setAddOpen(false)
        form.resetFields()
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '添加失败'))
    })
  }

  const toLibrary = (item: TrackingItem) => {
    api.post(`/tracking/items/${item.id}/to-library`)
      .then((r) => {
        if (r.data.already_exists) message.info('文献库中已存在该条目')
        else message.success('已加入文献库（去文献页查看）')
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '入库失败'))
  }

  const activeCount = sources.filter((s) => s.active).length

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {/* 概览 + 操作 */}
      <Card size="small">
        <Space wrap>
          <Tag color="green">活跃订阅 {activeCount}/{sources.length}</Tag>
          <Tag color="blue">近 14 天条目 {items.length}</Tag>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加订阅</Button>
          <Button icon={<ReloadOutlined />} loading={fetching} onClick={manualFetch}>立即抓取</Button>
          <Select
            placeholder="按订阅筛选" allowClear style={{ width: 200 }} value={sourceFilter}
            onChange={setSourceFilter}
            options={sources.map((s) => ({ value: s.id, label: s.name }))}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            每 6 小时自动抓取，新条目自动进入系统通知
          </Typography.Text>
        </Space>
      </Card>

      {/* 订阅源管理 */}
      <Card size="small" title={<span className="section-title">订阅源（{sources.length}）</span>}>
        {sources.length === 0 ? (
          <Empty description="暂无订阅" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            size="small"
            dataSource={sources}
            renderItem={(s) => (
              <List.Item
                actions={[
                  <Switch key="sw" size="small" checked={s.active}
                    onChange={(v) => api.put(`/tracking/sources/${s.id}`, { active: v }).then(() => bump())} />,
                  <Popconfirm key="d" title="删除该订阅？" onConfirm={() => api.delete(`/tracking/sources/${s.id}`).then(() => bump())}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>,
                ]}
              >
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Space>
                    <Tag color={s.active ? 'green' : 'default'}>{s.active ? '启用' : '停用'}</Tag>
                    <Tag>{STYPE_LABELS[s.stype]}</Tag>
                    <Typography.Text strong>{s.name}</Typography.Text>
                    <Tag>{s.item_count} 条</Tag>
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                    {s.query}
                    {s.last_fetched_at && ` · 上次抓取 ${fmtDate(s.last_fetched_at.slice(0, 10))}`}
                  </Typography.Text>
                  {s.last_error && (
                    <Typography.Text type="danger" style={{ fontSize: 11 }}>⚠ {s.last_error}</Typography.Text>
                  )}
                </Space>
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 论文流 */}
      <Card size="small" title={<span className="section-title">最新论文与动态</span>}>
        {items.length === 0 ? (
          <Empty description="暂无条目。添加订阅后点击「立即抓取」，或等待自动抓取。" />
        ) : (
          <List
            dataSource={items}
            renderItem={(item) => (
              <Card size="small" style={{ marginBottom: 10 }} key={item.id}>
                <Space direction="vertical" style={{ width: '100%' }} size={4}>
                  <Space wrap>
                    {item.is_new && <Tag color="#FF005C" style={{ color: '#fff', borderColor: '#FF005C' }}>新</Tag>}
                    <Typography.Text strong>{item.title}</Typography.Text>
                  </Space>
                  <Space size={8} wrap>
                    <Tag style={{ fontSize: 11 }}>{sources.find((s) => s.id === item.source_id)?.name ?? '来源'}</Tag>
                    {item.published && (
                      <Typography.Text type="secondary" style={{ fontSize: 12, fontFamily: 'var(--mono)' }}>
                        {item.published}
                      </Typography.Text>
                    )}
                    {item.authors.length > 0 && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {item.authors.slice(0, 3).join(', ')}{item.authors.length > 3 ? ' 等' : ''}
                      </Typography.Text>
                    )}
                  </Space>
                  {item.abstract && (
                    <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 0 }} ellipsis={{ rows: 3 }}>
                      {trackerTldr(item.abstract)}
                    </Typography.Paragraph>
                  )}
                  <Space>
                    <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => toLibrary(item)}>
                      加入文献库
                    </Button>
                    {item.link && (
                      <Button size="small" icon={<LinkOutlined />} href={item.link} target="_blank">原文</Button>
                    )}
                  </Space>
                </Space>
              </Card>
            )}
          />
        )}
      </Card>

      {/* 添加订阅弹窗 */}
      <ModalAdd
        open={addOpen}
        form={form}
        onCancel={() => setAddOpen(false)}
        onOk={addSource}
      />
    </Space>
  )
}

function ModalAdd({ open, form, onCancel, onOk }: {
  open: boolean
  form: ReturnType<typeof Form.useForm>[0]
  onCancel: () => void
  onOk: () => void
}) {
  return (
    <ModalComponent
      title="添加订阅源"
      open={open}
      onCancel={onCancel}
      onOk={onOk}
      okText="添加"
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="如：我的方向新论文" />
        </Form.Item>
        <Form.Item name="stype" label="类型" initialValue="arxiv_category">
          <Select options={[
            { value: 'arxiv_category', label: 'arXiv 分类（如 cat:cs.AI）' },
            { value: 'arxiv_keyword', label: 'arXiv 关键词（如 all:"graph neural network"）' },
            { value: 'rss', label: 'RSS 源（输入 URL）' },
          ]} />
        </Form.Item>
        <Form.Item name="query" label="查询内容 / RSS URL" rules={[{ required: true, message: '请输入查询或 URL' }]}>
          <Input placeholder="cat:cs.LG 或 all:protein folding 或 https://…rss" />
        </Form.Item>
        <Form.Item name="active" label="启用" initialValue={true}>
          <Switch />
        </Form.Item>
      </Form>
    </ModalComponent>
  )
}