import { useEffect, useState } from 'react'
import {
  Alert, Button, Collapse, Dropdown, Input, Modal, Popconfirm, Space, Tag, Upload, message,
} from 'antd'
import {
  CloudDownloadOutlined, CloudServerOutlined, CloudUploadOutlined, DatabaseOutlined, FileExcelOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'

interface AutoBackup { name: string; size: number; encrypted: boolean; sha256: string; created_at: string }
interface CloudFile { name: string; size: number; modified: string }

const fmtSize = (n: number) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`)

/** 数据管理：全库备份 / 恢复 / 加密 / WebDAV 云备份 */
export default function DataManager({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [restoring, setRestoring] = useState(false)
  const [autoBackups, setAutoBackups] = useState<AutoBackup[]>([])
  const [encrypting, setEncrypting] = useState<string | null>(null)
  const [encPass, setEncPass] = useState('')
  // WebDAV
  const [wdUrl, setWdUrl] = useState('')
  const [wdUser, setWdUser] = useState('')
  const [wdPass, setWdPass] = useState('')
  const [wdEnabled, setWdEnabled] = useState(false)
  const [cloudFiles, setCloudFiles] = useState<CloudFile[]>([])
  const [wdBusy, setWdBusy] = useState(false)
  const [restorePass, setRestorePass] = useState('')
  const [cloudRestorePass, setCloudRestorePass] = useState('')

  const loadAll = () => {
    api.get<{ items: AutoBackup[] }>('/backup/auto-list')
      .then((r) => setAutoBackups(r.data.items)).catch(() => {})
    api.get<{ url: string; user: string; enabled: boolean }>('/backup/webdav/settings')
      .then((r) => {
        setWdUrl(r.data.url)
        setWdUser(r.data.user)
        setWdEnabled(r.data.enabled)
      }).catch(() => {})
    api.get<{ items: CloudFile[] }>('/backup/webdav/list')
      .then((r) => setCloudFiles(r.data.items)).catch(() => {})
  }
  useEffect(() => { if (open) loadAll() }, [open])

  const restore = (file: File) => {
    setRestoring(true)
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', restorePass)
    api.post('/backup/restore', fd)
      .then((r) => {
        message.success(r.data.message ?? '恢复成功')
        onClose()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '恢复失败'))
      .finally(() => setRestoring(false))
  }

  const encryptBackup = (name: string) => {
    if (!encPass) { message.warning('请先输入加密密码'); return }
    setEncrypting(name)
    api.post('/backup/encrypt', { name, password: encPass })
      .then((r) => { message.success(r.data.message); setEncPass(''); loadAll() })
      .catch((e) => message.error(e.response?.data?.detail ?? '加密失败'))
      .finally(() => setEncrypting(null))
  }

  const saveWebdav = () => {
    setWdBusy(true)
    api.put('/backup/webdav/settings', { url: wdUrl, user: wdUser, pass: wdPass, enabled: wdEnabled })
      .then(() => { message.success('WebDAV 配置已保存'); setWdPass(''); loadAll() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
      .finally(() => setWdBusy(false))
  }

  const testWebdav = () => {
    setWdBusy(true)
    api.post('/backup/webdav/test', { url: wdUrl, user: wdUser, pass: wdPass })
      .then((r) => message.success(r.data.note ?? '连接成功'))
      .catch((e) => message.error(e.response?.data?.detail ?? '连接失败'))
      .finally(() => setWdBusy(false))
  }

  const uploadToCloud = (name?: string) => {
    setWdBusy(true)
    api.post('/backup/webdav/upload', { name: name ?? '' })
      .then((r) => { message.success(`已上传 ${r.data.name} 到云端`); loadAll() })
      .catch((e) => message.error(e.response?.data?.detail ?? '上传失败'))
      .finally(() => setWdBusy(false))
  }

  const restoreFromCloud = (name: string) => {
    setWdBusy(true)
    api.post('/backup/webdav/restore', { name, password: cloudRestorePass })
      .then((r) => {
        message.success(r.data.message ?? '恢复成功')
        onClose()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '恢复失败'))
      .finally(() => setWdBusy(false))
  }

  const csvItems = [
    { key: 'todos', label: '待办清单.csv' },
    { key: 'experiments', label: '实验记录.csv' },
    { key: 'achievements', label: '成果.csv' },
    { key: 'references', label: '文献.csv' },
    { key: 'writing', label: '写作打卡.csv' },
  ]

  return (
    <Modal
      title={<span><DatabaseOutlined style={{ marginRight: 8 }} />数据管理</span>}
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
      width={720}
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
              accept=".zip,.enc"
              showUploadList={false}
              beforeUpload={(f) => { restore(f); return false }}
            >
              <Button icon={<CloudUploadOutlined />} loading={restoring}>从备份恢复</Button>
            </Upload>
            <Input.Password placeholder="恢复密码（加密备份必填）" value={restorePass} onChange={(e) => setRestorePass(e.target.value)} style={{ width: 180 }} />
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
                <li key={b.name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span>
                    {b.name}（{fmtSize(b.size)}）
                    {b.encrypted && <Tag color="orange" style={{ marginLeft: 4 }}>已加密</Tag>}
                  </span>
                  {b.sha256 && <span style={{ fontSize: 10 }}>SHA256 {b.sha256.slice(0, 10)}…</span>}
                  {!b.encrypted && (
                    <Popconfirm title="密码加密该备份？" onConfirm={() => encryptBackup(b.name)}
                      description={`加密密码：${encPass || '（未设置）'}`}>
                      <Button size="small" type="link" loading={encrypting === b.name} onClick={() => { if (!encPass) message.warning('请先输入加密密码') }}>
                        加密
                      </Button>
                    </Popconfirm>
                  )}
                </li>
              ))}
            </ul>
          )}
          <Input.Password
            placeholder="备份加密密码（PBKDF2 派生，请牢记）"
            value={encPass}
            onChange={(e) => setEncPass(e.target.value)}
            style={{ width: 260, marginTop: 6 }}
          />
        </div>

        {/* WebDAV 云备份 */}
        <Collapse
          ghost
          items={[{
            key: 'webdav',
            label: <span><CloudServerOutlined style={{ marginRight: 6 }} />云备份（WebDAV：坚果云 / Nextcloud）{wdEnabled && <Tag color="green" style={{ marginLeft: 6 }}>已启用</Tag>}</span>,
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Space wrap>
                  <Input placeholder="WebDAV 地址（如 https://dav.jianguoyun.com/dav/sciplat）" value={wdUrl} onChange={(e) => setWdUrl(e.target.value)} style={{ width: 320 }} />
                  <Input placeholder="账号" value={wdUser} onChange={(e) => setWdUser(e.target.value)} style={{ width: 160 }} />
                  <Input.Password placeholder="应用密码" value={wdPass} onChange={(e) => setWdPass(e.target.value)} style={{ width: 160 }} />
                  <Button onClick={testWebdav} loading={wdBusy}>测试连接</Button>
                  <Button type="primary" onClick={saveWebdav} loading={wdBusy}>保存配置</Button>
                  <Button icon={<ReloadOutlined />} onClick={() => setWdEnabled((v) => !v)}>
                    {wdEnabled ? '停用' : '启用'}
                  </Button>
                </Space>
                <Space wrap>
                  <Button icon={<CloudUploadOutlined />} loading={wdBusy} onClick={() => uploadToCloud()}>
                    上传当前备份到云端
                  </Button>
                  <Button icon={<ReloadOutlined />} loading={wdBusy} onClick={loadAll}>刷新云端列表</Button>
                </Space>
                <Alert type="info" showIcon style={{ fontSize: 12 }}
                  message="启用后，每次启动自动备份时同步上传一份到云端（每日一次节流）。云端文件支持加密包恢复。" />
                {cloudFiles.length === 0 ? (
                  <span style={{ color: '#8a94a3', fontSize: 12 }}>云端暂无备份</span>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: '#94A3B8' }}>
                    {cloudFiles.map((f) => (
                      <li key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span>{f.name}（{fmtSize(f.size)}）</span>
                        <Popconfirm title={`从云端恢复 ${f.name}？`} description="将替换当前全部数据（恢复前自动备份当前库）"
                          onConfirm={() => restoreFromCloud(f.name)}>
                          <Button size="small" type="link">恢复</Button>
                        </Popconfirm>
                      </li>
                    ))}
                  </ul>
                )}
                <Input.Password
                  placeholder="云端加密备份的密码（解密恢复用，非加密包留空）"
                  value={cloudRestorePass}
                  onChange={(e) => setCloudRestorePass(e.target.value)}
                  style={{ width: 300 }}
                />
              </Space>
            ),
          }]}
        />
      </Space>
    </Modal>
  )
}
