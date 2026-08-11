import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, Input, Modal, Row, Space, Statistic, Table, Tag, Typography, message,
} from 'antd'
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import { api } from '../api/client'

interface UsageAgg {
  calls: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cache_hit_tokens: number
  cost: number
  currency: string
}
interface UsageData {
  today: UsageAgg
  month: UsageAgg
  total: UsageAgg
  by_model: { model: string; calls: number; total_tokens: number; prompt_tokens: number; completion_tokens: number; cache_hit_tokens: number; cost: number }[]
}
interface Balance {
  is_available: boolean
  total_balance: number
  currency: string
  note?: string
  manual?: boolean
  fetched_at?: string
}
interface ModelMeta { model: string; context_window: number; input_price_per_m: number; output_price_per_m: number; cache_price_per_m: number; currency: string }

const fmtTokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n))
const fmtCost = (n: number) => (n >= 100 ? n.toFixed(0) : n >= 1 ? n.toFixed(2) : n.toFixed(4))

/** LLM 用量详情：统计卡 + 余额（刷新/手动）+ 分模型明细 */
export default function LlmUsageModal({ open, onClose, onOpenLlm }: {
  open: boolean
  onClose: () => void
  onOpenLlm?: () => void
}) {
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [balance, setBalance] = useState<Balance | null>(null)
  const [models, setModels] = useState<ModelMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [manual, setManual] = useState('')
  const [savingManual, setSavingManual] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([
      api.get<UsageData>('/llm/usage'),
      api.get<Balance>('/llm/balance'),
      api.get<ModelMeta[]>('/llm/models'),
    ]).then(([u, b, m]) => {
      setUsage(u.data)
      setBalance(b.data)
      setModels(m.data)
      setManual(b.data?.manual ? String(b.data.total_balance) : '')
    }).catch(() => message.error('用量统计加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { if (open) load() }, [open])

  const refreshBalance = () => {
    setRefreshing(true)
    api.post<Balance>('/llm/balance/refresh')
      .then((r) => { setBalance(r.data); message.success('余额已刷新') })
      .catch((e) => message.error(e.response?.data?.detail ?? '刷新失败'))
      .finally(() => setRefreshing(false))
  }

  const saveManual = () => {
    setSavingManual(true)
    api.put<Balance>('/llm/balance', { manual })
      .then((r) => { setBalance(r.data); message.success('已保存') })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
      .finally(() => setSavingManual(false))
  }

  const cur = usage?.today
  const mon = usage?.month
  const total = usage?.total
  const bal = balance

  return (
    <Modal title={<span><ReloadOutlined style={{ marginRight: 8 }} />LLM 用量与余额</span>}
      open={open} onCancel={onClose} width={760}
      footer={[
        <Button key="set" icon={<SettingOutlined />} onClick={onOpenLlm}>模型配置（⚙️）</Button>,
        <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
      ]}>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>加载中…</div>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* 余额 */}
          <Card size="small" title="账户余额" extra={
            <Space>
              <Button size="small" icon={<ReloadOutlined />} loading={refreshing} onClick={refreshBalance}>刷新</Button>
            </Space>
          }>
            {bal?.is_available ? (
              <Space wrap size="middle">
                <Typography.Text style={{ fontSize: 26, fontWeight: 800, color: '#34D399' }}>
                  {bal.currency === 'USD' ? '$' : '¥'}{bal.total_balance}
                </Typography.Text>
                {bal.manual && <Tag color="orange">手动填写</Tag>}
                {bal.fetched_at && <Typography.Text type="secondary" style={{ fontSize: 11 }}>更新于 {bal.fetched_at.slice(0, 16).replace('T', ' ')}</Typography.Text>}
              </Space>
            ) : (
              <Alert type="warning" showIcon message="余额不可自动查询" description={bal?.note ?? ''} />
            )}
            <div style={{ marginTop: 10 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>手动填写余额（留空则使用自动查询）</Typography.Text>
              <Space.Compact style={{ width: '100%', marginTop: 4 }}>
                <Input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="如 12.34" style={{ maxWidth: 200 }} />
                <Button type="primary" loading={savingManual} onClick={saveManual}>保存</Button>
              </Space.Compact>
            </div>
          </Card>

          {/* 用量统计 */}
          <Row gutter={[12, 12]}>
            <Col span={8}><Card size="small"><Statistic title="今日" value={cur?.total_tokens ?? 0} suffix="tok" />
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>{cur?.calls ?? 0} 次调用 · 约 ¥{fmtCost(cur?.cost ?? 0)}</Typography.Text></Card></Col>
            <Col span={8}><Card size="small"><Statistic title="本月" value={mon?.total_tokens ?? 0} suffix="tok" />
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>{mon?.calls ?? 0} 次调用 · 约 ¥{fmtCost(mon?.cost ?? 0)}</Typography.Text></Card></Col>
            <Col span={8}><Card size="small"><Statistic title="累计" value={total?.total_tokens ?? 0} suffix="tok" />
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>{total?.calls ?? 0} 次调用 · 约 ¥{fmtCost(total?.cost ?? 0)}</Typography.Text></Card></Col>
          </Row>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            费用为按模型单价折算的估算值（输入/输出/缓存命中分价），可在「模型配置」中调整单价。
          </Typography.Text>

          {/* 分模型明细 */}
          <Card size="small" title="分模型用量">
            <Table<UsageData['by_model'][number]>
              rowKey="model" size="small" pagination={false}
              dataSource={usage?.by_model ?? []}
              columns={[
                { title: '模型', dataIndex: 'model' },
                { title: '调用', dataIndex: 'calls', width: 70 },
                { title: '输入 tok', dataIndex: 'prompt_tokens', width: 100, render: (v: number) => fmtTokens(v) },
                { title: '输出 tok', dataIndex: 'completion_tokens', width: 100, render: (v: number) => fmtTokens(v) },
                { title: '缓存命中', dataIndex: 'cache_hit_tokens', width: 100, render: (v: number) => (v > 0 ? fmtTokens(v) : '—') },
                { title: '费用', dataIndex: 'cost', width: 90, render: (v: number) => `¥${fmtCost(v)}` },
              ]}
              locale={{ emptyText: '暂无调用记录' }}
            />
          </Card>

          {/* 模型元数据（上下文/单价）速览 */}
          <Card size="small" title="模型元数据（上下文窗口 / 单价）">
            <Table<ModelMeta>
              rowKey="model" size="small" pagination={false}
              dataSource={models}
              columns={[
                { title: '模型', dataIndex: 'model' },
                { title: '上下文', dataIndex: 'context_window', width: 90, render: (v: number) => (v > 0 ? `${Math.round(v / 1024)}K` : '—') },
                { title: '输入价/1M', dataIndex: 'input_price_per_m', width: 100, render: (v: number) => (v > 0 ? `${v} ${models.find((m) => m.input_price_per_m === v)?.currency ?? ''}` : '免费') },
                { title: '输出价/1M', dataIndex: 'output_price_per_m', width: 100, render: (v: number) => (v > 0 ? String(v) : '免费') },
                { title: '缓存价/1M', dataIndex: 'cache_price_per_m', width: 100, render: (v: number) => (v > 0 ? String(v) : '—') },
              ]}
              locale={{ emptyText: '暂无模型数据' }}
            />
          </Card>
        </Space>
      )}
    </Modal>
  )
}
