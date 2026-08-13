import { useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Space, Spin, Tabs, Tag, Typography, message } from 'antd'
import { ReloadOutlined, RobotOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { LlmSettingsForm } from '../components/LlmSettings'
import { LlmUsageContent } from '../components/LlmUsageModal'
import { useAppStore } from '../store'

interface ProviderStatus {
  source: string
  overall: 'operational' | 'degraded' | 'outage' | 'unknown'
  description: string
  components: { name: string; status: string; label: string }[]
  incidents: { title: string; impact: string }[]
  status_url: string
  fetched_at: string
  cached?: boolean
}

interface ApiStatus {
  configured: boolean
  provider: string
  model: string
  online: boolean
  availability_pct: number | null
  total_checks: number
  ok_checks: number
  latency_ms: number | null
  endpoint: string
  checked_at: string
}

const OVERALL_META: Record<string, { label: string; color: string; emoji: string }> = {
  operational: { label: '正常运行', color: 'green', emoji: '🟢' },
  degraded: { label: '性能下降', color: 'orange', emoji: '🟡' },
  outage: { label: '服务中断', color: 'red', emoji: '🔴' },
  unknown: { label: '未知', color: 'default', emoji: '⚪' },
}

/** Provider 服务状态卡片（status.deepseek.com 等状态页 + 本地 API 探测） */
function ServiceStatusTab() {
  const [ps, setPs] = useState<ProviderStatus | null>(null)
  const [psLoading, setPsLoading] = useState(false)
  const [apiStatus, setApiStatus] = useState<ApiStatus | null>(null)
  const [apiLoading, setApiLoading] = useState(false)
  const bump = useAppStore((s) => s.bump)

  const loadPs = (force = false) => {
    setPsLoading(true)
    const req = force
      ? api.post<ProviderStatus>('/llm/provider-status/refresh', {}, { timeout: 30000 })
      : api.get<ProviderStatus>('/llm/provider-status')
    req
      .then((r) => setPs(r.data))
      .catch((e) => message.error(e.response?.data?.detail ?? '状态页加载失败'))
      .finally(() => setPsLoading(false))
  }
  useEffect(() => { loadPs() }, [])

  const probeApi = () => {
    setApiLoading(true)
    api.post<ApiStatus>('/llm/status/refresh', {}, { timeout: 20000 })
      .then((r) => {
        setApiStatus(r.data)
        r.data.configured && (r.data.online
          ? message.success(`API 在线（${r.data.latency_ms ?? '-'}ms）`)
          : message.warning('API 探测失败'))
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '探测失败'))
      .finally(() => setApiLoading(false))
  }
  useEffect(() => { api.get<ApiStatus>('/llm/status').then((r) => setApiStatus(r.data)).catch(() => {}) }, [])

  const meta = OVERALL_META[ps?.overall ?? 'unknown']
  const degraded = ps && ps.overall !== 'operational' && ps.overall !== 'unknown'

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {/* 性能下降/中断 Alert（核心提示） */}
      {degraded && (
        <Alert
          type={ps!.overall === 'outage' ? 'error' : 'warning'}
          showIcon
          message={`${ps!.overall === 'outage' ? '🔴 Provider 服务中断' : '🟡 Provider API 性能下降'}`}
          description={
            <span>
              {ps!.description || '服务商状态页报告异常。'}{' '}
              {ps!.fetched_at && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  （检测于 {ps!.fetched_at.replace('T', ' ').slice(0, 16)}，来源 {ps!.source}）
                </Typography.Text>
              )}
            </span>
          }
          closable={false}
        />
      )}

      <Card
        size="small"
        title={<span><RobotOutlined style={{ marginRight: 6 }} />Provider 服务状态（status.deepseek.com 等）</span>}
        extra={<Button size="small" icon={<ReloadOutlined />} loading={psLoading} onClick={() => loadPs(true)}>立即刷新</Button>}
      >
        {psLoading && !ps ? (
          <Spin />
        ) : !ps ? (
          <Typography.Text type="secondary">状态页加载失败，可点击「立即刷新」重试。</Typography.Text>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="整体状态">
                <Tag color={meta.color}>{meta.emoji} {meta.label}</Tag>
                {ps.cached && <Typography.Text type="secondary" style={{ fontSize: 11 }}>（缓存）</Typography.Text>}
              </Descriptions.Item>
              <Descriptions.Item label="状态说明">
                <Typography.Text>{ps.description || '—'}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态页地址">
                <Typography.Link href={ps.status_url} target="_blank" style={{ fontSize: 12 }}>
                  {ps.status_url}
                </Typography.Link>
              </Descriptions.Item>
              <Descriptions.Item label="最近检查">
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {ps.fetched_at ? ps.fetched_at.replace('T', ' ').slice(0, 16) : '—'}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>

            {ps.components.length > 0 && (
              <div>
                <Typography.Text strong style={{ fontSize: 12 }}>服务组件</Typography.Text>
                <div style={{ marginTop: 6 }}>
                  <Space size={[8, 6]} wrap>
                    {ps.components.map((c) => (
                      <Tag key={c.name} color={c.status.includes('operational') ? 'green' : c.status.includes('degraded') ? 'orange' : 'red'}>
                        {c.name} · {c.label}
                      </Tag>
                    ))}
                  </Space>
                </div>
              </div>
            )}

            {ps.incidents.length > 0 && (
              <div>
                <Typography.Text strong style={{ fontSize: 12 }}>未解决事件</Typography.Text>
                <Space direction="vertical" size={2} style={{ width: '100%', marginTop: 4 }}>
                  {ps.incidents.map((inc, i) => (
                    <Typography.Text key={i} style={{ fontSize: 12 }}>
                      🔧 {inc.title}（{inc.impact}）
                    </Typography.Text>
                  ))}
                </Space>
              </div>
            )}

            {ps.overall === 'unknown' && (
              <Alert type="info" showIcon message="状态页不可达或未配置"
                description="可在「模型设置」中填写 Provider 状态页地址（如 https://status.deepseek.com），或稍后刷新。" />
            )}
          </Space>
        )}
      </Card>

      {/* 本地 API 探测 */}
      <Card
        size="small"
        title="本地 API 探测（/models 轻量检查）"
        extra={<Button size="small" icon={<ReloadOutlined />} loading={apiLoading} onClick={probeApi}>立即探测</Button>}
      >
        {!apiStatus?.configured ? (
          <Typography.Text type="secondary">未配置 LLM API，请先到「模型设置」配置。</Typography.Text>
        ) : (
          <Space direction="vertical" size={4}>
            <Space size={8}>
              <span style={{ fontSize: 18, lineHeight: 1 }}>{apiStatus.online ? '🟢' : '🔴'}</span>
              <Typography.Text strong>{apiStatus.online ? '在线' : '离线'}</Typography.Text>
              {apiStatus.availability_pct != null && (
                <Tag color="blue">可用性 {apiStatus.availability_pct}%（{apiStatus.ok_checks}/{apiStatus.total_checks} 次）</Tag>
              )}
              {apiStatus.latency_ms != null && <Tag>{apiStatus.latency_ms}ms</Tag>}
            </Space>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              模型：{apiStatus.model || '—'} · 探测端点：{apiStatus.endpoint || '—'} · 最近探测：{apiStatus.checked_at || '—'}
            </Typography.Text>
          </Space>
        )}
      </Card>
    </Space>
  )
}

/** AI 状态页：服务状态 / 模型设置 / 用量与余额（侧边栏「AI 状态」二级菜单） */
export default function AiStatus() {
  const nav = useNavigate()
  const { sub = 'overview' } = useParams()

  return (
    <Tabs
      activeKey={sub}
      onChange={(k) => nav(`/ai-status/${k}`)}
      items={[
        { key: 'overview', label: '服务状态', children: <ServiceStatusTab /> },
        { key: 'settings', label: '模型设置', children: <LlmSettingsForm /> },
        { key: 'usage', label: '用量与余额', children: <LlmUsageContent /> },
      ]}
    />
  )
}
