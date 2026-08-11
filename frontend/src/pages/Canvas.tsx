import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Input, Modal, Popconfirm, Select, Space, Tag, Typography, message } from 'antd'
import { LinkOutlined, PlusOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { CanvasData, CanvasEdge, CanvasNode } from '../types'

const NODE_COLORS: Record<string, string> = {
  project: '#38BDF8', experiment: '#34D399', idea: '#FBBF24',
  reference: '#A78BFA', note: '#F9A8D4', text: '#64748B',
}
const NODE_LABELS: Record<string, string> = {
  project: '项目', experiment: '实验', idea: '灵感', reference: '文献', note: '笔记', text: '文本',
}
const NODE_LINKS: Record<string, (id: number) => string> = {
  project: (id) => `/projects/${id}`,
  experiment: () => '/projects',
  idea: () => '/ideas',
  reference: () => '/references',
  note: () => '/',
  text: () => '/',
}

/** 科研画布（Obsidian Canvas）：拖拽节点 + 连线 + 双击加文本卡 */
export default function CanvasPage() {
  const nav = useNavigate()
  const wrapRef = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<CanvasData>({ nodes: [], edges: [] })
  const [connectFrom, setConnectFrom] = useState<number | null>(null)
  const [textModal, setTextModal] = useState(false)
  const [textTitle, setTextTitle] = useState('')
  const [addSel, setAddSel] = useState<number | undefined>()
  const canvasPosRef = useRef<{ x: number; y: number } | null>(null)
  const [addType, setAddType] = useState('project')
  const [projects, setProjects] = useState<{ id: number; title: string }[]>([])
  const [ideas, setIdeas] = useState<{ id: number; content: string }[]>([])
  const [refs, setRefs] = useState<{ id: number; title: string }[]>([])
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  useEffect(() => {
    api.get<CanvasData>('/canvas').then((r) => setData(r.data)).catch(() => {})
    api.get<{ id: number; title: string }[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
    api.get<{ id: number; content: string }[]>('/ideas').then((r) => setIdeas(r.data)).catch(() => {})
    api.get<{ id: number; title: string }[]>('/references').then((r) => setRefs(r.data)).catch(() => {})
  }, [refreshKey])

  /** 拖拽移动节点 */
  const startDrag = (e: React.PointerEvent, node: CanvasNode) => {
    e.preventDefault()
    const startX = e.clientX - node.x
    const startY = e.clientY - node.y
    const onMove = (ev: PointerEvent) => {
      api.put(`/canvas/nodes/${node.id}`, { x: ev.clientX - startX, y: ev.clientY - startY }).catch(() => {})
      setData((d) => ({
        ...d,
        nodes: d.nodes.map((n) => (n.id === node.id ? { ...n, x: ev.clientX - startX, y: ev.clientY - startY } : n)),
      }))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  /** 双击空白：添加文本卡 */
  const addTextAt = (e: React.MouseEvent) => {
    if (e.target !== wrapRef.current) return
    const rect = wrapRef.current.getBoundingClientRect()
    setTextModal(true)
    setTextTitle('')
    canvasPosRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const createTextNode = () => {
    if (!textTitle.trim()) return
    const pos = canvasPosRef.current ?? { x: 100, y: 100 }
    api.post('/canvas/nodes', { ntype: 'text', title: textTitle.trim(), x: pos.x, y: pos.y })
      .then(() => {
        setTextModal(false)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '创建失败，请刷新后重试'))
  }

  const addObject = () => {
    if (addSel === undefined) { message.warning('请选择对象'); return }
    const item = addType === 'project' ? projects.find((p) => p.id === addSel)
      : addType === 'idea' ? ideas.find((i) => i.id === addSel)
        : refs.find((r) => r.id === addSel)
    if (!item) return
    const title = addType === 'idea' ? (item as { content: string }).content : (item as { title: string }).title
    const offset = 30 + data.nodes.length * 25
    api.post('/canvas/nodes', {
      ntype: addType, title: title.slice(0, 80), ref_id: addSel,
      x: 80 + (data.nodes.length % 5) * 220, y: 80 + offset,
    }).then(() => { setAddSel(undefined); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '加入画布失败'))
  }

  const nodeCenter = (id: number) => {
    const n = data.nodes.find((x) => x.id === id)
    return n ? { x: n.x + n.w / 2, y: n.y + n.h / 2 } : { x: 0, y: 0 }
  }

  return (
    <div>
      {/* 工具栏 */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <span style={{ fontSize: 12, color: '#94A3B8' }}>双击空白添加文本卡 · 拖动卡片移动 · 点击 🔗 再点另一张卡连线</span>
          <Select
            style={{ width: 120 }} value={addType} onChange={setAddType}
            options={['project', 'idea', 'reference'].map((t) => ({ value: t, label: NODE_LABELS[t] }))}
          />
          <Select
            style={{ width: 200 }} placeholder="选择对象加入画布" showSearch optionFilterProp="label"
            value={addSel} onChange={setAddSel}
            options={
              addType === 'project' ? projects.map((p) => ({ value: p.id, label: p.title }))
                : addType === 'idea' ? ideas.map((i) => ({ value: i.id, label: i.content.slice(0, 40) }))
                  : refs.map((r) => ({ value: r.id, label: r.title }))
            }
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={addObject}>加入画布</Button>
        </Space>
      </Card>

      {/* 画布 */}
      <div
        ref={wrapRef}
        onClick={addTextAt}
        style={{
          position: 'relative', height: '72vh', overflow: 'hidden',
          background: 'rgba(11, 17, 32, 0.6)', border: '1px solid #1E293B', borderRadius: 8,
        }}
      >
        <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          {data.edges.map((e) => {
            const a = nodeCenter(e.from_node)
            const b = nodeCenter(e.to_node)
            return <line key={e.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#34D399" strokeWidth={1.5} strokeDasharray="4 3" opacity={0.6} />
          })}
        </svg>

        {data.nodes.map((n) => (
          <div
            key={n.id}
            onPointerDown={(e) => startDrag(e, n)}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => {
              e.stopPropagation()
              const link = NODE_LINKS[n.ntype]?.(n.ref_id ?? n.id)
              if (link && n.ntype !== 'text') nav(link)
            }}
            style={{
              position: 'absolute', left: n.x, top: n.y, width: n.w, minHeight: n.h,
              background: 'rgba(15, 23, 42, 0.92)', border: `1px solid ${NODE_COLORS[n.ntype]}`,
              borderRadius: 8, padding: '8px 10px', cursor: 'grab', zIndex: 2,
              boxShadow: '0 4px 12px rgba(0,0,0,0.4)', userSelect: 'none',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <Tag color={NODE_COLORS[n.ntype]} style={{ fontSize: 10 }}>{NODE_LABELS[n.ntype]}</Tag>
              <Space size={2}>
                <Button
                  size="small" type="text" icon={<LinkOutlined />} style={{ fontSize: 11 }}
                  onClick={() => {
                    if (connectFrom === null) setConnectFrom(n.id)
                    else if (connectFrom !== n.id) {
                      api.post('/canvas/edges', { from_node: connectFrom, to_node: n.id })
                        .then(() => bump())
                        .catch((e) => message.error(e.response?.data?.detail ?? '连线失败'))
                      setConnectFrom(null)
                    }
                  }}
                  title={connectFrom === null ? '连线' : '连接到这张卡'}
                />
                <Popconfirm title="删除该节点？" onConfirm={() => api.delete(`/canvas/nodes/${n.id}`).then(() => bump())}>
                  <Button size="small" type="text" danger style={{ fontSize: 11 }}>✕</Button>
                </Popconfirm>
              </Space>
            </div>
            <Typography.Text strong style={{ fontSize: 13, color: '#E2E8F0' }}>{n.title}</Typography.Text>
            {connectFrom === n.id && (
              <div style={{ color: '#34D399', fontSize: 11, marginTop: 4 }}>等待连接目标…</div>
            )}
          </div>
        ))}
      </div>

      {/* 文本卡弹窗 */}
      <Modal title="添加文本卡" open={textModal} onOk={createTextNode} onCancel={() => setTextModal(false)} width={400} destroyOnClose>
        <Input placeholder="卡片内容" value={textTitle} onChange={(e) => setTextTitle(e.target.value)} onPressEnter={createTextNode} autoFocus />
      </Modal>
    </div>
  )
}
