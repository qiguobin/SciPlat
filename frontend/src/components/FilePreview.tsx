import { useEffect, useState } from 'react'
import { Alert, Modal, Spin } from 'antd'
import { api } from '../api/client'
import type { Material } from '../types'

const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg']
const TEXT_EXTS = [
  'txt', 'md', 'py', 'c', 'cpp', 'h', 'java', 'js', 'ts', 'json', 'tex', 'csv',
  'yml', 'yaml', 'xml', 'html', 'css', 'sh', 'bat', 'r', 'sql', 'log',
]

export default function FilePreview({
  material,
  onClose,
}: {
  material: Material | null
  onClose: () => void
}) {
  const [text, setText] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ext = material?.file_name.split('.').pop()?.toLowerCase() ?? ''
  const isPdf = ext === 'pdf'
  const isImage = IMAGE_EXTS.includes(ext)
  const isText = TEXT_EXTS.includes(ext)

  useEffect(() => {
    if (!material || !isText) return
    setError('')
    setText(null)
    setLoading(true)
    api
      .get(`/materials/${material.id}/preview`, { responseType: 'text' })
      .then((r) => setText(String(r.data)))
      .catch((e) => setError(e.response?.data?.detail ?? '预览失败'))
      .finally(() => setLoading(false))
  }, [material?.id, isText, material])

  const url = `/api/materials/${material?.id}/preview`

  return (
    <Modal open={!!material} title={material?.name} onCancel={onClose} footer={null} width={960}>
      {error && <Alert type="error" message={error} showIcon />}
      {material && isPdf && (
        <iframe src={url} title="pdf-preview" style={{ width: '100%', height: '72vh', border: 'none' }} />
      )}
      {material && isImage && (
        <div style={{ textAlign: 'center' }}>
          <img src={url} alt={material.name} style={{ maxWidth: '100%', maxHeight: '72vh' }} />
        </div>
      )}
      {material && isText && (loading ? <Spin style={{ margin: 24 }} /> : (
        <pre style={{ maxHeight: '72vh', overflow: 'auto', fontSize: 13, margin: 0 }}>
          {text ?? ''}
        </pre>
      ))}
      {material && !isPdf && !isImage && !isText && !error && (
        <Alert type="info" message="该类型不支持在线预览，请下载查看。" showIcon />
      )}
    </Modal>
  )
}
