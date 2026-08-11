import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Input, Popconfirm, Select, Space, Spin, Tag, Typography, message } from 'antd'
import {
  DeleteOutlined, EditOutlined, HighlightOutlined, LeftOutlined, QuestionCircleOutlined,
  RightOutlined, TranslationOutlined,
} from '@ant-design/icons'
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { PdfAnnotation } from '../types'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

const COLORS = [
  { value: '#FDE047', label: '荧光黄' },
  { value: '#4ADE80', label: '荧光绿' },
  { value: '#F9A8D4', label: '荧光粉' },
]

interface Rect { x: number; y: number; w: number; h: number }

/** PDF 阅读器：PDF 分页 + 框选高亮 + 文本视图（划词翻译/随手记/高亮）+ AI 问答 */
export default function PdfReader({ referenceId }: { referenceId: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayRef = useRef<SVGSVGElement>(null)
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [annotations, setAnnotations] = useState<PdfAnnotation[]>([])
  const [color, setColor] = useState('#FDE047')
  const [drawing, setDrawing] = useState<Rect | null>(null)
  const [viewSize, setViewSize] = useState({ w: 0, h: 0 })
  const [noteTarget, setNoteTarget] = useState<PdfAnnotation | null>(null)
  const [noteText, setNoteText] = useState('')
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const [pendingNote, setPendingNote] = useState<Rect | null>(null)
  const [view, setView] = useState<'pdf' | 'ai'>('pdf')
  const [textInfo, setTextInfo] = useState<{ text: string; summary: string } | null>(null)
  const [selection, setSelection] = useState('')
  const [translation, setTranslation] = useState('')
  const [translating, setTranslating] = useState(false)
  const [qaInput, setQaInput] = useState('')
  const [qaHistory, setQaHistory] = useState<{ id: number; role: string; content: string }[]>([])
  const [qaLoading, setQaLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const chatEndRef = useRef<HTMLDivElement>(null)
  const bump = useAppStore((s) => s.bump)

  const load = useCallback(() => {
    setLoading(true)
    pdfjsLib.getDocument({ url: `/api/references/${referenceId}/read` }).promise
      .then((doc) => { setPdf(doc); setPage(1); return doc })
      .catch(() => message.error('PDF 加载失败'))
      .finally(() => setLoading(false))
    api.get<PdfAnnotation[]>(`/references/${referenceId}/annotations`)
      .then((r) => setAnnotations(r.data)).catch(() => {})
  }, [referenceId])

  useEffect(load, [load])

  // 全文文本（文本视图 + AI 问答）
  useEffect(() => {
    api.get<{ text: string; summary: string }>(`/references/${referenceId}/text`)
      .then((r) => setTextInfo(r.data)).catch(() => setTextInfo(null))
    // 对话历史（持久化，重开阅读器自动恢复）
    api.get<{ id: number; role: string; content: string }[]>(`/references/${referenceId}/chat`)
      .then((r) => setQaHistory(r.data))
      .catch(() => setQaHistory([]))
  }, [referenceId])

  // 新消息自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [qaHistory.length])

  // 渲染当前页
  useEffect(() => {
    if (!pdf) return
    let cancelled = false
    pdf.getPage(page).then(async (pg) => {
      const canvas = canvasRef.current
      if (!canvas || cancelled) return
      const container = canvas.parentElement!
      const targetW = Math.min(container.clientWidth - 8, 900)
      const scale = targetW / pg.getViewport({ scale: 1 }).width
      const viewport = pg.getViewport({ scale })
      canvas.width = viewport.width
      canvas.height = viewport.height
      setViewSize({ w: viewport.width, h: viewport.height })
      const ctx = canvas.getContext('2d')!
      await pg.render({ canvas: canvas, viewport }).promise
    }).catch(() => message.error('页面渲染失败'))
    return () => { cancelled = true }
  }, [pdf, page])

  const toSvg = (r: Rect): Rect => ({
    x: r.x * viewSize.w, y: r.y * viewSize.h, w: r.w * viewSize.w, h: r.h * viewSize.h,
  })
  const fromSvg = (r: Rect): Rect => ({
    x: r.x / viewSize.w, y: r.y / viewSize.h, w: r.w / viewSize.w, h: r.h / viewSize.h,
  })

  // 框选高亮
  const onPointerDown = (e: React.PointerEvent) => {
    if (noteTarget) return
    const rect = overlayRef.current!.getBoundingClientRect()
    dragRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return
    const rect = overlayRef.current!.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setDrawing({
      x: Math.min(dragRef.current.x, x), y: Math.min(dragRef.current.y, y),
      w: Math.abs(x - dragRef.current.x), h: Math.abs(y - dragRef.current.y),
    })
  }
  const onPointerUp = () => {
    if (!dragRef.current || !drawing || drawing.w < 8 || drawing.h < 4) {
      dragRef.current = null; setDrawing(null); return
    }
    dragRef.current = null
    setPendingNote(drawing)
    setDrawing(null)
  }

  const confirmPending = () => {
    if (!pendingNote) return
    const r = fromSvg(pendingNote)
    api.post(`/references/${referenceId}/annotations`, {
      page, color, rect: `${r.x.toFixed(4)},${r.y.toFixed(4)},${r.w.toFixed(4)},${r.h.toFixed(4)}`, note: noteText,
    }).then(() => {
      message.success('已添加高亮'); setPendingNote(null); setNoteText(''); load()
    }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  /* ---------- 文本视图：划词操作 ---------- */
  const onTextSelect = () => {
    const sel = window.getSelection()?.toString().trim() ?? ''
    if (sel && sel.length > 2 && sel.length < 3000) setSelection(sel)
  }

  const translateSelection = () => {
    if (!selection) return
    setTranslating(true); setAiError('')
    api.post('/llm/chat', {
      system: '你是学术翻译助手。将用户文本翻译为中文（若原文为中文则译为英文），保留专业术语。只输出译文。',
      messages: [{ role: 'user', content: selection }],
    }).then((r) => setTranslation(r.data.reply))
      .catch((e) => { setAiError(e.response?.data?.detail ?? '翻译失败'); setTranslation('') })
      .finally(() => setTranslating(false))
  }

  const saveSelectionNote = () => {
    if (!selection) return
    api.post('/notes', {
      target_type: 'reference', target_id: referenceId,
      content: `## 随手记（划词）\n\n> ${selection}\n\n${new Date().toISOString().slice(0, 10)}`,
    }).then(() => { message.success('已存入文献笔记'); setSelection(''); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const highlightSelection = () => {
    if (!selection) return
    // text 类型高亮：rect 字段存选中文本
    api.post(`/references/${referenceId}/annotations`, {
      page, color, rect: `TEXT:${selection.slice(0, 2000)}`, note: selection.slice(0, 100),
    }).then(() => { message.success('已高亮'); setSelection(''); load() })
      .catch((e) => message.error(e.response?.data?.detail ?? '高亮失败'))
  }

  /** AI 对话式精读：后端注入全文上下文 + 历史，问答持久化 */
  const askAI = () => {
    if (!qaInput.trim()) return
    setAiError('')
    const question = qaInput
    setQaInput('')
    setQaLoading(true)
    // 临时 id（负数）避免与历史冲突，刷新后由服务端真实 id 取代
    setQaHistory((h) => [...h, { id: -Date.now(), role: 'user', content: question }])
    api.post(`/references/${referenceId}/chat`, { question })
      .then((r) => setQaHistory((h) => [...h, { id: -Date.now() - 1, role: 'assistant', content: r.data.reply }]))
      .catch((e) => setAiError(e.response?.data?.detail ?? '问答失败'))
      .finally(() => setQaLoading(false))
  }

  const clearChat = () => {
    api.delete(`/references/${referenceId}/chat`)
      .then(() => { setQaHistory([]); message.success('对话已清空') })
      .catch((e) => message.error(e.response?.data?.detail ?? '清空失败'))
  }

  /* ---------- AI 视图（文本 + 划词 + 问答） ---------- */
  const renderAiView = () => (
    <div>
      {selection && (
        <div style={{ marginBottom: 10, padding: 10, background: 'rgba(52,211,153,0.08)', borderRadius: 6 }}>
          <Space wrap>
            <span style={{ fontSize: 12, color: '#94A3B8' }}>已选中：{selection.slice(0, 60)}…</span>
            <Button size="small" icon={<TranslationOutlined />} loading={translating} onClick={translateSelection}>翻译</Button>
            <Button size="small" icon={<EditOutlined />} onClick={saveSelectionNote}>随手记</Button>
            <Button size="small" icon={<HighlightOutlined />} onClick={highlightSelection}>高亮标记</Button>
            <Button size="small" onClick={() => setSelection('')}>取消</Button>
          </Space>
          {translation && (
            <div style={{ marginTop: 8, fontSize: 13, color: '#E2E8F0' }}>译文：{translation}</div>
          )}
        </div>
      )}
      <div
        style={{ maxHeight: 380, overflow: 'auto', background: 'rgba(11,17,32,0.6)', borderRadius: 6, padding: 12, fontSize: 13, lineHeight: 1.8 }}
        onMouseUp={onTextSelect}
      >
        {textInfo ? textInfo.text : '（暂无提取文本。请先在文献页执行「提取全文文本」后重试，或使用 PDF 阅读模式框选高亮。）'}
      </div>
      <div style={{ marginTop: 12 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Typography.Text strong>AI 对话精读（历史自动保存，重开恢复）</Typography.Text>
          <Popconfirm title="清空该文献的对话历史？" onConfirm={clearChat}>
            <Button size="small" danger icon={<DeleteOutlined />}>清空对话</Button>
          </Popconfirm>
        </Space>
        <Space style={{ marginTop: 6, width: '100%' }}>
          <Input
            placeholder="如：本文的核心创新点是什么？"
            value={qaInput}
            onChange={(e) => setQaInput(e.target.value)}
            onPressEnter={askAI}
            style={{ flex: 1 }}
          />
          <Button type="primary" icon={<QuestionCircleOutlined />} loading={qaLoading} onClick={askAI}>提问</Button>
        </Space>
        {aiError && <div style={{ color: '#F87171', fontSize: 12, marginTop: 6 }}>⚠ {aiError}</div>}
        <div style={{ marginTop: 10, maxHeight: 300, overflow: 'auto', paddingRight: 4 }}>
          {qaHistory.length === 0 && !qaLoading && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>还没有提问。基于全文与历史的多轮问答，回答会自动保存。</Typography.Text>
          )}
          {qaHistory.map((q) => (
            <div key={q.id} style={{ marginBottom: 10, fontSize: 13, display: 'flex', gap: 8 }}>
              <Tag color={q.role === 'user' ? 'blue' : 'green'} style={{ fontSize: 10, flexShrink: 0, marginInlineEnd: 0 }}>
                {q.role === 'user' ? '我' : 'AI'}
              </Tag>
              <span style={{ color: q.role === 'user' ? '#E2E8F0' : '#A7F3D0', whiteSpace: 'pre-wrap', flex: 1 }}>
                {q.content}
              </span>
            </div>
          ))}
          {qaLoading && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Tag color="green" style={{ fontSize: 10, flexShrink: 0, marginInlineEnd: 0 }}>AI</Tag>
              <Spin size="small" /><span style={{ color: '#64748B', fontSize: 12 }}>思考中…</span>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
      </div>
    </div>
  )

  /* ---------- PDF 视图 ---------- */
  const renderPdfView = () => (
    <div>
      <Space style={{ marginBottom: 10 }} wrap>
        <Button size="small" icon={<LeftOutlined />} disabled={page <= 1} onClick={() => setPage((p) => p - 1)} />
        <span style={{ fontFamily: 'var(--mono)', color: '#94A3B8' }}>{page} / {pdf?.numPages ?? '—'}</span>
        <Button size="small" icon={<RightOutlined />} disabled={!pdf || page >= pdf.numPages} onClick={() => setPage((p) => p + 1)} />
        <span style={{ color: '#64748B', fontSize: 12, marginLeft: 8 }}>框选文字区域即可高亮</span>
        <Select size="small" value={color} onChange={setColor} style={{ width: 110 }}
          options={COLORS.map((c) => ({ value: c.value, label: c.label }))} />
      </Space>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
      ) : (
        <div style={{ position: 'relative', overflow: 'auto', maxHeight: '58vh', background: '#0B1120', borderRadius: 6 }}>
          <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: 'auto' }} />
          <svg
            ref={overlayRef}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', cursor: 'crosshair', touchAction: 'none' }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            {annotations.filter((a) => a.page === page).map((a) => {
              const isText = a.rect.startsWith('TEXT:')
              if (isText) return null
              const [x, y, w, h] = a.rect.split(',').map(Number)
              return (
                <g key={a.id} onClick={(e) => { e.stopPropagation(); setNoteTarget(a); setNoteText(a.note) }} style={{ cursor: 'pointer' }}>
                  <rect x={x * viewSize.w} y={y * viewSize.h} width={w * viewSize.w} height={h * viewSize.h}
                    fill={a.color} fillOpacity={0.4} stroke={a.color} strokeWidth={1.5} />
                </g>
              )
            })}
            {drawing && (
              <rect x={drawing.x} y={drawing.y} width={drawing.w} height={drawing.h}
                fill={color} fillOpacity={0.35} stroke={color} strokeWidth={1.5} strokeDasharray="4 3" />
            )}
          </svg>
        </div>
      )}
      {pendingNote && (
        <Space style={{ marginTop: 10 }} wrap>
          <Input placeholder="高亮备注（可选）" value={noteText} onChange={(e) => setNoteText(e.target.value)}
            style={{ width: 320 }} onPressEnter={confirmPending} />
          <Button type="primary" size="small" onClick={confirmPending}>保存高亮</Button>
          <Button size="small" onClick={() => { setPendingNote(null); setNoteText('') }}>取消</Button>
        </Space>
      )}
      {noteTarget && (
        <Space style={{ marginTop: 10 }} wrap>
          <Input placeholder="编辑备注" value={noteText} onChange={(e) => setNoteText(e.target.value)} style={{ width: 320 }} />
          <Button size="small" type="primary" onClick={() => {
            api.put(`/references/annotations/${noteTarget.id}`, { note: noteText }).then(() => {
              message.success('备注已更新'); setNoteTarget(null); load()
            })
          }}>保存</Button>
          <Popconfirm title="删除该高亮？" onConfirm={() => {
            api.delete(`/references/annotations/${noteTarget.id}`).then(() => { message.success('已删除'); setNoteTarget(null); load() })
          }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
          <Button size="small" onClick={() => setNoteTarget(null)}>关闭</Button>
        </Space>
      )}
      {annotations.length > 0 && (
        <div style={{ marginTop: 12, maxHeight: 140, overflow: 'auto' }}>
          <div style={{ fontSize: 12, color: '#64748B', marginBottom: 4 }}>全部批注（{annotations.length}）</div>
          {annotations.map((a) => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0', fontSize: 12 }}>
              <Tag>P{a.page}</Tag>
              <span style={{ width: 10, height: 10, background: a.color, borderRadius: 2, display: 'inline-block' }} />
              <span style={{ color: '#94A3B8', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {a.rect.startsWith('TEXT:') ? `📝 ${a.note}` : (a.note || '（无备注）')}
              </span>
              <Button size="small" type="link" onClick={() => { setPage(a.page); setNoteTarget(a); setNoteText(a.note) }}>查看</Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <div>
      <Space style={{ marginBottom: 10 }}>
        <Button size={view === 'pdf' ? 'small' : 'small'} type={view === 'pdf' ? 'primary' : 'default'} onClick={() => setView('pdf')}>
          PDF 阅读
        </Button>
        <Button size="small" type={view === 'ai' ? 'primary' : 'default'} onClick={() => setView('ai')}>
          文本视图与 AI
        </Button>
      </Space>
      {view === 'pdf' ? renderPdfView() : renderAiView()}
    </div>
  )
}
