import { useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Input, List, message, Popconfirm, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime } from '../utils'
import type { Note } from '../types'

/** 双链语法 [[标题]] → Markdown 链接（跳转全局搜索） */
function linkify(content: string): string {
  return content.replace(/\[\[([^\[\]]+)\]\]/g, '[$1](#wiki:$1)')
}

/** 挂载到 reference（阅读笔记）或 project（实验记录）的 Markdown 笔记面板，支持 [[双链]] */
export default function NotesPanel({ targetType, targetId }: { targetType: string; targetId: number }) {
  const [notes, setNotes] = useState<Note[]>([])
  const [text, setText] = useState('')
  const [editing, setEditing] = useState<Note | null>(null)
  const [mentions, setMentions] = useState<{ type: string; id: number; title: string; link: string }[]>([])
  const nav = useNavigate()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    api.get<Note[]>('/notes', { params: { target_type: targetType, target_id: targetId } })
      .then((r) => {
        setNotes(r.data)
        // 未链接提及（Obsidian Unlinked mentions）：检测最近一条笔记
        if (r.data.length > 0) {
          api.get<{ mentions: { type: string; id: number; title: string; link: string }[] }>(
            '/notes/mentions', { params: { note_id: r.data[0].id } },
          ).then((m) => setMentions(m.data.mentions)).catch(() => setMentions([]))
        } else {
          setMentions([])
        }
      })
      .catch(() => {})
  }
  useEffect(load, [targetType, targetId, refreshKey])

  const save = () => {
    if (!text.trim()) return
    const body = { target_type: targetType, target_id: targetId, content: text }
    const req = editing
      ? api.put(`/notes/${editing.id}`, { content: text })
      : api.post('/notes', body)
    req
      .then(() => {
        message.success(editing ? '笔记已更新' : '笔记已保存')
        setText('')
        setEditing(null)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const startEdit = (n: Note) => {
    setEditing(n)
    setText(n.content)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const remove = (n: Note) => {
    api.delete(`/notes/${n.id}`).then(() => {
      message.success('已删除')
      bump()
    })
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small" title={editing ? `编辑笔记（#${editing.id}）` : '写新笔记（支持 Markdown）'}>
        <Input.TextArea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="支持 Markdown 与 [[双链]]：标题、列表、公式、代码块……"
        />
        {mentions.length > 0 && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 8 }}
            message={
              <span>
                检测到 {mentions.length} 个未链接提及：
                {mentions.slice(0, 5).map((m) => (
                  <Tag key={`${m.type}-${m.id}`} style={{ cursor: 'pointer', marginLeft: 6 }}
                    onClick={() => nav(m.link)}>
                    {m.title}
                  </Tag>
                ))}
              </span>
            }
          />
        )}
        <Space style={{ marginTop: 12 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={save} disabled={!text.trim()}>
            {editing ? '保存修改' : '添加笔记'}
          </Button>
          {editing && (
            <Button
              onClick={() => {
                setEditing(null)
                setText('')
              }}
            >
              取消编辑
            </Button>
          )}
        </Space>
      </Card>

      {notes.length === 0 ? (
        <Empty description="还没有笔记。写下阅读要点或实验记录，支持 Markdown。" style={{ padding: '16px 0' }} />
      ) : (
        <List
          dataSource={notes}
          renderItem={(n) => (
            <Card size="small" key={n.id} style={{ marginBottom: 8 }}>
              <div className="markdown-body">
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => (
                      <a
                        href={href}
                        onClick={(e) => {
                          const m = /^#wiki:(.+)$/.exec(href ?? '')
                          if (m) {
                            e.preventDefault()
                            nav(`/search?q=${encodeURIComponent(m[1])}`)
                          }
                        }}
                      >
                        {children}
                      </a>
                    ),
                  }}
                >
                  {linkify(n.content)}
                </ReactMarkdown>
              </div>
              <Space style={{ marginTop: 8, justifyContent: 'space-between', width: '100%' }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {fmtDateTime(n.updated_at)}
                </Typography.Text>
                <Space>
                  <Button size="small" icon={<EditOutlined />} onClick={() => startEdit(n)}>
                    编辑
                  </Button>
                  <Popconfirm title="删除这条笔记？" onConfirm={() => remove(n)}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              </Space>
            </Card>
          )}
        />
      )}
    </Space>
  )
}
