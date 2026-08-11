import { useEffect, useState } from 'react'
import { Card, Empty, Select, Space, Tag, Typography, message } from 'antd'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { Todo } from '../types'

const COLUMNS = [
  { key: '待办', color: 'default' },
  { key: '进行中', color: 'blue' },
  { key: '已完成', color: 'green' },
]
const PRIORITY_COLORS: Record<string, string> = { 高: 'red', 中: 'orange', 低: 'default' }

/** 看板：待办三列拖拽流转（GitHub Projects 模式）；projectId 为空时展示全局全部待办 */
export default function ProjectKanban({ projectId, todoIds }: { projectId?: number; todoIds?: number[] }) {
  const [todos, setTodos] = useState<Todo[]>([])
  const [projectFilter, setProjectFilter] = useState<number | undefined>(projectId)
  const [projects, setProjects] = useState<{ id: number; title: string }[]>([])
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  useEffect(() => {
    api.get<Todo[]>('/todos', { params: { project_id: projectId ?? projectFilter } })
      .then((r) => setTodos(r.data)).catch(() => {})
    api.get<{ id: number; title: string }[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
  }, [projectId, projectFilter, refreshKey])

  const moveTodo = (tid: number, status: string) => {
    api.patch(`/todos/${tid}/status`, { status }).then(() => bump())
      .catch((e) => message.error(e.response?.data?.detail ?? '流转失败'))
  }

  const inPhase = (t: Todo) => (todoIds ?? []).includes(t.id)

  return (
    <div>
      {!projectId && (
        <Select
          allowClear placeholder="全部项目" style={{ width: 220, marginBottom: 12 }}
          value={projectFilter} onChange={setProjectFilter}
          options={projects.map((p) => ({ value: p.id, label: p.title }))}
        />
      )}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, minHeight: 200 }}>
      {COLUMNS.map((col) => (
        <div
          key={col.key}
          style={{
            background: 'rgba(15, 23, 42, 0.4)',
            border: '1px solid #1E293B',
            borderRadius: 8,
            padding: 8,
            minHeight: 160,
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            const tid = Number(e.dataTransfer.getData('text/plain'))
            if (tid) moveTodo(tid, col.key)
          }}
        >
          <div style={{ marginBottom: 8 }}>
            <Tag color={col.color}>{col.key}</Tag>
            <span style={{ fontSize: 12, color: '#64748B' }}>
              {todos.filter((t) => t.status === col.key).length}
            </span>
          </div>
          {todos.filter((t) => t.status === col.key).length === 0 ? (
            <Empty description="" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '20px 0' }} />
          ) : (
            todos.filter((t) => t.status === col.key).map((t) => (
              <Card
                key={t.id}
                size="small"
                draggable
                style={{ marginBottom: 8, cursor: 'grab' }}
                onDragStart={(e) => e.dataTransfer.setData('text/plain', String(t.id))}
              >
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</span>
                    <Tag color={PRIORITY_COLORS[t.priority]} style={{ marginInlineEnd: 0 }}>{t.priority}</Tag>
                  </div>
                  <Space size={6}>
                    <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'var(--mono)' }}>{t.date}</Typography.Text>
                    {inPhase(t) && <Tag color="green" style={{ fontSize: 10 }}>阶段关联</Tag>}
                    {t.repeat !== 'none' && <Tag style={{ fontSize: 10 }}>♻</Tag>}
                  </Space>
                  {t.status !== '已完成' && (
                    <Select
                      size="small" value={t.status} style={{ width: '100%', marginTop: 4 }}
                      onChange={(v) => moveTodo(t.id, v)}
                      options={['待办', '进行中', '已完成'].map((s) => ({ value: s, label: s }))}
                    />
                  )}
                </Space>
              </Card>
            ))
          )}
        </div>
      ))}
    </div>
    </div>
  )
}
