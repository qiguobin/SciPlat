import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Button, Card, Checkbox, Collapse, DatePicker, Descriptions, Form, Input, message, Modal,
  Popconfirm, Progress, Select, Space, Statistic, Table, Tag, Timeline, Typography, Upload,
} from 'antd'
import {
  ArrowLeftOutlined, CheckSquareOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, PlusOutlined, RobotOutlined, UploadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import ReactMarkdown from 'react-markdown'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate, fmtDateTime, fmtSize, splitTags } from '../utils'
import { PaperStatusTag, PAPER_STATUS } from '../components/StatusTag'
import PaperFormModal from '../components/PaperFormModal'
import type { PaperDetail, PaperSection, ReviewRound, StatusLog, WritingLog } from '../types'

const DECISION_OPTIONS = ['Major Revision', 'Minor Revision', 'Accept', 'Reject']

const POLISH_ACTIONS = [
  { value: 'polish', label: '学术润色' },
  { value: 'translate_zh', label: '翻译为中文（学术风格）' },
  { value: 'translate_en', label: '翻译为英文（学术风格）' },
  { value: 'expand', label: '扩写' },
  { value: 'condense', label: '缩写' },
  { value: 'deai', label: '降 AI 味' },
]

export default function PaperDetail() {
  const nav = useNavigate()
  const pid = Number(location.pathname.split('/')[2])
  const [data, setData] = useState<PaperDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [versionFile, setVersionFile] = useState<File | null>(null)
  const [changelog, setChangelog] = useState('')
  const [uploading, setUploading] = useState(false)
  const [roundModal, setRoundModal] = useState(false)
  const [roundFile, setRoundFile] = useState<File | null>(null)
  const [roundForm] = Form.useForm()
  const [writingLogs, setWritingLogs] = useState<WritingLog[]>([])
  const [writingToday, setWritingToday] = useState('')
  const [writingSection, setWritingSection] = useState<number | undefined>()
  const [sectionModal, setSectionModal] = useState(false)
  const [editingSection, setEditingSection] = useState<PaperSection | null>(null)
  const [secForm] = Form.useForm()
  const [statusLogs, setStatusLogs] = useState<StatusLog[]>([])
  const [citedRefs, setCitedRefs] = useState<{ id: number; title: string; year: number | null; venue: string }[]>([])
  const [refModal, setRefModal] = useState(false)
  const [refSel, setRefSel] = useState<number | undefined>()
  const [allRefs, setAllRefs] = useState<{ id: number; title: string }[]>([])
  const [writingGoal, setWritingGoal] = useState(0)
  const [streak, setStreak] = useState(0)
  const [aiReviewOpen, setAiReviewOpen] = useState(false)
  const [aiReview, setAiReview] = useState('')
  const [aiReviewLoading, setAiReviewLoading] = useState(false)
  // AI 写作润色
  const [polishOpen, setPolishOpen] = useState(false)
  const [polishSection, setPolishSection] = useState<PaperSection | null>(null)
  const [polishAction, setPolishAction] = useState('polish')
  const [polishSrc, setPolishSrc] = useState('')
  const [polishResult, setPolishResult] = useState('')
  const [polishLoading, setPolishLoading] = useState(false)
  const [polishCount, setPolishCount] = useState(false)
  const [sectionContent, setSectionContent] = useState<Record<number, string>>({})
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = () => {
    setLoading(true)
    api
      .get<PaperDetail>(`/papers/${pid}`)
      .then((r) => setData(r.data))
      .catch(() => message.error('论文不存在'))
      .finally(() => setLoading(false))
    api.get<WritingLog[]>('/writing-logs', { params: { paper_id: pid } })
      .then((r) => setWritingLogs(r.data)).catch(() => {})
    api.get<StatusLog[]>('/papers/{0}/status-history'.replace('{0}', String(pid)))
      .then((r) => setStatusLogs(r.data)).catch(() => {})
    api.get<{ id: number; title: string; year: number | null; venue: string }[]>(`/papers/${pid}/references`)
      .then((r) => setCitedRefs(r.data)).catch(() => {})
    api.get<{ id: number; title: string }[]>('/references')
      .then((r) => setAllRefs(r.data)).catch(() => {})
    api.get<{ goal: number }>('/settings/writing-goal')
      .then((r) => setWritingGoal(r.data.goal)).catch(() => {})
    api.get<{ streak: number }>('/writing-logs/streak')
      .then((r) => setStreak(r.data.streak)).catch(() => {})
  }
  useEffect(load, [pid, refreshKey])

  const openSectionModal = (s?: PaperSection) => {
    setEditingSection(s ?? null)
    secForm.setFieldsValue(s
      ? { title: s.title, target_words: s.target_words, status: s.status, order_no: s.order_no }
      : { status: '未开始', target_words: 0 })
    setSectionModal(true)
  }

  const saveSection = () => {
    secForm.validateFields().then((v) => {
      const req = editingSection
        ? api.put(`/papers/sections/${editingSection.id}`, v)
        : api.post(`/papers/${pid}/sections`, v)
      req.then(() => {
        message.success('已保存')
        setSectionModal(false)
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const runAiReview = () => {
    setAiReviewLoading(true)
    api.post(`/papers/${pid}/ai-submit-review`)
      .then((r) => { setAiReview(r.data.review); setAiReviewOpen(true) })
      .catch((e) => message.error(e.response?.data?.detail ?? '审查失败'))
      .finally(() => setAiReviewLoading(false))
  }

  const saveSectionContent = (sid: number, content: string) => {
    api.put(`/papers/sections/${sid}`, { content }).then(() => {})
  }

  const openPolish = (sec: PaperSection) => {
    setPolishSection(sec)
    setPolishSrc(sec.content || '')
    setPolishResult('')
    setPolishAction('polish')
    setPolishCount(false)
    setPolishOpen(true)
  }

  const runPolish = () => {
    if (!polishSrc.trim()) { message.warning('请输入需要处理的文本'); return }
    setPolishLoading(true)
    api.post('/ai/polish', { text: polishSrc, action: polishAction })
      .then((r) => setPolishResult(r.data.result))
      .catch((e) => message.error(e.response?.data?.detail ?? '处理失败'))
      .finally(() => setPolishLoading(false))
  }

  const applyPolish = () => {
    if (!polishSection || !polishResult) return
    saveSectionContent(polishSection.id, polishResult)
    if (polishCount) {
      const today = dayjs().format('YYYY-MM-DD')
      const existing = writingLogs.find((w) => w.date === today)
      const n = polishResult.length
      const req = existing
        ? api.put(`/writing-logs/${existing.id}`, { word_count: n, section_id: polishSection.id, note: 'AI 润色' })
        : api.post('/writing-logs', { date: today, paper_id: pid, word_count: n, section_id: polishSection.id, note: 'AI 润色' })
      req.then(() => { message.success('已计入今日写作打卡') }).catch(() => {})
    }
    message.success('已应用到章节')
    setPolishOpen(false)
    bump()
  }

  const saveWriting = () => {
    const n = Number(writingToday)
    if (!n || n <= 0) { message.warning('请输入有效的字数'); return }
    const today = dayjs().format('YYYY-MM-DD')
    const existing = writingLogs.find((w) => w.date === today)
    const req = existing
      ? api.put(`/writing-logs/${existing.id}`, { word_count: n, section_id: writingSection ?? null })
      : api.post('/writing-logs', { date: today, paper_id: pid, word_count: n, section_id: writingSection ?? null })
    req.then(() => {
      message.success('打卡成功')
      setWritingToday('')
      bump()
    }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const changeStatus = (to: string) => {
    api.post(`/papers/${pid}/status`, { to }).then(() => {
      message.success(`状态已更新：${PAPER_STATUS[to]?.label ?? to}`)
      bump()
    }).catch((e) => message.error(e.response?.data?.detail ?? '状态更新失败'))
  }

  const uploadVersion = () => {
    if (!versionFile) {
      message.warning('请选择文件')
      return
    }
    setUploading(true)
    const fd = new FormData()
    fd.append('file', versionFile)
    fd.append('changelog', changelog)
    api.post(`/papers/${pid}/versions`, fd)
      .then(() => {
        message.success('版本已上传')
        setVersionFile(null)
        setChangelog('')
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '上传失败'))
      .finally(() => setUploading(false))
  }

  const saveRound = () => {
    roundForm.validateFields().then((v) => {
      const fd = new FormData()
      fd.append('decision', v.decision)
      fd.append('summary', v.summary ?? '')
      if (v.review_date) fd.append('review_date', v.review_date.format('YYYY-MM-DD'))
      if (roundFile) fd.append('file', roundFile)
      api.post(`/papers/${pid}/review-rounds`, fd)
        .then(() => {
          message.success('审稿记录已添加')
          setRoundModal(false)
          setRoundFile(null)
          roundForm.resetFields()
          bump()
        })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  if (loading || !data) return <Card loading={loading} />

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card
        title={
          <Space>
            <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => nav('/papers')} />
            <Typography.Text strong style={{ fontSize: 16 }}>{data.title}</Typography.Text>
            <PaperStatusTag status={data.status} />
          </Space>
        }
        extra={
          <Space>
            <Button icon={<RobotOutlined />} loading={aiReviewLoading} onClick={runAiReview}>
              AI 投稿建议
            </Button>
            <Button icon={<EditOutlined />} onClick={() => setEditOpen(true)}>
              编辑基本信息
            </Button>
          </Space>
        }
      >
        <Descriptions column={3} size="small">
          <Descriptions.Item label="类型">{data.paper_type}</Descriptions.Item>
          <Descriptions.Item label="所属项目">{data.project_title || '—'}</Descriptions.Item>
          <Descriptions.Item label="目标期刊">{data.target_journal || '—'}</Descriptions.Item>
          <Descriptions.Item label="分区 / 影响因子">
            {data.journal_quartile || '—'} / {data.journal_if || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="投稿截止">{fmtDate(data.submission_deadline)}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{fmtDateTime(data.created_at)}</Descriptions.Item>
          <Descriptions.Item label="关键词" span={3}>
            {splitTags(data.keywords).map((k) => <Tag key={k}>{k}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="摘要" span={3}>
            {data.abstract || '—'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 章节进度 */}
      <Card
        size="small"
        title="章节进度"
        extra={<Button size="small" icon={<PlusOutlined />} onClick={() => openSectionModal()}>添加章节</Button>}
      >
        {data.sections.length === 0 ? (
          <Typography.Text type="secondary">还没有章节。添加引言/方法/实验/结论等章节，设定字数目标跟踪写作进度。</Typography.Text>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            {data.sections.map((s) => {
              const pct = s.target_words > 0 ? Math.min(100, Math.round((s.written_words / s.target_words) * 100)) : 0
              return (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Tag style={{ width: 40, textAlign: 'center', marginInlineEnd: 0 }}>{s.status === '完成' ? '✓' : s.order_no}</Tag>
                  <span style={{ width: 140, fontWeight: 600 }}>{s.title}</span>
                  <Progress
                    percent={pct}
                    size="small"
                    style={{ flex: 1, maxWidth: 320, margin: 0 }}
                    strokeColor={s.status === '完成' ? '#12b886' : '#1e3a5f'}
                  />
                  <Typography.Text type="secondary" style={{ fontSize: 12, width: 110 }}>
                    {s.written_words} / {s.target_words || '—'} 字
                  </Typography.Text>
                  <Select
                    size="small"
                    value={s.status}
                    style={{ width: 90 }}
                    onChange={(v) => api.put(`/papers/sections/${s.id}`, { status: v }).then(() => bump())}
                    options={['未开始', '撰写中', '完成'].map((x) => ({ value: x, label: x }))}
                  />
                  <span style={{ fontSize: 11, color: '#64748B' }}>{s.content ? '📝 已记录' : ''}</span>
                  <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openSectionModal(s)} />
                  <Popconfirm title="删除该章节？" onConfirm={() => api.delete(`/papers/sections/${s.id}`).then(() => bump())}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </div>
              )
            })}
          </Space>
        )}
        {/* 章节内容分区记录（大论文章节正文/要点） */}
        {data.sections.length > 0 && (
          <Collapse
            size="small"
            ghost
            style={{ marginTop: 8 }}
            items={data.sections.map((sec) => ({
              key: sec.id,
              label: `📝 ${sec.title} 内容记录`,
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={4}>
                  <Input.TextArea
                    rows={6}
                    defaultValue={sec.content}
                    style={{ fontFamily: 'var(--mono)', fontSize: 12 }}
                    onBlur={(e) => saveSectionContent(sec.id, e.target.value)}
                    placeholder="该章节的正文要点 / 草稿记录…（失焦自动保存）"
                  />
                  <Space>
                    <Button size="small" icon={<RobotOutlined />} onClick={() => openPolish(sec)}>AI 润色</Button>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      润色 / 中英互译 / 扩写缩写 / 降 AI 味，可计入写作打卡
                    </Typography.Text>
                  </Space>
                </Space>
              ),
            }))}
          />
        )}
      </Card>

      {/* 引用文献 */}
      <Card
        size="small"
        title={`引用文献（${citedRefs.length}）`}
        extra={
          <Space>
            <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => { setRefSel(undefined); setRefModal(true) }}>
              关联文献
            </Button>
            <Button size="small" icon={<EditOutlined />} onClick={() => api.put('/settings/writing-goal', { goal: prompt('每周写作目标字数：', String(writingGoal || 0)) }).then(() => bump()).catch(() => {})}>
              周目标 {writingGoal ? `${writingGoal} 字` : '设置'}
            </Button>
          </Space>
        }
      >
        {citedRefs.length === 0 ? (
          <Typography.Text type="secondary">还没有关联文献。写引言/相关工作时可把引用的文献关联到这里，形成证据链。</Typography.Text>
        ) : (
          <Space wrap size={4}>
            {citedRefs.map((r) => (
              <Tag key={r.id} closable onClose={(e) => {
                e.preventDefault()
                api.delete(`/papers/${pid}/references/${r.id}`).then(() => bump())
              }}>
                {r.title}{r.year ? `（${r.year}）` : ''}
              </Tag>
            ))}
          </Space>
        )}
      </Card>

      {/* 写作打卡 */}
      <Card size="small" title="写作打卡">
        <Space wrap>
          <Input
            type="number"
            placeholder="今日写作字数"
            value={writingToday}
            onChange={(e) => setWritingToday(e.target.value)}
            style={{ width: 140 }}
            onPressEnter={saveWriting}
          />
          <Select
            placeholder="对应章节（可选）"
            allowClear
            style={{ width: 140 }}
            value={writingSection}
            onChange={(v) => setWritingSection(v)}
            options={data.sections.map((s) => ({ value: s.id, label: s.title }))}
          />
          <Button type="primary" onClick={saveWriting}>打卡</Button>
          <Statistic title="累计打卡字数" value={writingLogs.reduce((s, w) => s + w.word_count, 0)} suffix={`字 / ${writingLogs.length} 天`} style={{ marginLeft: 24 }} />
          {streak > 0 && <Statistic title="连续打卡" value={streak} suffix="天 🔥" style={{ marginLeft: 24 }} />}
          <Statistic title="最近 7 天" value={writingLogs.filter((w) => dayjs(w.date).isAfter(dayjs().subtract(7, 'day'))).reduce((s, w) => s + w.word_count, 0)} suffix="字" />
        </Space>
      </Card>

      {/* 投稿历程 */}
      {statusLogs.length > 0 && (
        <Card size="small" title="投稿历程">
          <Timeline
            items={statusLogs.map((l) => ({
              color: l.to_status === 'Published' ? 'green' : 'blue',
              children: (
                <Space>
                  <Tag>{PAPER_STATUS[l.from_status]?.label ?? l.from_status}</Tag>
                  <span>→</span>
                  <Tag color={PAPER_STATUS[l.to_status]?.color}>{PAPER_STATUS[l.to_status]?.label ?? l.to_status}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12, fontFamily: 'var(--mono)' }}>
                    {fmtDateTime(l.created_at)}
                  </Typography.Text>
                </Space>
              ),
            }))}
          />
        </Card>
      )}

      <Card title="投稿状态流转" size="small">
        <Space wrap>
          <span>当前状态：</span>
          <PaperStatusTag status={data.status} />
          {data.next_statuses.length > 0 ? (
            <>
              <span style={{ marginLeft: 16 }}>可执行操作：</span>
              {data.next_statuses.map((s) => (
                <Button key={s} size="small" onClick={() => changeStatus(s)}>
                  → {PAPER_STATUS[s]?.label ?? s}
                </Button>
              ))}
            </>
          ) : (
            <Typography.Text type="secondary">（终态，无后续操作）</Typography.Text>
          )}
        </Space>
      </Card>

      <Card
        title="草稿版本"
        size="small"
        extra={
          <Button size="small" icon={<PlusOutlined />} onClick={() => fileInputRef.current?.click()}>
            上传新版本
          </Button>
        }
      >
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) setVersionFile(f)
            e.target.value = ''
          }}
        />
        {versionFile && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={
              <Space direction="vertical" style={{ width: '100%' }}>
                <span>待上传：{versionFile.name}（{fmtSize(versionFile.size)}）</span>
                <Space>
                  <Input
                    placeholder="变更说明（可选）"
                    value={changelog}
                    onChange={(e) => setChangelog(e.target.value)}
                    style={{ width: 320 }}
                  />
                  <Button type="primary" size="small" loading={uploading} onClick={uploadVersion}>
                    确认上传
                  </Button>
                  <Button size="small" onClick={() => setVersionFile(null)}>取消</Button>
                </Space>
              </Space>
            }
          />
        )}
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data.versions}
          columns={[
            { title: '版本', dataIndex: 'version_no', width: 80, render: (v: number) => `v${v}` },
            { title: '文件', dataIndex: 'file_name', ellipsis: true },
            { title: '大小', dataIndex: 'file_size', width: 90, render: (v: number) => fmtSize(v) },
            { title: '变更说明', dataIndex: 'changelog', ellipsis: true },
            { title: '时间', dataIndex: 'created_at', width: 150, render: (v) => fmtDateTime(v) },
            {
              title: '操作',
              width: 90,
              render: (_, v) => (
                <Space>
                  <Button size="small" icon={<DownloadOutlined />} href={`/api/papers/versions/${v.id}/download`} />
                  <Popconfirm title="删除该版本？" onConfirm={() => {
                    api.delete(`/papers/versions/${v.id}`).then(() => bump())
                  }}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
          locale={{ emptyText: '暂无版本，上传第一版草稿' }}
        />
      </Card>

      <Card
        title="审稿记录"
        size="small"
        extra={
          <Button size="small" icon={<PlusOutlined />} onClick={() => setRoundModal(true)}>
            添加审稿记录
          </Button>
        }
      >
        {data.review_rounds.length === 0 ? (
          <Typography.Text type="secondary">暂无审稿记录</Typography.Text>
        ) : (
          <Timeline
            items={data.review_rounds.map((r) => ({
              children: (
                <Space direction="vertical" size={2}>
                  <Space>
                    <Tag color="blue">第 {r.round_no} 轮</Tag>
                    <Tag>{r.decision}</Tag>
                    <Typography.Text type="secondary">{fmtDate(r.review_date)}</Typography.Text>
                    {r.file_name && (
                      <Button size="small" type="link" icon={<DownloadOutlined />} href={`/api/papers/review-rounds/${r.id}/download`}>
                        意见文件
                      </Button>
                    )}
                    <Button size="small" type="link" icon={<CheckSquareOutlined />} onClick={() => {
                      api.post(`/api/papers/review-rounds/${r.id}/convert`, { text: r.summary || undefined })
                        .then(() => { message.success('已转为今日待办'); bump() })
                        .catch((e) => message.error(e.response?.data?.detail ?? '转换失败'))
                    }}>
                      转待办
                    </Button>
                    <Popconfirm title="删除该条记录？" onConfirm={() => {
                      api.delete(`/papers/review-rounds/${r.id}`).then(() => bump())
                    }}>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                  {r.summary && <Typography.Text type="secondary">{r.summary}</Typography.Text>}
                </Space>
              ),
            }))}
          />
        )}
      </Card>

      {/* AI 投稿建议弹窗 */}
      <Modal title="AI 投稿前审查建议" open={aiReviewOpen} onCancel={() => setAiReviewOpen(false)}
        footer={[
          <Button key="save" type="primary" disabled={!aiReview} onClick={() => {
            api.post('/notes', { target_type: 'paper', target_id: pid, content: `## AI 投稿建议

${aiReview}` })
              .then(() => { message.success('已存入笔记'); bump() })
          }}>存入笔记</Button>,
          <Button key="close" onClick={() => setAiReviewOpen(false)}>关闭</Button>,
        ]}
        width={720} destroyOnClose>
        <div className="markdown-body" style={{ maxHeight: '55vh', overflow: 'auto' }}>
          <ReactMarkdown>{aiReview}</ReactMarkdown>
        </div>
        <Alert type="info" showIcon style={{ marginTop: 8 }}
          message="更深入的精修可在 ZCode 中使用 nature-polishing / nature-reviewer 技能处理全文。" />
      </Modal>

      {/* AI 写作润色弹窗 */}
      <Modal
        title={`AI 写作润色${polishSection ? ` · ${polishSection.title}` : ''}`}
        open={polishOpen}
        onCancel={() => setPolishOpen(false)}
        width={760}
        footer={[
          <Checkbox key="count" checked={polishCount} onChange={(e) => setPolishCount(e.target.checked)}>
            计入今日写作打卡
          </Checkbox>,
          <Button key="apply" type="primary" icon={<CheckSquareOutlined />} disabled={!polishResult} onClick={applyPolish}>
            应用替换章节
          </Button>,
          <Button key="copy" icon={<CopyOutlined />} disabled={!polishResult} onClick={() => {
            navigator.clipboard.writeText(polishResult)
            message.success('已复制')
          }}>复制</Button>,
          <Button key="close" onClick={() => setPolishOpen(false)}>关闭</Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Space wrap>
            <span style={{ fontSize: 12, color: '#94A3B8' }}>处理动作</span>
            <Select value={polishAction} onChange={setPolishAction} style={{ width: 240 }}
              options={POLISH_ACTIONS.map((a) => ({ value: a.value, label: a.label }))} />
            <Button type="primary" icon={<RobotOutlined />} loading={polishLoading} onClick={runPolish}>生成</Button>
          </Space>
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>原文</Typography.Text>
            <Input.TextArea rows={6} value={polishSrc} onChange={(e) => setPolishSrc(e.target.value)}
              placeholder="粘贴需要处理的文本…" style={{ marginTop: 4 }} />
          </div>
          {polishResult && (
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>处理结果（可继续编辑）</Typography.Text>
              <Input.TextArea rows={8} value={polishResult} onChange={(e) => setPolishResult(e.target.value)}
                style={{ fontFamily: 'var(--mono)', fontSize: 12, marginTop: 4 }} />
            </div>
          )}
        </Space>
      </Modal>

      {/* 章节弹窗 */}
      <Modal
        title={editingSection ? '编辑章节' : '添加章节'}
        open={sectionModal}
        onOk={saveSection}
        onCancel={() => setSectionModal(false)}
        destroyOnClose
      >
        <Form form={secForm} layout="vertical">
          <Form.Item name="title" label="章节名" rules={[{ required: true, message: '请输入章节名' }]}>
            <Input placeholder="如：引言 / 方法 / 实验 / 结论" />
          </Form.Item>
          <Form.Item label="目标字数 / 状态">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="target_words" noStyle>
                <Input type="number" placeholder="目标字数" style={{ width: '50%' }} />
              </Form.Item>
              <Form.Item name="status" noStyle>
                <Select style={{ width: '50%' }} options={['未开始', '撰写中', '完成'].map((x) => ({ value: x, label: x }))} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="order_no" label="顺序"><Input type="number" /></Form.Item>
        </Form>
      </Modal>

      {/* 关联文献弹窗 */}
      <Modal title="关联引用文献" open={refModal} onOk={() => {
        if (!refSel) { message.warning('请选择文献'); return }
        api.post(`/papers/${pid}/references`, { reference_id: refSel })
          .then(() => { message.success('已关联'); setRefModal(false); bump() })
          .catch((e) => message.error(e.response?.data?.detail ?? '关联失败'))
      }} onCancel={() => setRefModal(false)} destroyOnClose>
        <Select
          style={{ width: '100%' }}
          showSearch
          optionFilterProp="label"
          placeholder="搜索并选择文献"
          value={refSel}
          onChange={(v) => setRefSel(v)}
          options={allRefs.map((r) => ({ value: r.id, label: r.title }))}
        />
      </Modal>

      <PaperFormModal
        open={editOpen}
        initial={data}
        onClose={() => setEditOpen(false)}
        onSaved={() => {
          message.success('已更新')
          bump()
        }}
      />

      <Modal
        title="添加审稿记录"
        open={roundModal}
        onOk={saveRound}
        onCancel={() => setRoundModal(false)}
        destroyOnClose
      >
        <Form form={roundForm} layout="vertical">
          <Form.Item name="decision" label="审稿结果" rules={[{ required: true, message: '请选择审稿结果' }]}>
            <Select options={DECISION_OPTIONS.map((d) => ({ value: d, label: d }))} />
          </Form.Item>
          <Form.Item name="review_date" label="收到日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="summary" label="意见摘要">
            <Input.TextArea rows={4} placeholder="审稿意见要点、需要修改的内容……" />
          </Form.Item>
          <Form.Item label="审稿意见文件（可选）">
            <Upload
              beforeUpload={(f) => {
                setRoundFile(f)
                return false
              }}
              onRemove={() => setRoundFile(null)}
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
