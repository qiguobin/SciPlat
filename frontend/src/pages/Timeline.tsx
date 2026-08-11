import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Checkbox, Empty, List, Space, Tag, Typography } from 'antd'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { TimelineEvent } from '../types'

const TYPE_META: Record<string, { label: string; color: string }> = {
  phase: { label: '阶段', color: 'blue' },
  milestone: { label: '里程碑', color: 'green' },
  deadline: { label: '期刊截稿', color: 'red' },
  todo: { label: '待办', color: 'default' },
}

const STATUS_COLORS: Record<string, string> = {
  已完成: 'green', 进行中: 'blue', 未开始: 'default', 延期: 'red',
}

/** 全局时间线：项目阶段 + 里程碑 + 期刊截稿 + 待办 */
export default function TimelinePage() {
  const nav = useNavigate()
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [kinds, setKinds] = useState<Set<string>>(new Set(['phase', 'milestone', 'deadline', 'todo']))
  const refreshKey = useAppStore((s) => s.refreshKey)

  useEffect(() => {
    api.get<{ events: TimelineEvent[] }>('/schedule/timeline', { params: { kinds: [...kinds].join(',') } })
      .then((r) => setEvents(r.data.events)).catch(() => {})
  }, [kinds, refreshKey])

  const groups = useMemo(() => {
    const m = new Map<string, TimelineEvent[]>()
    events.forEach((e) => {
      const key = e.date.slice(0, 7)
      m.set(key, [...(m.get(key) ?? []), e])
    })
    return [...m.entries()]
  }, [events])

  const toggleKind = (k: string, checked: boolean) => {
    const next = new Set(kinds)
    if (checked) next.add(k)
    else next.delete(k)
    setKinds(next)
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          {Object.entries(TYPE_META).map(([k, meta]) => (
            <Checkbox key={k} checked={kinds.has(k)} onChange={(e) => toggleKind(k, e.target.checked)}>
              <Tag color={meta.color} style={{ marginInlineEnd: 0 }}>{meta.label}</Tag>
            </Checkbox>
          ))}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            共 {events.length} 个事件 · 未来 1 年 + 过去 90 天
          </Typography.Text>
        </Space>
      </Card>

      {groups.length === 0 ? (
        <Card><Empty description="所选范围内暂无事件" /></Card>
      ) : (
        groups.map(([month, items]) => (
          <Card key={month} size="small" title={<span className="section-title">{month}</span>}>
            <List
              size="small"
              dataSource={items}
              renderItem={(e) => {
                const meta = TYPE_META[e.type]
                return (
                  <List.Item onClick={() => nav(e.link)} style={{ cursor: 'pointer', paddingInline: 8 }}>
                    <Space>
                      <Tag color={meta.color} style={{ width: 74, textAlign: 'center', marginInlineEnd: 4 }}>{meta.label}</Tag>
                      <Typography.Text strong>{e.title}</Typography.Text>
                      <Tag color={STATUS_COLORS[e.status] ?? 'default'}>{e.status}</Tag>
                    </Space>
                    <Typography.Text type="secondary">{e.date}</Typography.Text>
                  </List.Item>
                )
              }}
            />
          </Card>
        ))
      )}
    </Space>
  )
}
