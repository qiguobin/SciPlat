import { useEffect, useState } from 'react'
import {
  Button, Empty, List, Modal, Popover, Space, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  AlertOutlined, CheckCircleOutlined, CloseCircleOutlined, DatabaseOutlined, DeleteOutlined, ReloadOutlined, RobotOutlined,
} from '@ant-design/icons'
import { api } from '../api/client'

interface Health {
  status: string
  version: string
  app_name: string
  data_dir: string
  db_path: string
  db_size: number
  llm_configured: boolean
  llm_provider: string
  llm_model: string
  llm_context_window: number
  llm_balance: { is_available: boolean; total_balance: number; currency: string; note?: string; manual?: boolean } | null
  llm_status: { online: boolean; availability_pct: number | null; latency_ms: number | null; checked_at: string } | null
  llm_usage_today: { total_tokens: number; cost: number; calls: number }
  ai_tasks_running: number
  python: string
  error_count: number
  uptime_seconds: number
}

interface SysEvent {
  id: number
  level: string
  source: string
  message: string
  created_at: string
}

const fmtSize = (n: number) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1024).toFixed(0)} KB`)

const fmtTokens = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n))

const fmtCost = (n: number) => (n >= 100 ? n.toFixed(0) : n >= 1 ? n.toFixed(2) : n.toFixed(4))

const fmtUptime = (s: number) => {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}h${m}m` : `${m}m`
}

