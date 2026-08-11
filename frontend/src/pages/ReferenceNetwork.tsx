import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Checkbox, Descriptions, Empty, message, Modal, Popconfirm, Select, Space, Tag, Typography,
} from 'antd'
import {
  CloudSyncOutlined, DeleteOutlined, ReloadOutlined, RobotOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { splitTags } from '../utils'
import NetworkGraph from '../components/NetworkGraph'
import type { NetworkData, NetworkNode, NetworkStats, Reference } from '../types'

const WEIGHT_OPTIONS = [
  { value: 0, label: '全部关联' },
  { value: 10, label: '强度 ≥ 10' },
  { value: 20, label: '强度 ≥ 20' },
  { value: 30, label: '仅强关联 (≥30)' },
]

interface AiLinkRow {
  id: number
  ref_a: number
  ref_b: number
  title_a: string
  title_b: string
  weight: number
  reason: string
  tags: string[]
  method: string
}

/** 文献关联图谱视图（References 页 Tab 2） */
export default function ReferenceNetwork() {
  const [data, setData] = useState<NetworkData | null>(null)
  const [stats, setStats] = useState<NetworkStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [tagFilter, setTagFilter] = useState<string | undefined>()
  const [minWeight, setMinWeight] = useState(0)
  const [allTags, setAllTags] = useState<string[]>([])
  const [fetchingAll, setFetchingAll] = useState(false)
  const [detail, setDetail] = useState<Reference | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [relatedLinks, setRelatedLinks] = useState<NetworkData['links']>([])
  const [showAi, setShowAi] = useState(true)
  const [aiRunning, setAiRunning] = useState(false)
  const [aiManageOpen, setAiManageOpen] = useState(false)
  const [aiLinks, setAiLinks] = useState<AiLinkRow[]>([])
  const bump = useAppStore((s) => s.bump)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.get<NetworkData>('/references/network', { params: { tag: tagFilter, min_weight: minWeight } }),
      api.get<NetworkStats>('/references/network/stats'),
      api.get<Reference[]>('/references'),
    ])
      .then(([net, st, refs]) => {
        setData(net.data)
        setStats(st.data)
        const tags = new Set<string>()
        refs.data.forEach((r) => splitTags(r.tags).forEach((t) => tags.add(t)))
        setAllTags([...tags])
      })
      .catch(() => message.error('图谱加载失败'))
      .finally(() => setLoading(false))
  }, [tagFilter, minWeight])

  useEffect(load, [load])

  const fetchAll = () => {
    setFetchingAll(true)
    api
      .post('/references/fetch-all-citations')
      .then((r) => {
        const d = r.data
        message.success(`已抓取 ${d.refs} 篇文献的引用：共 ${d.fetched} 条，命中库内 ${d.matched} 条` +
          (d.errors ? `（${d.errors} 篇失败，可能离线或 DOI 无效）` : ''))
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '抓取失败'))
      .finally(() => setFetchingAll(false))
  }

  const openDetail = (node: NetworkNode) => {
    setDetailLoading(true)
    setRelatedLinks(data?.links.filter((l) => l.source === node.id || l.target === node.id) ?? [])
    api
      .get<Reference>(`/references/${node.id}`)
      .then((r) => setDetail(r.data))
      .catch(() => message.error('文献详情加载失败'))
      .finally(() => setDetailLoading(false))
  }

  const fetchOne = () => {
    if (!detail) return
    api
      .post(`/references/${detail.id}/fetch-citations`)
      .then((r) => {
        message.success(`抓取到 ${r.data.fetched} 条引用，其中 ${r.data.matched} 条命中库内文献`)
        bump()
        setDetail(null)
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '抓取失败'))
  }

  const nodeById = useMemo(() => {
    const m = new Map<number, NetworkNode>()
    data?.nodes.forEach((n) => m.set(n.id, n))
    return m
  }, [data])

  // AI 边可单独开关显示（客户端过滤，不重新请求）
  const graphData = useMemo(() => {
    if (!data) return null
    if (showAi) return data
    return { ...data, links: data.links.filter((l) => !l.ai) }
  }, [data, showAi])

  const runAutoLink = () => {
    setAiRunning(true)
    // 120s 客户端超时兜底：LLM 慢时避免无限等待（后端单批 60s 超时，超时自动降级本地特征）
    api.post('/references/ai-auto-link', {}, { timeout: 120000 })
      .then((r) => {
        if (r.data.created === 0) {
          message.warning(r.data.message ?? '未生成关联')
        } else {
          message.success(r.data.message)
        }
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? 'AI 自动关联失败（可重试，未配置 LLM 时使用本地特征相似度）'))
      .finally(() => setAiRunning(false))
  }

  const openAiManage = () => {
    api.get<AiLinkRow[]>('/references/ai-links')
      .then((r) => { setAiLinks(r.data); setAiManageOpen(true) })
      .catch(() => message.error('AI 关联列表加载失败'))
  }

  const clearAiLinks = () => {
    api.delete('/references/ai-links')
      .then(() => { message.success('已清除全部 AI 关联'); setAiLinks([]); bump() })
      .catch(() => message.error('清除失败'))
  }

  const deleteAiLink = (id: number) => {
    api.delete(`/references/ai-links/${id}`)
      .then(() => { setAiLinks((prev) => prev.filter((l) => l.id !== id)); bump() })
      .catch(() => message.error('删除失败'))
  }

  if (data && data.nodes.length < 2) {
    return (
      <Card loading={loading}>
        <Empty
          description="至少需要 2 篇文献才能形成关联网络。去「列表」页添加文献，或导入 BibTeX 后再来看看。"
          style={{ padding: '48px 0' }}
        />
      </Card>
    )
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {/* 工具栏 */}
      <Card size="small">
        <Space wrap>
          <Select
            placeholder="按标签过滤文献"
            allowClear
            style={{ width: 200 }}
            value={tagFilter}
            onChange={(v) => setTagFilter(v)}
            options={allTags.map((t) => ({ value: t, label: t }))}
          />
          <Select
            style={{ width: 150 }}
            value={minWeight}
            onChange={(v) => setMinWeight(v)}
            options={WEIGHT_OPTIONS}
          />
          <Popconfirm
            title="批量抓取全部文献的引用？"
            description="通过 OpenAlex 获取引用关系，需要联网，逐篇抓取可能需要一些时间。"
            onConfirm={fetchAll}
          >
            <Button icon={<CloudSyncOutlined />} loading={fetchingAll}>
              抓取全部引用
            </Button>
          </Popconfirm>
          <Popconfirm
            title="运行 AI 自动关联？"
            description="本地相似度预筛候选对后，由 LLM 批量评分（未配置 LLM 时自动用本地文本相似度）。重新生成会覆盖旧结果。"
            onConfirm={runAutoLink}
          >
            <Button type="primary" icon={<RobotOutlined />} loading={aiRunning}>
              AI 自动关联
            </Button>
          </Popconfirm>
          <Button icon={<DeleteOutlined />} onClick={openAiManage}>
            AI 关联管理
          </Button>
          <Checkbox checked={showAi} onChange={(e) => setShowAi(e.target.checked)}>
            显示 AI 关联
          </Checkbox>
          <Button icon={<ReloadOutlined />} onClick={() => bump()} title="刷新" />
          {stats && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              节点 {stats.node_count} · 关联 {stats.link_count} 条
              {stats.citation_link_count > 0 && `（含引用 ${stats.citation_link_count} 条）`}
              {stats.citations_fetched > 0 ? ` · ${stats.citations_fetched} 篇已抓取引用` : ''}
            </Typography.Text>
          )}
        </Space>
      </Card>

      {data && data.nodes.length > 200 && (
        <Alert
          type="info"
          showIcon
          message="文献较多，图谱可读性下降。建议用标签过滤后再查看。"
        />
      )}

      {/* 图例 */}
      <Space size="middle" style={{ paddingLeft: 4 }}>
        {Object.entries({ 未读: '#8a94a3', 在读: '#c8873a', 已读: '#4a6b52' }).map(([k, v]) => (
          <span key={k} style={{ fontSize: 12, color: '#5b6675' }}>
            <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: v, marginRight: 5 }} />
            {k}
          </span>
        ))}
        <span style={{ fontSize: 12, color: '#5b6675' }}>
          <span style={{ display: 'inline-block', width: 16, borderTop: '2px dashed #b03a2e', marginRight: 5, verticalAlign: 'middle' }} />
          引用关系（红虚线）
        </span>
        <span style={{ fontSize: 12, color: '#5b6675' }}>
          <span style={{ display: 'inline-block', width: 16, borderTop: '2px solid #A78BFA', marginRight: 5, verticalAlign: 'middle' }} />
          AI 语义关联（紫实线）
        </span>
      </Space>

      <Card loading={loading} bodyStyle={{ padding: 8 }}>
        {graphData && <NetworkGraph data={graphData} onNodeClick={openDetail} />}
      </Card>

      {/* 节点详情弹窗 */}
      <Modal
        title={detail?.title ?? '文献详情'}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={
          detail ? [
            <Button key="fetch" icon={<CloudSyncOutlined />} onClick={fetchOne}>
              抓取该文献引用
            </Button>,
            <Button key="close" type="primary" onClick={() => setDetail(null)}>
              关闭
            </Button>,
          ] : []
        }
        width={560}
      >
        {detailLoading ? (
          <Card loading />
        ) : detail ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Descriptions column={2} size="small">
              <Descriptions.Item label="作者">
                {detail.authors.slice(0, 4).join(', ')}{detail.authors.length > 4 ? ' 等' : ''}
              </Descriptions.Item>
              <Descriptions.Item label="年份">{detail.year ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="期刊/会议">
                <span title={detail.venue || ''} style={{ display: 'inline-block', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>
                  {detail.venue || '—'}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="DOI">{detail.doi || '—'}</Descriptions.Item>
              <Descriptions.Item label="阅读状态">
                <Tag>{detail.read_status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标签">
                {splitTags(detail.tags).map((t) => <Tag key={t}>{t}</Tag>)}
              </Descriptions.Item>
            </Descriptions>
            <div>
              <Typography.Text strong style={{ fontSize: 13 }}>关联文献（{relatedLinks.length}）</Typography.Text>
              <Space direction="vertical" size={2} style={{ width: '100%', marginTop: 8 }}>
                {relatedLinks.map((l) => {
                  const other = l.source === detail.id ? l.target : l.source
                  const node = nodeById.get(other)
                  if (!node) return null
                  return (
                    <div key={`${l.source}-${l.target}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div style={{ minWidth: 0 }}>
                        <Typography.Text ellipsis style={{ maxWidth: 300, display: 'block' }}>{node.title}</Typography.Text>
                        {l.ai && l.reason && (
                          <Typography.Text style={{ fontSize: 11, color: '#A78BFA' }}>
                            🤖 {l.reason}
                            {(l.ai_tags ?? []).map((t) => <Tag key={t} color="purple" style={{ fontSize: 10, marginLeft: 4 }}>{t}</Tag>)}
                          </Typography.Text>
                        )}
                      </div>
                      <Typography.Text type="secondary" style={{ fontSize: 12, flexShrink: 0 }}>
                        强度 {l.weight}
                        {l.citation && <Tag color="red" style={{ marginLeft: 6 }}>引用</Tag>}
                      </Typography.Text>
                    </div>
                  )
                })}
              </Space>
            </div>
          </Space>
        ) : null}
      </Modal>

      {/* AI 关联管理弹窗 */}
      <Modal
        title="AI 自动关联管理"
        open={aiManageOpen}
        onCancel={() => setAiManageOpen(false)}
        width={720}
        footer={[
          <Popconfirm key="clear" title="清除全部 AI 关联？" description="该操作不可撤销，可重新运行 AI 自动关联生成。" onConfirm={clearAiLinks}>
            <Button danger>全部清除</Button>
          </Popconfirm>,
          <Button key="close" type="primary" onClick={() => setAiManageOpen(false)}>关闭</Button>,
        ]}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          共 {aiLinks.length} 条 AI 关联。运行「AI 自动关联」可整体重新生成；此处可逐条删除或一键清除。
        </Typography.Paragraph>
        {aiLinks.length === 0 ? (
          <Empty description="暂无 AI 关联，点击工具栏「AI 自动关联」生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={2}>
            {aiLinks.map((l) => (
              <div key={l.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 4px', borderBottom: '1px solid #1E293B' }}>
                <Tag color="purple" style={{ flexShrink: 0 }}>{l.weight}</Tag>
                <Typography.Text ellipsis style={{ flex: 1, fontSize: 12 }} title={`${l.title_a} ⇄ ${l.title_b}`}>
                  {l.title_a} ⇄ {l.title_b}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>
                  {l.method === 'llm' ? 'LLM' : '本地'}{l.tags.length > 0 && ` · ${l.tags.slice(0, 2).join('/')}`}
                </Typography.Text>
                <Popconfirm title="删除该条 AI 关联？" onConfirm={() => deleteAiLink(l.id)}>
                  <Button size="small" danger type="text" icon={<DeleteOutlined />} />
                </Popconfirm>
              </div>
            ))}
          </Space>
        )}
      </Modal>
    </Space>
  )
}
