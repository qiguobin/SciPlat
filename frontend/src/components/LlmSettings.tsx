import { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, Modal, Radio, Space, Tag, Typography, message } from 'antd'
import { ApiOutlined, SyncOutlined } from '@ant-design/icons'
import { api } from '../api/client'

interface LlmConfig {
  provider: string
  base_url: string
  api_key: string
  model: string
  ollama_url: string
  context_window: number
  input_price_per_m: number
  output_price_per_m: number
  cache_price_per_m: number
  model_route: Record<string, string>
  provider_status_url?: string
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
  history: boolean[]
}

// 任务→模型 路由（按任务选模型，实现成本优化）
const ROUTE_LABELS: [string, string][] = [
  ['default', '默认（未指定任务时）'],
  ['chat', '文献对话 / 通用问答'],
  ['summary', '解读 / 十问 / 综述 / 纪要'],
  ['review', '投稿审查'],
  ['polish', '写作润色'],
  ['link', 'AI 自动关联'],
  ['metadata', '元数据补全'],
  ['report', '周报 / 月报'],
]

/** LLM 设置表单（无 Modal 外壳，供「AI 状态」页面与弹窗复用） */
export function LlmSettingsForm({ onSaved }: { onSaved?: () => void } = {}) {
  const [form] = Form.useForm()
  const [config, setConfig] = useState<LlmConfig | null>(null)
  const [testing, setTesting] = useState(false)
  const [status, setStatus] = useState<ApiStatus | null>(null)
  const [probing, setProbing] = useState(false)

  useEffect(() => {
    api.get<LlmConfig>('/settings/llm').then((r) => {
      setConfig(r.data)
      form.setFieldsValue(r.data)
    }).catch(() => {})
    api.get<ApiStatus>('/llm/status').then((r) => setStatus(r.data)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const probe = () => {
    setProbing(true)
    api.post<ApiStatus>('/llm/status/refresh', {}, { timeout: 20000 })
      .then((r) => {
        setStatus(r.data)
        if (r.data.configured) {
          r.data.online
            ? message.success(`API 在线（${r.data.latency_ms ?? '-'}ms），可用性 ${r.data.availability_pct ?? '-'}%`)
            : message.warning('API 探测失败（离线或地址/Key 错误）')
        }
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '探测失败'))
      .finally(() => setProbing(false))
  }

  const save = () => {
    form.validateFields().then((v) => {
      api.put('/settings/llm', v).then(() => {
        message.success('LLM 配置已保存')
        onSaved?.()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const test = () => {
    setTesting(true)
    form.validateFields().then((v) => {
      // 先保存再测试；客户端 25s 超时兜底（后端测试超时 20s），避免错误地址长时间卡页面
      api.put('/settings/llm', v)
        .then(() => api.post('/llm/test', {}, { timeout: 25000 }))
        .then((r) => message.success(`连接成功：${r.data.reply ?? ''}`))
        .catch((e) => message.error(e.response?.data?.detail ?? '连接失败（请检查地址/Key/模型名或网络）'))
        .finally(() => setTesting(false))
    }).catch(() => setTesting(false))
  }

  const provider = Form.useWatch('provider', form)

  return (
    <Form form={form} layout="vertical" initialValues={{ provider: 'openai', ollama_url: 'http://127.0.0.1:11434' }}>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        配置后即可使用：文献 AI 问答/解读/十问、AI 综述、划词翻译、论文投稿建议等。
        OpenAI 兼容 API 支持 DeepSeek / 通义千问 / 月之暗面 / OpenAI 等；Ollama 为完全离线方案。
      </Typography.Paragraph>
      <Form.Item name="provider" label="Provider">
        <Radio.Group
          options={[
            { value: 'openai', label: 'OpenAI 兼容 API' },
            { value: 'ollama', label: 'Ollama 本地' },
          ]}
        />
      </Form.Item>
      {provider === 'openai' ? (
        <>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true, message: '请输入 API 地址' }]}>
            <Input placeholder="如 https://api.deepseek.com/v1 或 https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder="sk-..." />
          </Form.Item>
          <Form.Item name="model" label="模型" rules={[{ required: true, message: '请输入模型名' }]}>
            <Input placeholder="如 deepseek-chat / qwen-plus / gpt-4o-mini" />
          </Form.Item>
        </>
      ) : (
        <>
          <Form.Item name="ollama_url" label="Ollama 地址">
            <Input placeholder="http://127.0.0.1:11434" />
          </Form.Item>
          <Form.Item name="model" label="模型" rules={[{ required: true, message: '请输入模型名' }]}>
            <Input placeholder="如 qwen2.5 / llama3.1（需已 pull）" />
          </Form.Item>
        </>
      )}
      {config && config.api_key && provider === 'openai' && (
        <Alert type="info" showIcon message="已保存 API Key，可重新输入覆盖。" style={{ marginTop: 4 }} />
      )}
      <Card
        size="small"
        title="API 服务状态"
        style={{ marginBottom: 16 }}
        extra={<Button size="small" icon={<SyncOutlined />} loading={probing} onClick={probe}>立即探测</Button>}
      >
        {!status?.configured ? (
          <Typography.Text type="secondary">
            未配置 LLM API（或配置不完整），保存配置后可探测服务状态。
          </Typography.Text>
        ) : status.total_checks === 0 ? (
          <Typography.Text type="secondary">
            尚未探测。点击「立即探测」检查 {status.provider === 'ollama' ? 'Ollama' : 'API'} 服务可用性。
          </Typography.Text>
        ) : (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Space size={8}>
              <span style={{ fontSize: 18, lineHeight: 1 }}>{status.online ? '🟢' : '🔴'}</span>
              <Typography.Text strong>{status.online ? '在线' : '离线'}</Typography.Text>
              <Tag color="blue">
                可用性 {status.availability_pct ?? '-'}%（{status.ok_checks}/{status.total_checks} 次）
              </Tag>
              {status.latency_ms != null && <Tag>{status.latency_ms}ms</Tag>}
            </Space>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              模型：{status.model || '—'} · 探测端点：{status.endpoint || '—'} · 最近探测：{status.checked_at || '—'}
            </Typography.Text>
          </Space>
        )}
      </Card>
      <Form.Item label="模型参数（状态栏用量/费用估算用，可留空用预设）">
        <Space.Compact style={{ width: '100%' }}>
          <Form.Item name="context_window" noStyle>
            <Input type="number" placeholder="上下文窗口(如 128000)" style={{ width: '40%' }} />
          </Form.Item>
          <Form.Item name="input_price_per_m" noStyle>
            <Input type="number" step="0.01" placeholder="输入价/百万tok" style={{ width: '20%' }} />
          </Form.Item>
          <Form.Item name="output_price_per_m" noStyle>
            <Input type="number" step="0.01" placeholder="输出价/百万tok" style={{ width: '20%' }} />
          </Form.Item>
          <Form.Item name="cache_price_per_m" noStyle>
            <Input type="number" step="0.01" placeholder="缓存价/百万tok" style={{ width: '20%' }} />
          </Form.Item>
        </Space.Compact>
      </Form.Item>
      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
        单价用于折算费用（估算，可在「用量与余额」中查看）；Ollama 本地免费。
      </Typography.Text>
      <Form.Item label="任务 → 模型 路由（成本优化：不同任务用不同模型，留空 = 默认模型）">
        <Space direction="vertical" style={{ width: '100%' }} size={2}>
          {ROUTE_LABELS.map(([key, label]) => (
            <Space key={key} style={{ width: '100%' }}>
              <Typography.Text style={{ width: 150, fontSize: 12, flexShrink: 0 }}>{label}</Typography.Text>
              <Form.Item name={['model_route', key]} noStyle>
                <Input placeholder="模型名（留空用默认）" style={{ width: 220 }} />
              </Form.Item>
            </Space>
          ))}
        </Space>
      </Form.Item>
      <Form.Item label="Provider 状态页地址（status.deepseek.com 等，留空自动识别）">
        <Form.Item name="provider_status_url" noStyle>
          <Input placeholder="如 https://status.deepseek.com" />
        </Form.Item>
      </Form.Item>
      <Space>
        <Button onClick={test} loading={testing}>测试连接</Button>
        <Button type="primary" onClick={save}>保存</Button>
      </Space>
    </Form>
  )
}

/** LLM 设置弹窗（快速入口兼容壳） */
export default function LlmSettings({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal title={<span><ApiOutlined style={{ marginRight: 8 }} />AI 设置（LLM）</span>}
      open={open} onCancel={onClose}
      footer={null}
      width={560} destroyOnClose
    >
      {open && <LlmSettingsForm />}
    </Modal>
  )
}
