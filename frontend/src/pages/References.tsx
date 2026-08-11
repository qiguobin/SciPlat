import { useEffect, useRef, useState } from 'react'
import {
  Alert, Button, Card, Dropdown, Empty, Form, Input, List, message, Modal, Popconfirm, Progress, Select, Slider, Space, Spin, Table, Tabs, Tag, Typography, Upload,
} from 'antd'
import {
  CloudDownloadOutlined, CopyOutlined, DeleteOutlined, DownOutlined, DownloadOutlined, EditOutlined, ExperimentOutlined,
  FileSearchOutlined, FileTextOutlined, ImportOutlined, LinkOutlined, PlusOutlined, ApartmentOutlined,
  ReadOutlined, RobotOutlined, SaveOutlined, ScissorOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate, splitTags } from '../utils'
import { READ_STATUS } from '../components/StatusTag'
import NotesPanel from '../components/NotesPanel'
import ReferenceNetwork from './ReferenceNetwork'
import CitationModal from '../components/CitationModal'
import ReactMarkdown from 'react-markdown'
import PdfReader from '../components/PdfReader'
import { FACTOR_LABELS } from '../types'
import type { DeepReading, DuplicateGroup, QueueItem, Reference, ReferenceTextInfo } from '../types'

const CATEGORY_OPTIONS = ['经典必读', '综述', '方法', '数据', '工具', '其他']

// 常用文献等级定位工具（快捷打开新标签页查询）
const LEVEL_TOOLS = [
  { name: 'LetPub', url: 'https://www.letpub.com.cn' },
  { name: '中科院分区表', url: 'https://www.fenqubiao.com' },
  { name: 'JCR 官网', url: 'https://jcr.clarivate.com' },
  { name: '新锐分区', url: 'https://xr-scholar.com' },
]

const READ_OPTIONS = Object.keys(READ_STATUS)

