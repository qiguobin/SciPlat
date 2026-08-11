import { useEffect, useRef, useState } from 'react'
import { Badge, Button, Empty, Popover, Space, Tag, Typography, message } from 'antd'
import { BellOutlined, CheckOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store'

interface NotificationItem {
  id: number
  message: string
  category: string
  target_type: string
  target_id: number | null
  read: boolean
  created_at: string
}

const CATEGORY_COLORS: Record<string, string> = { info: 'default', success: 'green', warning: 'orange' }
const TYPE_LINKS: Record<string, string> = {
  project: '/projects', paper: '/papers', reference: '/references', material: '/materials',
  todo: '/schedule', idea: '/ideas', achievement: '/achievements', note: '/references',
  resource: '/materials', writing: '/papers', canvas: '/canvas',
}

/** 系统通知中心：顶栏铃铛 + 未读 #FF005C 红点 + 操作记录列表 */
export default function NotificationCenter() {
  const nav = useNavigate()
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const pollRef = useRef<number | null>(null)
  const refreshKey = useAppStore((s) => s.refreshKey)

  const load = () => {
    fetch('/api/notifications?limit=20')
      .then((r) => r.json())
      .then((d) => {
        setItems(d.items ?? [])
        setUnread(d.unread ?? 0)
      })
      .catch(() => {})
  }

  useEffect(() => {
    load()
  }, [refreshKey])

  // 轮询未读数（5 秒），操作后即时刷新
  useEffect(() => {
    pollRef.current = window.setInterval(() => {
      fetch('/api/notifications?limit=1').then((r) => r.json()).then((d) => {
        if (d.unread !== undefined) setUnread(d.unread)
      }).catch(() => {})
    }, 5000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  const markRead = (id: number) => {
    fetch(`/api/notifications/${id}/read`, { method: 'POST' }).then(() => load()).catch(() => {})
  }

  const readAll = () => {
    fetch('/api/notifications/read-all', { method: 'POST' })
      .then(() => { message.success('已全部标记为已读'); load() })
      .catch(() => {})
  }

  const go = (n: NotificationItem) => {
    const base = TYPE_LINKS[n.target_type]
    if (!base) return
    if (n.target_type === 'project' && n.target_id) nav(`/projects/${n.target_id}`)
    else if (n.target_type === 'paper' && n.target_id) nav(`/papers/${n.target_id}`)
    else nav(base)
    if (!n.read) markRead(n.id)
    setOpen(false)
  }

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomRight"
      content={
        <div style={{ width: 380, maxHeight: 460, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #1E293B' }}>
            <Typography.Text strong>操作记录（{unread > 0 ? `${unread} 条未读` : '全部已读'}）</Typography.Text>
            {unread > 0 && (
              <Button size="small" type="link" icon={<CheckOutlined />} onClick={readAll}>全部已读</Button>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {items.length === 0 ? (
              <Empty description="暂无操作记录" style={{ padding: '32px 0' }} />
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  onClick={() => go(n)}
                  style={{
                    padding: '10px 12px',
                    borderBottom: '1px solid #16233A',
                    cursor: 'pointer',
                    display: 'flex',
                    gap: 10,
                    alignItems: 'flex-start',
                    background: n.read ? 'transparent' : 'rgba(52, 211, 153, 0.06)',
                  }}
                >
                  <span
                    style={{
                      width: 7, height: 7, borderRadius: '50%', marginTop: 5, flexShrink: 0,
                      background: n.read ? '#334155' : '#FF005C',
                      boxShadow: n.read ? 'none' : '0 0 8px rgba(255, 0, 92, 0.6)',
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: '#E2E8F0' }}>{n.message}</div>
                    <Space size={6} style={{ marginTop: 2 }}>
                      <Tag color={CATEGORY_COLORS[n.category] ?? 'default'} style={{ fontSize: 10, lineHeight: '16px' }}>
                        {n.category === 'success' ? '完成' : n.category === 'warning' ? '变更' : '记录'}
                      </Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'var(--mono)' }}>
                        {n.created_at.slice(5, 16).replace('T', ' ')}
                      </Typography.Text>
                    </Space>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      }
    >
      <Badge count={unread} size="small" color="#FF005C" offset={[-2, 2]}>
        <Button type="text" icon={<BellOutlined />} title="操作记录与通知" />
      </Badge>
    </Popover>
  )
}
