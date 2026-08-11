import { useEffect, useState } from 'react'
import {
  Alert, Button, Collapse, Input, Modal, Progress, Space, Spin, Tag, Typography, message,
} from 'antd'
import { DownloadOutlined, ReloadOutlined, RocketOutlined, SettingOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { api } from '../api/client'

interface UpdateInfo {
  has_update: boolean
  current_version: string
  latest_version: string
  download_url: string
  sha256: string
  notes: string
  mandatory: boolean
  published_at: string
  error: string
  source: string
}

const isDesktop = () => !!(window as unknown as { pywebview?: { api?: unknown } }).pywebview?.api

/** 软件更新检查：检测 → 发布说明 → 一键下载安装（桌面端）/ 跳转下载（浏览器） */
export default function UpdateChecker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [info, setInfo] = useState<UpdateInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'downloading' | 'verifying' | 'installing' | 'error'>('idle')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [savingSource, setSavingSource] = useState(false)

  const check = () => {
    setLoading(true)
    api.get<UpdateInfo>('/update/check')
      .then((r) => { setInfo(r.data); setError('') })
      .catch((e) => setError(e.response?.data?.detail ?? '检查失败'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { if (open) { setPhase('idle'); setProgress(0); check() } }, [open])

  useEffect(() => {
    if (!open) return
    api.get<{ source_url: string }>('/settings/update')
      .then((r) => setSourceUrl(r.data.source_url)).catch(() => {})
  }, [open])

  const saveSource = () => {
    setSavingSource(true)
    api.put<{ source_url: string }>('/settings/update', { source_url: sourceUrl })
      .then((r) => { message.success('更新源已保存'); setSourceUrl(r.data.source_url); check() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
      .finally(() => setSavingSource(false))
  }

  const startUpdate = () => {
    if (!info) return
    if (!isDesktop()) {
      // 浏览器模式：跳转下载页手动安装
      if (info.download_url) window.open(info.download_url, '_blank')
      return
    }
    const py = (window as unknown as { pywebview: { api: { download: Function; install: Function } } }).pywebview.api
    setPhase('downloading'); setProgress(0); setError('')
    ;(window as unknown as { __updateProgress?: (p: number) => void }).__updateProgress = (pct: number) => {
      setProgress(Math.round(pct))
      if (pct >= 100) setPhase('verifying')
    }
    py.download(info.download_url, info.sha256)
      .then((res: { ok: boolean; path?: string; error?: string }) => {
        if (!res.ok) {
          setPhase('error')
          setError(res.error ?? '下载失败')
          return
        }
        setPhase('installing')
        // 主进程将启动静默安装器并退出当前应用，随后自动拉起新版
        py.install(res.path)
        setPhase('installing')
      })
      .catch((e: unknown) => { setPhase('error'); setError(String(e)) })
  }

  const mandatory = info?.mandatory ?? false
  const busy = phase === 'downloading' || phase === 'verifying' || phase === 'installing'

  return (
    <Modal
      title={<span><RocketOutlined style={{ marginRight: 8 }} />软件更新</span>}
      open={open}
      onCancel={onClose}
      closable={!mandatory && !busy}
      maskClosable={!mandatory}
      footer={
        busy ? null : info?.has_update ? [
          <Button key="later" disabled={mandatory} onClick={onClose}>稍后</Button>,
          <Button key="now" type="primary" icon={<DownloadOutlined />} onClick={startUpdate}>
            {isDesktop() ? '立即更新' : '前往下载'}
          </Button>,
        ] : [
          <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
        ]
      }
      width={620}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : busy ? (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Typography.Text>
            {phase === 'downloading' && '正在下载新版本…'}
            {phase === 'verifying' && '下载完成，正在校验文件完整性（SHA256）…'}
            {phase === 'installing' && '正在静默安装，完成后将自动重启新版…'}
          </Typography.Text>
          <Progress percent={progress} status="active" />
        </Space>
      ) : error && !info ? (
        <>
          <Alert type="warning" showIcon message="无法检查更新" description={error} />
          <Collapse
            ghost
            style={{ marginTop: 12 }}
            items={[{
              key: 'src',
              label: <span><SettingOutlined style={{ marginRight: 6 }} />更新源设置</span>,
              children: (
                <Space.Compact style={{ width: '100%' }}>
                  <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="latest.json 地址" />
                  <Button type="primary" loading={savingSource} onClick={saveSource}>保存并重试</Button>
                </Space.Compact>
              ),
            }]}
          />
        </>
      ) : info && info.has_update ? (
        <>
          <Space wrap style={{ marginBottom: 8 }}>
            <Tag color="green">v{info.current_version} → v{info.latest_version}</Tag>
            {info.mandatory && <Tag color="red">强制更新</Tag>}
            {info.published_at && <Tag>{info.published_at}</Tag>}
          </Space>
          {info.notes ? (
            <div className="markdown-body" style={{ maxHeight: '45vh', overflow: 'auto', padding: 8 }}>
              <ReactMarkdown>{info.notes}</ReactMarkdown>
            </div>
          ) : (
            <Typography.Text type="secondary">（无发布说明）</Typography.Text>
          )}
          <Collapse
            ghost
            style={{ marginTop: 12 }}
            items={[{
              key: 'src',
              label: <span><SettingOutlined style={{ marginRight: 6 }} />更新源设置</span>,
              children: (
                <Space.Compact style={{ width: '100%' }}>
                  <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="latest.json 地址" />
                  <Button type="primary" loading={savingSource} onClick={saveSource}>保存</Button>
                </Space.Compact>
              ),
            }]}
          />
        </>
      ) : info ? (
        <Alert type="success" showIcon message={`当前已是最新版本 v${info.current_version}`} />
      ) : null}
    </Modal>
  )
}
