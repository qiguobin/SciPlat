import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Card, Empty, List, Space, Tag, Typography } from 'antd'
import { api } from '../api/client'
import { PAPER_STATUS } from '../components/StatusTag'
import type { SearchResults } from '../types'

export default function Search() {
  const [params] = useSearchParams()
  const q = params.get('q') ?? ''
  const nav = useNavigate()
  const [data, setData] = useState<SearchResults | null>(null)

  useEffect(() => {
    if (!q) return
    api.get<SearchResults>('/search', { params: { q } }).then((r) => setData(r.data)).catch(() => {})
  }, [q])

  if (!q) return <Card><Empty description="请输入搜索关键词" /></Card>
  if (!data) return <Card loading />

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Typography.Text type="secondary">
        「{q}」的搜索结果（每个类别最多 5 条）
      </Typography.Text>

      <Card size="small" title="项目">
        <List
          size="small"
          dataSource={data.projects}
          locale={{ emptyText: '没有找到相关内容，换个关键词试试' }}
          renderItem={(p) => (
            <List.Item onClick={() => nav(`/projects/${p.id}`)} style={{ cursor: 'pointer' }}>
              <Typography.Text strong>{p.title}</Typography.Text>
              <Tag>{p.status}</Tag>
            </List.Item>
          )}
        />
      </Card>

      <Card size="small" title="论文">
        <List
          size="small"
          dataSource={data.papers}
          locale={{ emptyText: '没有找到相关内容，换个关键词试试' }}
          renderItem={(p) => (
            <List.Item onClick={() => nav(`/papers/${p.id}`)} style={{ cursor: 'pointer' }}>
              <Typography.Text strong>{p.title}</Typography.Text>
              <Tag color={PAPER_STATUS[p.status]?.color}>{PAPER_STATUS[p.status]?.label ?? p.status}</Tag>
            </List.Item>
          )}
        />
      </Card>

      <Card size="small" title="材料">
        <List
          size="small"
          dataSource={data.materials}
          locale={{ emptyText: '没有找到相关内容，换个关键词试试' }}
          renderItem={(m) => (
            <List.Item onClick={() => nav('/materials')} style={{ cursor: 'pointer' }}>
              <Typography.Text strong>{m.name}</Typography.Text>
              <Tag>{m.category}</Tag>
            </List.Item>
          )}
        />
      </Card>

      <Card size="small" title="文献">
        <List
          size="small"
          dataSource={data.references}
          locale={{ emptyText: '没有找到相关内容，换个关键词试试' }}
          renderItem={(r) => (
            <List.Item onClick={() => nav('/references')} style={{ cursor: 'pointer' }}>
              <Typography.Text strong>{r.title}</Typography.Text>
              <Tag>{r.read_status}</Tag>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  )
}