export default function References() {
  const nav = useNavigate()
  const { sub = 'list' } = useParams()
  const [list, setList] = useState<Reference[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [readFilter, setReadFilter] = useState<string | undefined>()
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>()
  const [yearFilter, setYearFilter] = useState<number | undefined>()
  const [years, setYears] = useState<number[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Reference | null>(null)
  const [form] = Form.useForm()
  const [doiLoading, setDoiLoading] = useState(false)
  const [noteTarget, setNoteTarget] = useState<Reference | null>(null)
  const [importLoading, setImportLoading] = useState(false)
  const [reader, setReader] = useState<Reference | null>(null)
  const [textTarget, setTextTarget] = useState<Reference | null>(null)
  const [textInfo, setTextInfo] = useState<ReferenceTextInfo | null>(null)
  const [textLoading, setTextLoading] = useState(false)
  const [fetchingFulltext, setFetchingFulltext] = useState<number | null>(null)
  const [aiMetaLoading, setAiMetaLoading] = useState<number | null>(null)
  const [batchAiLoading, setBatchAiLoading] = useState(false)
  const [citationOpen, setCitationOpen] = useState(false)
  const [citationTarget, setCitationTarget] = useState<Reference[]>([])
  const [deepReading, setDeepReading] = useState<DeepReading | null>(null)
  const [deepForm] = Form.useForm()
  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([])
  const [dupOpen, setDupOpen] = useState(false)
  const [dupLoading, setDupLoading] = useState(false)
  const [fulltextSearch, setFulltextSearch] = useState(false)
  const [ftHits, setFtHits] = useState<{ reference_id: number; title: string; snippet: string }[]>([])
  const [ftQ, setFtQ] = useState('')
  const [selectedRefs, setSelectedRefs] = useState<Reference[]>([])
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [collections, setCollections] = useState<{ id: number; name: string; count: number }[]>([])
  const [collectionFilter, setCollectionFilter] = useState<number | undefined>()
  const [refCollections, setRefCollections] = useState<number[]>([])
  const [savedViews, setSavedViews] = useState<{ id: number; name: string; filters: Record<string, string> }[]>([])
  const [viewName, setViewName] = useState('')
  const [relatedOpen, setRelatedOpen] = useState(false)
  const [similarOpen, setSimilarOpen] = useState(false)
  const [similarTarget, setSimilarTarget] = useState<Reference | null>(null)
  const [similarList, setSimilarList] = useState<{ id: number; title: string; year: number | null; venue: string; weight: number; factors: string[] }[]>([])
  const [aiModal, setAiModal] = useState<{ type: 'summary' | 'questions'; ref: Reference; content: string; loading: boolean } | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewMd, setReviewMd] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)
  const [relatedTarget, setRelatedTarget] = useState<Reference | null>(null)
  const [relatedSel, setRelatedSel] = useState<number | undefined>()
  const readerOpenAt = useRef<number | null>(null)
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    setLoading(true)
    api
      .get<Reference[]>('/references', {
        params: { q: search || undefined, read_status: readFilter, category: categoryFilter, year: yearFilter, collection_id: collectionFilter },
      })
      .then((r) => {
        setList(r.data)
        const ys = new Set<number>()
        r.data.forEach((x) => x.year && ys.add(x.year))
        setYears([...ys].sort((a, b) => b - a))
      })
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [refreshKey, search, readFilter, categoryFilter, yearFilter, collectionFilter])
  useEffect(() => {
    api.get<{ id: number; name: string; count: number }[]>('/collections').then((r) => setCollections(r.data)).catch(() => {})
    api.get<{ id: number; name: string; filters: Record<string, string> }[]>('/saved-views').then((r) => setSavedViews(r.data)).catch(() => {})
  }, [refreshKey])

  const openModal = (r?: Reference) => {
    setEditing(r ?? null)
    form.setFieldsValue(
      r
        ? {
            title: r.title,
            authors: r.authors,
            year: r.year,
            venue: r.venue,
            doi: r.doi,
            bibkey: r.bibkey,
            tags: splitTags(r.tags),
            read_status: r.read_status,
            category: r.category,
            quartile: r.quartile,
            journal_if: r.journal_if,
            jcr_quartile: r.jcr_quartile,
            cas_quartile: r.cas_quartile,
            xinrui_quartile: r.xinrui_quartile,
          }
        : { read_status: '未读', authors: [], category: '其他' },
    )
    setModalOpen(true)
  }

  const fetchFulltext = (r: Reference) => {
    setFetchingFulltext(r.id)
    api.post(`/references/${r.id}/fetch-fulltext`)
      .then((res) => {
        message.success(`已获取全文（${res.data.source === 'arxiv' ? 'arXiv' : 'Unpaywall'}）`)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '未找到合法开放获取全文'))
      .finally(() => setFetchingFulltext(null))
  }

  const openText = (r: Reference) => {
    setTextTarget(r)
    setTextInfo(null)
    setTextLoading(true)
    api.get<ReferenceTextInfo>(`/references/${r.id}/text`)
      .then((res) => setTextInfo(res.data))
      .catch(() => setTextInfo(null))
      .finally(() => setTextLoading(false))
  }

  const extractText = () => {
    if (!textTarget) return
    setTextLoading(true)
    api.post<ReferenceTextInfo>(`/references/${textTarget.id}/extract-text`)
      .then((res) => {
        setTextInfo(res.data)
        message.success('文本提取完成')
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '提取失败'))
      .finally(() => setTextLoading(false))
  }

  // 阅读时长计时：打开阅读器开始，关闭/切换时上报
  const openReader = (r: Reference) => {
    setReader(r)
    readerOpenAt.current = Date.now()
    api.get<DeepReading>(`/references/${r.id}/deep-reading`)
      .then((res) => {
        setDeepReading(res.data)
        deepForm.setFieldsValue({
          question: res.data.question, method: res.data.method,
          conclusion: res.data.conclusion, insight: res.data.insight,
        })
      })
      .catch(() => setDeepReading(null))
  }
  const closeReader = () => {
    if (reader && readerOpenAt.current) {
      const seconds = Math.round((Date.now() - readerOpenAt.current) / 1000)
      if (seconds >= 10) api.post(`/references/${reader.id}/reading-session`, { seconds })
    }
    readerOpenAt.current = null
    setReader(null)
  }

  const checkDuplicates = () => {
    setDupLoading(true)
    api.get<DuplicateGroup[]>('/references/duplicates')
      .then((r) => { setDuplicates(r.data); setDupOpen(true) })
      .catch(() => message.error('检测失败'))
      .finally(() => setDupLoading(false))
  }

  const merge = (keepId: number, dropId: number) => {
    api.post(`/references/${dropId}/merge`, { target_id: keepId })
      .then(() => {
        message.success('已合并（保留笔记/附件/标签并集）')
        checkDuplicates()
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '合并失败'))
  }

  const runAiSummary = (ref: Reference) => {
    setAiModal({ type: 'summary', ref, content: '', loading: true })
    api.post(`/references/${ref.id}/ai-summary`)
      .then((r) => setAiModal({ type: 'summary', ref, content: r.data.summary, loading: false }))
      .catch((e) => {
        setAiModal(null)
        message.error(e.response?.data?.detail ?? 'AI 解读失败')
      })
  }

  const runAiQuestions = (ref: Reference) => {
    setAiModal({ type: 'questions', ref, content: '', loading: true })
    api.post(`/references/${ref.id}/ai-ten-questions`)
      .then((r) => setAiModal({ type: 'questions', ref, content: r.data.questions, loading: false }))
      .catch((e) => {
        setAiModal(null)
        message.error(e.response?.data?.detail ?? '十问生成失败')
      })
  }

  const saveAiToNotes = () => {
    if (!aiModal) return
    const prefix = aiModal.type === 'summary' ? 'AI 解读' : '论文十问'
    api.post('/notes', {
      target_type: 'reference', target_id: aiModal.ref.id,
      content: `## ${prefix}：${aiModal.ref.title}

${aiModal.content}`,
    }).then(() => { message.success('已存入文献笔记'); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const runAiReview = () => {
    if (selectedRefs.length === 0) { message.warning('请先选择文献'); return }
    setReviewLoading(true)
    api.post('/references/ai-review', { ids: selectedRefs.map((r) => r.id) })
      .then((r) => { setReviewMd(r.data.markdown); setReviewOpen(true) })
      .catch((e) => message.error(e.response?.data?.detail ?? '综述生成失败'))
      .finally(() => setReviewLoading(false))
  }

  const exportReviewPdf = () => {
    // 打印排版页 → 浏览器导出 PDF
    const w = window.open('', '_blank', 'width=900,height=700')
    if (!w) { message.error('浏览器拦截了弹窗'); return }
    w.document.write(`<html><head><title>AI 文献综述</title>
      <style>body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:820px;margin:40px auto;padding:0 24px;color:#222;line-height:1.9}
      h1,h2{border-bottom:1px solid #ddd;padding-bottom:6px}h1{font-size:24px}h2{font-size:19px}pre{white-space:pre-wrap}</style></head>
      <body><pre>${reviewMd.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
      <script>window.onload=function(){setTimeout(function(){window.print()},400)}</script></body></html>`)
    w.document.close()
  }

  const doFulltextSearch = (q: string) => {
    if (!q.trim()) { setFtHits([]); return }
    api.get<{ hits: { reference_id: number; title: string; snippet: string }[] }>('/references/search-fulltext', { params: { q } })
      .then((r) => setFtHits(r.data.hits))
      .catch(() => setFtHits([]))
  }

  const loadQueue = () => {
    api.get<QueueItem[]>('/references/queue').then((r) => setQueue(r.data)).catch(() => {})
  }
  useEffect(loadQueue, [refreshKey])

  const importRis = (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    api.post('/references/import-ris', fd)
      .then((r) => {
        message.success(`RIS 导入成功 ${r.data.imported} 条，跳过重复 ${r.data.skipped} 条`)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '导入失败'))
  }

  const fetchDoi = () => {
    const doi = form.getFieldValue('doi')
    if (!doi) {
      message.warning('请先填写 DOI')
      return
    }
    setDoiLoading(true)
    api.post('/references/doi-metadata', { doi })
      .then((r) => {
        const m = r.data
        form.setFieldsValue({
          title: m.title || form.getFieldValue('title'),
          authors: m.authors?.length ? m.authors : form.getFieldValue('authors'),
          year: m.year ?? form.getFieldValue('year'),
          venue: m.venue || form.getFieldValue('venue'),
        })
        message.success('已从 CrossRef 获取元数据')
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '获取失败'))
      .finally(() => setDoiLoading(false))
  }

  /** AI 自动匹配单篇文献信息（CrossRef + LLM 推断，只填空缺字段） */
  const runAiMetadata = (ref: Reference) => {
    setAiMetaLoading(ref.id)
    api.post<{ filled: string[]; source: string }>(`/references/${ref.id}/ai-metadata`)
      .then((r) => {
        const src = r.data.source === 'llm' ? 'LLM 推断' : r.data.source === 'crossref' ? 'CrossRef' : '混合'
        message.success(`已补全 ${r.data.filled.length} 个字段（${src}）`)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '补全失败'))
      .finally(() => setAiMetaLoading(null))
  }

  /** AI 批量补全（默认仅处理信息不完整的文献） */
  const runAiMatch = () => {
    setBatchAiLoading(true)
    api.post<{ processed: number; filled_total: number }>('/references/ai-match', { limit: 20, only_incomplete: true })
      .then((r) => {
        if (r.data.processed === 0) message.info('没有需要补全的文献')
        else message.success(`已处理 ${r.data.processed} 篇，共补全 ${r.data.filled_total} 个字段`)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '批量补全失败'))
      .finally(() => setBatchAiLoading(false))
  }

  /** 编辑弹窗内 AI 自动匹配：按当前表单的标题/DOI 补全（返回字段并回填表单） */
  const aiMatchInModal = () => {
    const title = form.getFieldValue('title')
    const doi = form.getFieldValue('doi')
    if (!title && !doi) {
      message.warning('请先填写标题或 DOI')
      return
    }
    if (!editing) {
      message.warning('请先保存文献，再用 AI 自动匹配')
      return
    }
    setDoiLoading(true)
    api.post<{ filled: string[]; source: string }>(`/references/${editing.id}/ai-metadata`)
      .then((r) => {
        const src = r.data.source === 'llm' ? 'LLM 推断' : r.data.source === 'crossref' ? 'CrossRef' : '混合'
        message.success(`已补全 ${r.data.filled.length} 个字段（${src}）`)
        api.get<Reference>(`/references/${editing.id}`).then((res) => {
          const m = res.data
          form.setFieldsValue({
            title: m.title, authors: m.authors, year: m.year, venue: m.venue, doi: m.doi,
            tags: splitTags(m.tags), category: m.category,
            journal_if: m.journal_if, jcr_quartile: m.jcr_quartile,
            cas_quartile: m.cas_quartile, xinrui_quartile: m.xinrui_quartile,
          })
        }).catch(() => {})
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '匹配失败'))
      .finally(() => setDoiLoading(false))
  }

  const save = () => {
    form.validateFields().then((v) => {
      const body = {
        ...v,
        authors: v.authors ?? [],
        tags: (v.tags ?? []).join(','),
      }
      const req = editing ? api.put(`/references/${editing.id}`, body) : api.post('/references', body)
      req
        .then(() => {
          message.success('已保存')
          setModalOpen(false)
          bump()
        })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const importBib = (file: File) => {
    setImportLoading(true)
    const fd = new FormData()
    fd.append('file', file)
    api.post('/references/import-bib', fd)
      .then((r) => {
        message.success(`导入成功 ${r.data.imported} 条，跳过重复 ${r.data.skipped} 条`)
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '导入失败'))
      .finally(() => setImportLoading(false))
  }

  const uploadAttachment = (rid: number, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    api.post(`/references/${rid}/attachment`, fd)
      .then(() => {
        message.success('附件已上传')
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '上传失败'))
  }

  return (
    <>
      <Tabs
        activeKey={sub}
        onChange={(k) => nav(`/references/${k}`)}
        items={[
        {
          key: 'list',
          label: '文献列表',
          children: (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Card size="small">
                <Space wrap>
                  <Input.Search
                    placeholder="搜索标题 / 标签 / DOI"
                    allowClear
                    style={{ width: 240 }}
                    onSearch={(v) => setSearch(v)}
                  />
                  <Select
                    placeholder="按阅读状态筛选"
                    allowClear
                    style={{ width: 150 }}
                    onChange={(v) => setReadFilter(v)}
                    options={READ_OPTIONS.map((s) => ({ value: s, label: s }))}
                  />
                  <Select
                    placeholder="按分类筛选"
                    allowClear
                    style={{ width: 140 }}
                    onChange={(v) => setCategoryFilter(v)}
                    options={CATEGORY_OPTIONS.map((c) => ({ value: c, label: c }))}
                  />
                  <Select
                    placeholder="按年份筛选"
                    allowClear
                    style={{ width: 130 }}
                    onChange={(v) => setYearFilter(v)}
                    options={years.map((y) => ({ value: y, label: String(y) }))}
                  />
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
                    新建文献
                  </Button>
                  <Upload
                    accept=".bib,.ris"
                    showUploadList={false}
                    beforeUpload={(f) => {
                      if (f.name.toLowerCase().endsWith('.ris')) importRis(f)
                      else importBib(f)
                      return false
                    }}
                  >
                    <Button icon={<ImportOutlined />} loading={importLoading}>导入 BibTeX / RIS</Button>
                  </Upload>
                  <Button icon={<DownloadOutlined />} href="/api/references/export-bib">
                    导出 BibTeX
                  </Button>
                  <Button icon={<ScissorOutlined />} loading={dupLoading} onClick={checkDuplicates}>
                    检测重复
                  </Button>
                  <Popconfirm
                    title="AI 批量补全文献信息？"
                    description="默认处理信息不完整的文献（缺 DOI/期刊/年份/分区之一，最多 20 篇），每篇可能调用一次 LLM。只填空缺字段，不覆盖已有值。"
                    onConfirm={runAiMatch}
                  >
                    <Button icon={<RobotOutlined />} loading={batchAiLoading}>
                      AI 批量补全
                    </Button>
                  </Popconfirm>
                  <Button
                    icon={<FileSearchOutlined />}
                    type={fulltextSearch ? 'primary' : 'default'}
                    onClick={() => setFulltextSearch((v) => !v)}
                  >
                    全文搜索
                  </Button>
                  <Button
                    icon={<CopyOutlined />}
                    disabled={selectedRefs.length === 0}
                    onClick={() => { setCitationTarget(selectedRefs); setCitationOpen(true) }}
                  >
                    批量引用（{selectedRefs.length}）
                  </Button>
                  <Button
                    icon={<RobotOutlined />}
                    disabled={selectedRefs.length === 0}
                    loading={reviewLoading}
                    onClick={runAiReview}
                    title="基于选中文献生成 AI 综述"
                  >
                    AI 综述
                  </Button>
                  <Button
                    icon={<LinkOutlined />}
                    disabled={selectedRefs.length !== 2}
                    onClick={() => {
                      if (selectedRefs.length === 2) {
                        api.post(`/references/${selectedRefs[0].id}/related`, { reference_id: selectedRefs[1].id })
                          .then(() => { message.success('已建立手动关联'); bump() })
                          .catch((e) => message.error(e.response?.data?.detail ?? '关联失败'))
                      }
                    }}
                  >
                    关联两篇
                  </Button>
                  <Select
                    placeholder="集合筛选"
                    allowClear
                    style={{ width: 150 }}
                    value={collectionFilter}
                    onChange={(v) => setCollectionFilter(v)}
                    options={collections.map((c) => ({ value: c.id, label: `${c.name}（${c.count}）` }))}
                  />
                  <Select
                    placeholder="已存视图"
                    allowClear
                    style={{ width: 140 }}
                    onChange={(v) => {
                      const view = savedViews.find((x) => x.id === v)
                      if (view) {
                        const f = view.filters
                        setCategoryFilter(f.category ?? undefined)
                        setReadFilter(f.read_status ?? undefined)
                        setYearFilter(f.year ? Number(f.year) : undefined)
                        setSearch(f.q ?? '')
                      }
                    }}
                    options={savedViews.map((v) => ({ value: v.id, label: v.name }))}
                  />
                  <Button size="small" icon={<SaveOutlined />} onClick={() => {
                    const name = prompt('保存当前筛选为视图：')
                    if (name) {
                      api.post('/saved-views', { name, filters: {
                        category: categoryFilter ?? '', read_status: readFilter ?? '',
                        year: yearFilter ? String(yearFilter) : '', q: search ?? '',
                      } }).then(() => { message.success('视图已保存'); bump() })
                    }
                  }}>保存筛选</Button>
                </Space>
                {fulltextSearch && (
                  <div style={{ marginTop: 12 }}>
                    <Input.Search
                      placeholder="在已提取的文献全文文本中搜索…（需先对文献执行文本提取）"
                      onSearch={doFulltextSearch}
                      enterButton="搜索全文"
                      style={{ maxWidth: 460 }}
                    />
                    {ftHits.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        {ftHits.map((h) => (
                          <Alert
                            key={h.reference_id}
                            type="info"
                            style={{ marginBottom: 6 }}
                            message={
                              <div>
                                <Typography.Text strong>{h.title}</Typography.Text>
                                <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '4px 0 0' }}>
                                  {h.snippet}
                                </Typography.Paragraph>
                              </div>
                            }
                          />
                        ))}
                      </div>
                    )}
                    {ftQ && ftHits.length === 0 && <Typography.Text type="secondary">未找到命中</Typography.Text>}
                  </div>
                )}
              </Card>

              <Card size="small">
                <Table<Reference>
                  rowKey="id"
                  loading={loading}
                  dataSource={list}
                  virtual
                  scroll={{ x: 1400, y: 620 }}
                  rowSelection={{
                    selectedRowKeys: selectedRefs.map((r) => r.id),
                    onChange: (_keys, rows) => setSelectedRefs(rows),
                  }}
                  columns={[
                    {
                      title: '标题',
                      dataIndex: 'title',
                      ellipsis: true,
                      render: (v, r) => (
                        <Space direction="vertical" size={0}>
                          <Typography.Text strong>{v}</Typography.Text>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {r.authors.slice(0, 3).join(', ')}{r.authors.length > 3 ? ' 等' : ''}{r.year ? `（${r.year}）` : ''}
                          </Typography.Text>
                          {r.doi && (
                            <Typography.Link href={`https://doi.org/${r.doi}`} target="_blank"
                              style={{ fontSize: 11, display: 'block', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {r.doi}
                            </Typography.Link>
                          )}
                        </Space>
                      ),
                    },
                    {
                      title: '分类',
                      dataIndex: 'category',
                      width: 100,
                      render: (c: string) => <Tag color={c === '其他' ? 'default' : 'blue'}>{c}</Tag>,
                    },
                    {
                      title: '期刊/分区',
                      dataIndex: 'venue',
                      width: 220,
                      ellipsis: true,
                      render: (v, r) => (
                        <Space direction="vertical" size={0} style={{ maxWidth: '100%' }}>
                          <div style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}
                            title={v || ''}>
                            {v || '—'}
                          </div>
                          <Space size={2} wrap>
                            {r.jcr_quartile && <Tag color="blue" style={{ fontSize: 10, marginInlineEnd: 2 }} title="AI 推断，可编辑">JCR {r.jcr_quartile}</Tag>}
                            {r.cas_quartile && <Tag color="green" style={{ fontSize: 10, marginInlineEnd: 2 }} title="AI 推断，可编辑">中科院 {r.cas_quartile}</Tag>}
                            {r.xinrui_quartile && <Tag color="purple" style={{ fontSize: 10, marginInlineEnd: 2 }} title="AI 推断，可编辑">新锐 {r.xinrui_quartile}</Tag>}
                            {r.journal_if && <span style={{ fontSize: 11, color: '#5b6675' }}>IF {r.journal_if}</span>}
                          </Space>
                        </Space>
                      ),
                    },
                    {
                      title: '标签',
                      dataIndex: 'tags',
                      width: 150,
                      ellipsis: true,
                      render: (t: string) => splitTags(t).map((x) => <Tag key={x}>{x}</Tag>),
                    },
                    {
                      title: '阅读状态',
                      dataIndex: 'read_status',
                      width: 120,
                      render: (s: string, r) => (
                        <Space direction="vertical" size={0}>
                          <Tag color={READ_STATUS[s]?.color ?? 'default'}>{s}</Tag>
                          {r.reading_progress > 0 && (
                            <Progress percent={r.reading_progress} size="small" strokeColor="#1e3a5f" style={{ width: 80, margin: 0 }} />
                          )}
                        </Space>
                      ),
                    },
                    { title: '附件', dataIndex: 'file_name', width: 110, ellipsis: true, render: (v, r) => (
                      <span>
                        {v ? '✓' : '—'}
                        {r.fulltext_source === 'auto' && <Tag color="green" style={{ marginLeft: 4 }}>自动</Tag>}
                      </span>
                    )},
                    {
                      title: '操作',
                      width: 310,
                      render: (_, r) => (
                        <Space size={2} wrap>
                          <Button size="small" type="primary" icon={<RobotOutlined />} onClick={() => runAiSummary(r)} title="AI 解读论文" />
                          <Button size="small" icon={<FileTextOutlined />} onClick={() => setNoteTarget(r)} title="阅读笔记" />
                          <Button size="small" icon={<EditOutlined />} onClick={() => openModal(r)} title="编辑" />
                          <Dropdown
                            menu={{ items: [
                              { key: 'read', icon: <ReadOutlined />, label: '在线阅读', disabled: !r.file_name, onClick: () => openReader(r) },
                              { key: 'cite', icon: <CopyOutlined />, label: '生成引用', onClick: () => { setCitationTarget([r]); setCitationOpen(true) } },
                              { key: 'related', icon: <LinkOutlined />, label: '手动关联', onClick: () => { setRelatedTarget(r); setRelatedSel(undefined); setRelatedOpen(true) } },
                              { key: 'similar', icon: <ExperimentOutlined />, label: '推荐相似', onClick: () => {
                                api.get<{ similar: { id: number; title: string; year: number | null; venue: string; weight: number; factors: string[] }[] }>(`/references/similar/${r.id}`)
                                  .then((res) => { setSimilarTarget(r); setSimilarList(res.data.similar); setSimilarOpen(true) })
                                  .catch(() => message.error('推荐失败'))
                              } },
                              { key: 'fulltext', icon: <CloudDownloadOutlined />, label: '自动检索全文', onClick: () => fetchFulltext(r) },
                              { key: 'ai-meta', icon: <RobotOutlined />, label: aiMetaLoading === r.id ? '补全中…' : 'AI 补全信息', disabled: aiMetaLoading === r.id, onClick: () => runAiMetadata(r) },
                              { key: 'text', icon: <ScissorOutlined />, label: '提取全文文本', onClick: () => openText(r) },
                              { key: 'upload', icon: <DownloadOutlined />, label: '上传/替换 PDF', onClick: () => document.getElementById(`ref-upload-${r.id}`)?.click() },
                              ...(r.file_name ? [{ key: 'download', icon: <DownloadOutlined />, label: '下载附件', onClick: () => window.open(`/api/references/${r.id}/download`) }] : []),
                            ] }}
                            trigger={['click']}
                          >
                            <Button size="small">更多 <DownOutlined style={{ fontSize: 10 }} /></Button>
                          </Dropdown>
                          <input
                            id={`ref-upload-${r.id}`} type="file" hidden
                            onChange={(e) => {
                              const f = e.target.files?.[0]
                              if (f) uploadAttachment(r.id, f)
                              e.target.value = ''
                            }}
                          />
                          <Popconfirm title="删除该文献？" onConfirm={() => {
                            api.delete(`/references/${r.id}`).then(() => {
                              message.success('已删除')
                              bump()
                            })
                          }}>
                            <Button size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>
                        </Space>
                      ),
                    },
                  ]}
                  locale={{ emptyText: '暂无文献' }}
                />
              </Card>
            </Space>
          ),
        },
        {
          key: 'network',
          label: (
            <span>
              <ApartmentOutlined style={{ marginRight: 6 }} />
              关联图谱
            </span>
          ),
          children: <ReferenceNetwork />,
        },
        {
          key: 'queue',
          label: (
            <span>
              <ReadOutlined style={{ marginRight: 6 }} />
              阅读队列{queue.length > 0 ? `（${queue.length}）` : ''}
            </span>
          ),
          children: (
            <Card size="small">
              {queue.length === 0 ? (
                <Empty description="队列为空。在文献列表行点击 ⭐ 将文献加入待读队列。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <List
                  dataSource={queue}
                  renderItem={(q) => (
                    <List.Item
                      style={{ paddingInline: 8 }}
                      actions={[
                        <Select
                          key="p"
                          size="small"
                          value={q.queue_priority}
                          style={{ width: 80 }}
                          onChange={(v) => api.patch(`/references/${q.id}/queue`, { priority: v }).then(() => loadQueue())}
                          options={[
                            { value: 1, label: 'P1 低' },
                            { value: 2, label: 'P2 中' },
                            { value: 3, label: 'P3 高' },
                          ]}
                        />,
                        <Button key="done" size="small" type="primary" onClick={() => {
                          api.patch(`/references/${q.id}/queue`, { priority: 0 }).then(() => {
                            api.patch(`/references/${q.id}/progress`, { progress: 100 }).then(() => {
                              message.success('已完成阅读，移出队列')
                              loadQueue()
                              bump()
                            })
                          })
                        }}>
                          完成
                        </Button>,
                        <Popconfirm key="rm" title="移出队列？" onConfirm={() => api.patch(`/references/${q.id}/queue`, { priority: 0 }).then(() => loadQueue())}>
                          <Button size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>,
                      ]}
                    >
                      <Space direction="vertical" size={0}>
                        <Typography.Text strong>{q.title}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          <span title={q.venue || ''}>{q.venue || '—'}</span> {q.year ? `（${q.year}）` : ''}
                          {q.queue_date ? ` · 计划 ${q.queue_date}` : ''}
                        </Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          ),
        },
      ]}
    />

    {/* 新建/编辑弹窗 */}
    <Modal
      title={editing ? '编辑文献' : '新建文献'}
      open={modalOpen}
      onOk={save}
      onCancel={() => setModalOpen(false)}
      width={640}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item name="doi" label="DOI">
          <Space.Compact style={{ width: '100%' }}>
            <Input placeholder="如 10.1038/nature14539" />
            <Button loading={doiLoading} onClick={fetchDoi}>自动获取</Button>
            <Button loading={doiLoading} onClick={aiMatchInModal} title="CrossRef + LLM 推断补全全部字段（含分区），只填空缺">
              AI 自动匹配
            </Button>
          </Space.Compact>
        </Form.Item>
        <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
          <Input />
        </Form.Item>
        <Form.Item name="authors" label="作者">
          <Select mode="tags" placeholder="输入后回车" open={false} suffixIcon={null} />
        </Form.Item>
        <Form.Item label="年份 / 期刊 / BibTeX key">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="year" noStyle>
              <Input placeholder="年份" style={{ width: '20%' }} />
            </Form.Item>
            <Form.Item name="venue" noStyle>
              <Input placeholder="期刊/会议" style={{ width: '45%' }} />
            </Form.Item>
            <Form.Item name="bibkey" noStyle>
              <Input placeholder="BibTeX key" style={{ width: '35%' }} />
            </Form.Item>
          </Space.Compact>
        </Form.Item>
        <Form.Item name="tags" label="标签">
          <Select mode="tags" placeholder="输入后回车" open={false} suffixIcon={null} />
        </Form.Item>
        <Form.Item label="文献等级（可手动修改）">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="jcr_quartile" noStyle>
              <Select allowClear placeholder="JCR 分区" style={{ width: '25%' }}
                options={['Q1', 'Q2', 'Q3', 'Q4'].map((q) => ({ value: q, label: q }))} />
            </Form.Item>
            <Form.Item name="cas_quartile" noStyle>
              <Select allowClear placeholder="中科院分区" style={{ width: '25%' }}
                options={['1区', '2区', '3区', '4区'].map((q) => ({ value: q, label: q }))} />
            </Form.Item>
            <Form.Item name="xinrui_quartile" noStyle>
              <Select allowClear placeholder="新锐分区" style={{ width: '25%' }}
                options={['1区', '2区', '3区', '4区'].map((q) => ({ value: q, label: q }))} />
            </Form.Item>
            <Form.Item name="journal_if" noStyle>
              <Input placeholder="影响因子" style={{ width: '25%' }} />
            </Form.Item>
          </Space.Compact>
        </Form.Item>
        <Form.Item label="等级查询工具">
          <Space size={4} wrap>
            {LEVEL_TOOLS.map((t) => (
              <Button key={t.name} size="small" icon={<LinkOutlined />} href={t.url} target="_blank">
                {t.name}
              </Button>
            ))}
          </Space>
        </Form.Item>
        <Form.Item name="category" label="分类">
          <Select
            placeholder="选择或输入新分类"
            options={CATEGORY_OPTIONS.map((c) => ({ value: c, label: c }))}
            mode="tags"
            maxCount={1}
            suffixIcon={null}
          />
        </Form.Item>
        <Form.Item name="read_status" label="阅读状态">
          <Select options={READ_OPTIONS.map((s) => ({ value: s, label: s }))} />
        </Form.Item>
      </Form>
    </Modal>

    {/* 在线阅读弹窗（含精读与笔记 Tab + 阅读时长计时） */}
    <Modal
      title={`阅读：${reader?.title ?? ''}`}
      open={!!reader}
      onCancel={closeReader}
      footer={null}
      width={1000}
      destroyOnClose
    >
      {reader && (
        <Tabs
          items={[
            {
              key: 'pdf',
              label: 'PDF 阅读（可高亮批注）',
              children: reader.file_name ? (
                <PdfReader referenceId={reader.id} />
              ) : (
                <Alert type="warning" showIcon message="该文献暂无 PDF。可自动检索全文（Unpaywall/arXiv）或手动上传后阅读。" />
              ),
            },
            {
              key: 'deep',
              label: '精读',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Card size="small" title="阅读进度">
                    <Slider
                      value={reader.reading_progress}
                      min={0}
                      max={100}
                      tooltip={{ formatter: (v) => `${v}%` }}
                      onChangeComplete={(p) => {
                        api.patch(`/references/${reader.id}/progress`, { progress: p }).then(() => bump())
                      }}
                    />
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      拖动进度条，完成 100% 自动标记已读
                    </Typography.Text>
                  </Card>
                  <Form
                    form={deepForm}
                    layout="vertical"
                    onValuesChange={(_, all) => {
                      api.put(`/references/${reader.id}/deep-reading`, all).catch(() => {})
                    }}
                  >
                    <Form.Item name="question" label="研究问题"><Input.TextArea rows={2} /></Form.Item>
                    <Form.Item name="method" label="方法"><Input.TextArea rows={2} /></Form.Item>
                    <Form.Item name="conclusion" label="结论"><Input.TextArea rows={2} /></Form.Item>
                    <Form.Item name="insight" label="对我的启发"><Input.TextArea rows={2} /></Form.Item>
                  </Form>
                </Space>
              ),
            },
            {
              key: 'notes',
              label: '笔记',
              children: <NotesPanel targetType="reference" targetId={reader.id} />,
            },
          ]}
        />
      )}
    </Modal>

    {/* 手动关联弹窗 */}
    <Modal title={`关联文献：${relatedTarget?.title ?? ''}`} open={relatedOpen} onCancel={() => setRelatedOpen(false)}
      onOk={() => {
        if (!relatedSel) { message.warning('请选择文献'); return }
        api.post(`/references/${relatedTarget!.id}/related`, { reference_id: relatedSel })
          .then(() => { message.success('已关联（图谱中以「手动关联」边显示）'); setRelatedOpen(false); bump() })
          .catch((e) => message.error(e.response?.data?.detail ?? '关联失败'))
      }} width={520} destroyOnClose>
      <Select
        style={{ width: '100%' }} showSearch optionFilterProp="label" placeholder="搜索并选择要关联的文献"
        value={relatedSel} onChange={setRelatedSel}
        options={list.filter((x) => x.id !== relatedTarget?.id).map((r) => ({ value: r.id, label: r.title }))}
      />
    </Modal>

    {/* AI 解读 / 十问弹窗 */}
    <Modal
      title={`${aiModal?.type === 'summary' ? 'AI 论文解读' : '论文十问'}：${aiModal?.ref.title ?? ''}`}
      open={!!aiModal}
      onCancel={() => setAiModal(null)}
      footer={
        aiModal ? [
          <Button key="q" onClick={() => { if (aiModal.type === 'summary') runAiQuestions(aiModal.ref) }}>
            {aiModal.type === 'summary' ? '生成论文十问' : '生成 AI 解读'}
          </Button>,
          <Button key="save" type="primary" disabled={!aiModal.content} onClick={saveAiToNotes}>存入笔记</Button>,
          <Button key="close" onClick={() => setAiModal(null)}>关闭</Button>,
        ] : []
      }
      width={720}
      destroyOnClose
    >
      {aiModal?.loading ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div> : aiModal ? (
        <div className="markdown-body" style={{ maxHeight: '55vh', overflow: 'auto' }}>
          <ReactMarkdown>{aiModal.content}</ReactMarkdown>
        </div>
      ) : null}
    </Modal>

    {/* AI 综述弹窗 */}
    <Modal
      title="AI 文献综述"
      open={reviewOpen}
      onCancel={() => setReviewOpen(false)}
      footer={[
        <Button key="md" disabled={!reviewMd} onClick={() => {
          api.post('/references/ai-review/export', { ids: selectedRefs.map((r) => r.id) }, { responseType: 'blob' })
            .then((r) => {
              const url = URL.createObjectURL(new Blob([r.data]))
              const a = document.createElement('a')
              a.href = url; a.download = 'AI文献综述.md'; a.click()
              URL.revokeObjectURL(url)
            }).catch(() => message.error('导出失败'))
        }}>导出 .md</Button>,
        <Button key="pdf" type="primary" disabled={!reviewMd} onClick={exportReviewPdf}>打印 / 导出 PDF</Button>,
        <Button key="close" onClick={() => setReviewOpen(false)}>关闭</Button>,
      ]}
      width={820}
      destroyOnClose
    >
      <div className="markdown-body" style={{ maxHeight: '60vh', overflow: 'auto' }}>
        <ReactMarkdown>{reviewMd || '正在生成…'}</ReactMarkdown>
      </div>
    </Modal>

    {/* 相似文献推荐弹窗 */}
    <Modal title={`相似文献推荐：${similarTarget?.title ?? ''}`} open={similarOpen} onCancel={() => setSimilarOpen(false)}
      footer={<Button type="primary" onClick={() => setSimilarOpen(false)}>关闭</Button>} width={560} destroyOnClose>
      {similarList.length === 0 ? (
        <Empty description="暂未找到相似文献（可从标签/作者/期刊角度完善文献信息）" />
      ) : (
        <List
          dataSource={similarList}
          renderItem={(s) => (
            <List.Item style={{ paddingInline: 4 }}>
              <Space direction="vertical" size={0}>
                <Typography.Text strong>{s.title}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {s.venue || '—'} {s.year ? `（${s.year}）` : ''} · 相似度 {s.weight}
                </Typography.Text>
              </Space>
              <Space size={4}>
                {s.factors.map((f) => <Tag key={f} style={{ fontSize: 10 }}>{FACTOR_LABELS[f] ?? f}</Tag>)}
              </Space>
            </List.Item>
          )}
        />
      )}
    </Modal>

    {/* 引用格式弹窗 */}
    <CitationModal open={citationOpen} references={citationTarget} onClose={() => setCitationOpen(false)} />

    {/* 重复检测弹窗 */}
    <Modal
      title={`重复检测（${duplicates.length} 组）`}
      open={dupOpen}
      onCancel={() => setDupOpen(false)}
      footer={<Button type="primary" onClick={() => setDupOpen(false)}>关闭</Button>}
      width={640}
    >
      {duplicates.length === 0 ? (
        <Alert type="success" showIcon message="未发现重复文献" />
      ) : (
        duplicates.map((g, gi) => {
          const keep = g.ids[0]
          return (
            <Card key={gi} size="small" style={{ marginBottom: 10 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Tag color="red">{g.reason}</Tag>
                {g.ids.map((id) => {
                  const r = list.find((x) => x.id === id)
                  return r ? <div key={id}>· {r.title}（{r.year ?? '—'}）</div> : null
                })}
                <Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    保留 #1（合并标签/作者/附件/笔记并集）
                  </Typography.Text>
                  <Button size="small" type="primary" onClick={() => merge(keep, g.ids[1])}>
                    合并到 #1
                  </Button>
                </Space>
              </Space>
            </Card>
          )
        })
      )}
    </Modal>

    {/* 全文文本与摘要弹窗 */}
    <Modal
      title={`全文摘要：${textTarget?.title ?? ''}`}
      open={!!textTarget}
      onCancel={() => setTextTarget(null)}
      width={720}
      footer={
        textInfo ? [
          <Button key="export" icon={<DownloadOutlined />} href={`/api/references/${textTarget?.id}/export-text`}>
            导出全文（供 AI 技能处理）
          </Button>,
          <Button key="close" type="primary" onClick={() => setTextTarget(null)}>关闭</Button>,
        ] : [
          <Button key="extract" type="primary" loading={textLoading} onClick={extractText}>提取文本</Button>,
          <Button key="close" onClick={() => setTextTarget(null)}>关闭</Button>,
        ]
      }
      destroyOnClose
    >
      {!textInfo && textTarget?.file_name && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="提取 PDF 全文文本，自动生成摘要与关键词（本地离线处理）。" />
      )}
      {!textInfo && !textTarget?.file_name && (
        <Alert type="warning" showIcon
          message="该文献还没有 PDF 附件。请先上传 PDF 或自动检索全文，再提取文本。" />
      )}
      {textInfo && (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Card size="small" title="摘要（自动提取）">
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{textInfo.summary || '未能提取到摘要'}</Typography.Paragraph>
            {textInfo.keywords && <Typography.Text type="secondary">关键词：{textInfo.keywords}</Typography.Text>}
          </Card>
          <Card size="small" title={`全文文本（${textInfo.text.length.toLocaleString()} 字符）`}>
            <Typography.Paragraph type="secondary" style={{ maxHeight: 300, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
              {textInfo.text.slice(0, 4000)}
              {textInfo.text.length > 4000 ? '…' : ''}
            </Typography.Paragraph>
            <Alert type="info" showIcon message="完整文本可导出为 .md。在 ZCode 中用 nature-reader / deep-research 等技能处理，结果可粘贴回文献笔记。" />
          </Card>
        </Space>
      )}
    </Modal>

    {/* 阅读笔记弹窗 */}
    <Modal
      title={`阅读笔记：${noteTarget?.title ?? ''}`}
      open={!!noteTarget}
      onCancel={() => setNoteTarget(null)}
      footer={null}
      width={760}
      destroyOnClose
    >
      {noteTarget && <NotesPanel targetType="reference" targetId={noteTarget.id} />}
    </Modal>
  </>
)
}
