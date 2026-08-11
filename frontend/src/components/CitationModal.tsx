import { useEffect, useState } from 'react'
import { Button, Modal, Radio, Typography, message } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import type { Reference } from '../types'

const FORMATS = [
  { value: 'gbt7714', label: 'GB/T 7714（中文论文）' },
  { value: 'apa', label: 'APA 7' },
  { value: 'ieee', label: 'IEEE' },
]

/** 文献引用一键生成：三格式切换 + 批量复制 */
export default function CitationModal({
  open,
  references,
  onClose,
}: {
  open: boolean
  references: Reference[]
  onClose: () => void
}) {
  const [format, setFormat] = useState('gbt7714')
  const [citations, setCitations] = useState<string[]>([])

  useEffect(() => {
    if (!open || references.length === 0) return
    api.post('/references/citations/format', { ids: references.map((r) => r.id), format })
      .then((r) => setCitations(r.data.citations))
      .catch(() => setCitations([]))
  }, [open, references, format])

  const copyAll = () => {
    navigator.clipboard.writeText(citations.join('\n'))
    message.success(`已复制 ${citations.length} 条引用`)
  }

  return (
    <Modal
      title={`生成引用（${references.length} 篇）`}
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={copyAll} disabled={citations.length === 0}>
          复制全部
        </Button>,
        <Button key="close" onClick={onClose}>关闭</Button>,
      ]}
      width={680}
      destroyOnClose
    >
      <Radio.Group
        value={format}
        onChange={(e) => setFormat(e.target.value)}
        options={FORMATS}
        optionType="button"
        style={{ marginBottom: 12 }}
      />
      <div style={{ maxHeight: '50vh', overflow: 'auto', background: '#f4f5f1', borderRadius: 6, padding: 12 }}>
        {citations.length === 0 ? (
          <Typography.Text type="secondary">正在生成…</Typography.Text>
        ) : (
          citations.map((c, i) => (
            <div key={i} style={{ marginBottom: 8, fontSize: 13, lineHeight: 1.6 }}>
              <Typography.Text copyable={{ text: c }} style={{ display: 'block' }}>{c}</Typography.Text>
            </div>
          ))
        )}
      </div>
    </Modal>
  )
}
