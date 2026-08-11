import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, Modal, Radio, Space, Typography, message } from 'antd'
import { ApiOutlined } from '@ant-design/icons'
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
}

/** LLM 设置：OpenAI 兼容 API + Ollama 双通道 */
export default function LlmSettings({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm()
  const [config, setConfig] = useState<LlmConfig | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    if (!open) return
    api.get<LlmConfig>('/settings/llm').then((r) => {
      setConfig(r.data)
      form.setFieldsValue(r.data)
    }).catch(() => {})
  }, [open, form])

  const save = () => {
    form.validateFields().then((v) => {
      api.put('/settings/llm', v).then(() => {
        message.success('LLM 配置已保存')
        onClose()
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
    <Modal title={<span><ApiOutlined style={{ marginRight: 8 }} />AI 设置（LLM）</span>}
      open={open} onCancel={onClose}
      footer={
        <Space>
          <Button onClick={test} loading={testing}>测试连接</Button>
          <Button type="primary" onClick={save}>保存</Button>
        </Space>
      }
      width={560} destroyOnClose
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        配置后即可使用：文献 AI 问答/解读/十问、AI 综述、划词翻译、论文投稿建议等。
        OpenAI 兼容 API 支持 DeepSeek / 通义千问 / 月之暗面 / OpenAI 等；Ollama 为完全离线方案。
      </Typography.Paragraph>
      <Form form={form} layout="vertical" initialValues={{ provider: 'openai', ollama_url: 'http://127.0.0.1:11434' }}>
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
          单价用于折算费用（估算，可在「LLM 用量与余额」中查看）；Ollama 本地免费。
        </Typography.Text>
      </Form>
    </Modal>
  )
}