/** 底部状态栏：服务/数据库/版本/LLM（上下文·余额·用量·子任务）/错误计数 */
export default function StatusBar({ onOpenData, onOpenLlm, onOpenUpdate, onOpenUsage }: {
  onOpenData?: () => void
  onOpenLlm?: () => void
  onOpenUpdate?: () => void
  onOpenUsage?: () => void
}) {
  const [health, setHealth] = useState<Health | null>(null)
  const [online, setOnline] = useState(true)
  const [hasUpdate, setHasUpdate] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [events, setEvents] = useState<SysEvent[]>([])
  const [eventsLoading, setEventsLoading] = useState(false)

  const load = () => {
    api.get<Health>('/health')
      .then((r) => { setHealth(r.data); setOnline(true) })
      .catch(() => setOnline(false))
  }
  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  // 更新可用性：启动时 + 每 6 小时静默检测一次（🆕 徽标）
  useEffect(() => {
    const checkUpdate = () => {
      api.get<{ has_update: boolean }>('/update/check')
        .then((r) => setHasUpdate(Boolean(r.data.has_update)))
        .catch(() => { /* 网络不可达时静默 */ })
    }
    checkUpdate()
    const t = setInterval(checkUpdate, 6 * 3600 * 1000)
    return () => clearInterval(t)
  }, [])

  const openLog = () => {
    setEventsLoading(true)
    api.get<SysEvent[]>('/system-events')
      .then((r) => { setEvents(r.data); setLogOpen(true) })
      .catch(() => message.error('错误日志加载失败'))
      .finally(() => setEventsLoading(false))
  }

  const clearLog = () => {
    api.post('/system-events/clear')
      .then(() => { setEvents([]); message.success('错误日志已清空') })
      .catch(() => message.error('清空失败'))
  }

  const dbName = health?.db_path.split(/[\\/]/).pop() ?? 'sci.db'
  const errorCount = health?.error_count ?? 0

  return (
    <>
      <div className="app-statusbar">
        <Space size={14} wrap>
          <Tooltip title={online ? '服务运行正常' : '无法连接后端服务'}>
            <span className="statusbar-item">
              {online
                ? <CheckCircleOutlined style={{ color: '#34D399' }} />
                : <CloseCircleOutlined style={{ color: '#FF005C' }} />}
              <span style={{ color: online ? '#4ade80' : '#FF005C' }}>{online ? '服务正常' : '服务异常'}</span>
            </span>
          </Tooltip>

          <Tooltip title={`数据库文件：${health?.db_path ?? '—'}\n数据目录：${health?.data_dir ?? '—'}`}>
            <span className="statusbar-item statusbar-click" onClick={onOpenData}>
              <DatabaseOutlined />
              🗄 {dbName}
              {health && health.db_size > 0 && <span className="statusbar-dim">（{fmtSize(health.db_size)}）</span>}
            </span>
          </Tooltip>

          <span className="statusbar-item">
            📦 v{health?.version ?? '—'}
            <span className="statusbar-dim"> · Python {health?.python ?? '—'}</span>
          </span>

          <Tooltip title="检查更新">
            <span className="statusbar-item statusbar-click" onClick={onOpenUpdate}>
              <ReloadOutlined />
              {hasUpdate ? <span className="statusbar-error">🆕 有新版本</span> : '检查更新'}
            </span>
          </Tooltip>

          <Tooltip title={health?.llm_configured
            ? `LLM 用量/余额/上下文（点击查看详情；配置见顶栏 ⚙️）${health.llm_status?.checked_at
              ? `\nAPI ${health.llm_status.online ? '在线' : '离线'} · 可用性 ${health.llm_status.availability_pct ?? '-'}% · ${health.llm_status.latency_ms ?? '-'}ms · ${health.llm_status.checked_at}`
              : '\n尚未探测 API 状态（可在 AI 设置中立即探测）'}`
            : '未配置 LLM，点击打开 AI 设置'}>
            <span className="statusbar-item statusbar-click" onClick={health?.llm_configured ? onOpenUsage : onOpenLlm}>
              <RobotOutlined />
              {health?.llm_configured ? (
                <>
                  <span className="statusbar-llm">
                    {health.llm_status?.online
                      ? '🟢 '
                      : health.llm_status?.checked_at ? '🔴 ' : '⚪ '}
                    🤖 {health.llm_model || health.llm_provider}
                    {health.llm_status?.checked_at && health.llm_status.availability_pct != null && (
                      <span className="statusbar-dim"> 可用性 {health.llm_status.availability_pct}%</span>
                    )}
                    {health.llm_context_window > 0 && <span className="statusbar-dim">（{Math.round(health.llm_context_window / 1024)}K）</span>}
                  </span>
                  <span className="statusbar-dim">
                    {health.llm_balance?.is_available
                      ? `💰 ${health.llm_balance.currency === 'USD' ? '$' : '¥'}${health.llm_balance.total_balance}${health.llm_balance.manual ? '(手动)' : ''}`
                      : '💰 不可查'}
                  </span>
                  {health.llm_usage_today && health.llm_usage_today.calls > 0 && (
                    <span className="statusbar-dim">
                      ⚡ 今日 {fmtTokens(health.llm_usage_today.total_tokens)} tok · {fmtCost(health.llm_usage_today.cost)}
                    </span>
                  )}
                  <span className={health.ai_tasks_running > 0 ? 'statusbar-error' : 'statusbar-dim'}>
                    {health.ai_tasks_running > 0 ? `🟡 AI 子任务 ${health.ai_tasks_running}` : '🟢 无子任务'}
                  </span>
                </>
              ) : (
                <span className="statusbar-dim">LLM 未配置</span>
              )}
            </span>
          </Tooltip>

          <span className={`statusbar-item statusbar-click ${errorCount > 0 ? 'statusbar-error' : ''}`} onClick={openLog}>
            <AlertOutlined />
            {errorCount > 0 ? `⚠ 错误 ${errorCount} 条（7 天内）` : '无错误记录'}
          </span>

          {health && health.uptime_seconds > 0 && (
            <span className="statusbar-dim">运行 {fmtUptime(health.uptime_seconds)}</span>
          )}
        </Space>
      </div>

      {/* 错误日志弹窗 */}
      <Modal
        title="系统错误日志"
        open={logOpen}
        onCancel={() => setLogOpen(false)}
        footer={[
          <Button key="clear" danger icon={<DeleteOutlined />} disabled={events.length === 0} onClick={clearLog}>
            清空日志
          </Button>,
          <Button key="close" type="primary" onClick={() => setLogOpen(false)}>关闭</Button>,
        ]}
        width={680}
      >
        {events.length === 0 ? (
          <Empty description={eventsLoading ? '加载中…' : '暂无错误记录'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            size="small"
            dataSource={events}
            renderItem={(e) => (
              <List.Item>
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Space size={6}>
                    <Tag color={e.level === 'error' ? 'red' : 'blue'} style={{ fontSize: 10 }}>{e.level}</Tag>
                    <Typography.Text style={{ fontSize: 12, fontFamily: 'var(--mono)' }}>{e.source}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      {e.created_at.slice(0, 19).replace('T', ' ')}
                    </Typography.Text>
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>{e.message}</Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Modal>
    </>
  )
}
