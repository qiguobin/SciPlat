import { useEffect, useState } from 'react'
import { Alert, Button, Dropdown, Modal, Space, Upload, message } from 'antd'
import { CloudDownloadOutlined, CloudUploadOutlined, DatabaseOutlined, FileExcelOutlined } from '@ant-design/icons'
import { api } from '../api/client'

/** 数据管理：全库备份导出 / 从备份恢复 */
export default function DataManager({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [restoring, setRestoring] = useState(false)
  const [autoBackups, setAutoBackups] = useState<{ name: string; size: number; created_at: string }[]>([])

  useEffect(() => {
    if (!open) return
    api.get<{ items: { name: string; size: number; created_at: string }[] }>('/backup/auto-list')
      .then((r) => setAutoBackups(r.data.items)).catch(() => {})
  }, [open])

  const csvItems = [
    { key: 'todos', label: '待办清单.csv' },
    { key: 'experiments', label: '实验记录.csv' },
    { key: 'achievements', label: '成果.csv' },
    { key: 'references', label: '文献.csv' },
    { key: 'writing', label: '写作打卡.csv' },
  ]

  const restore = (file: File) => {
    setRestoring(true)
    const fd = new FormData()
    fd.append('file', file)
    api.post('/backup/restore', fd)
      .then((r) => {
        message.success(r.data.message ?? '恢复成功')
        onClose()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '恢复失败'))
      .finally(() => setRestoring(false))
  }

  return (
    <Modal
      title={<span><DatabaseOutlined style={{ marginRight: 8 }} />数据管理</span>}
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Button type="primary" icon={<CloudDownloadOutlined />} href="/api/backup/download">
            导出全库备份（zip）
          </Button>
          <div style={{ color: '#8a94a3', fontSize: 12, marginTop: 6 }}>
            包含数据库与全部上传文件。建议定期备份到网盘或移动硬盘。
          </div>
        </div>
        <div>
          <Space>
            <Upload
              accept=".zip"
              showUploadList={false}
              beforeUpload={(f) => { restore(f); return false }}
            >
              <Button icon={<CloudUploadOutlined />} loading={restoring}>从备份恢复</Button>
            </Upload>
            <Dropdown menu={{ items: csvItems.map((c) => ({ key: c.key, label: c.label, onClick: () => window.open(`/api/export/csv?kind=${c.key}`) })) }}>
              <Button icon={<FileExcelOutlined />}>导出 CSV</Button>
            </Dropdown>
          </Space>
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 8 }}
            message="恢复会替换当前全部数据"
            description="恢复前会自动把当前数据备份到 data/pre-restore-* 目录。恢复后需要重启应用生效。"
          />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>自动备份（启动时检查，超 7 天自动备份，保留最近 5 份）</div>
          {autoBackups.length === 0 ? (
            <span style={{ color: '#8a94a3', fontSize: 12 }}>暂无自动备份</span>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: '#94A3B8' }}>
              {autoBackups.slice(0, 5).map((b) => (
                <li key={b.name}>{b.name}（{(b.size / 1024).toFixed(0)} KB）</li>
              ))}
            </ul>
          )}
        </div>
      </Space>
    </Modal>
  )
}
