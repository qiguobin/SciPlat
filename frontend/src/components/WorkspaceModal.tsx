import { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, List, message, Modal, Popconfirm, Space, Tag, Typography } from 'antd'
import { FolderOpenOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { api } from '../api/client'

interface WorkspaceInfo {
  name: string
  path: string
  created_at?: string
  last_opened?: string
  current?: boolean
}

/** 工作区弹窗：查看/新建/切换/注销。切换后页面 reload 刷新全部数据。 */
export default function WorkspaceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [list, setList] = useState<WorkspaceInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [switching, setSwitching] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()

  const load = () => {
    setLoading(true)
    api
      .get<{ current: string; workspaces: WorkspaceInfo[] }>('/workspace')
      .then((r) => {
        setCurrent(r.data.current)
        setList(r.data.workspaces)
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '工作区加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(() => {
    if (open) load()
  }, [open])

  /** 桌面版：pywebview 原生目录选择（浏览器模式不可用，提示手动输入） */
  const pickDir = async () => {
    const py = (window as unknown as { pywebview?: { api?: { workspace?: { pick_directory?: () => Promise<string[]> } } } }).pywebview
    try {
      const ws = py?.api?.workspace
      const res = await ws?.pick_directory?.()
      if (res?.[0]) form.setFieldValue('path', res[0])
      else message.info('未选择目录')
    } catch {
      message.warning('目录选择不可用，请手动输入绝对路径')
    }
  }

  const create = () => {
    form.validateFields().then((v) => {
      setCreating(true)
      api
        .post('/workspace', v)
        .then(() => {
          message.success(`已创建并切换到工作区「${v.name}」，页面即将刷新`)
          setTimeout(() => window.location.reload(), 800)
        })
        .catch((e) => message.error(e.response?.data?.detail ?? '创建失败'))
        .finally(() => setCreating(false))
    })
  }

  const doSwitch = (ws: WorkspaceInfo) => {
    setSwitching(ws.path)
    api
      .post('/workspace/switch', { path: ws.path })
      .then(() => {
        message.success('已切换工作区，页面即将刷新')
        setTimeout(() => window.location.reload(), 800)
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '切换失败'))
      .finally(() => setSwitching(null))
  }

  const remove = (ws: WorkspaceInfo) => {
    api
      .delete('/workspace', { data: { path: ws.path } })
      .then(() => {
        message.success(`已注销「${ws.name}」（数据文件保留在磁盘）`)
        load()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '注销失败'))
  }

  return (
    <Modal title="工作区（独立数据目录）" open={open} onCancel={onClose} footer={null} width={680}>
      <Alert
        type="info"
        showIcon
        message="每个工作区拥有独立的数据目录：文献库、PDF 附件、笔记、设置完全隔离，适合按科研项目分开管理。"
        style={{ marginBottom: 12 }}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        当前工作区：<Typography.Text code>{current || '—'}</Typography.Text>
      </Typography.Text>

      <List
        style={{ marginTop: 12 }}
        loading={loading}
        dataSource={list}
        locale={{ emptyText: '暂无工作区' }}
        renderItem={(ws) => (
          <List.Item
            actions={[
              ws.current ? (
                <Tag color="green">当前</Tag>
              ) : (
                <>
                  <Popconfirm title={`切换到工作区「${ws.name}」？`} description="页面将刷新以加载该工作区的数据。" onConfirm={() => doSwitch(ws)}>
                    <Button size="small" type="primary" loading={switching === ws.path}>
                      切换
                    </Button>
                  </Popconfirm>
                  <Popconfirm title={`注销「${ws.name}」？`} description="仅从列表移除，不会删除任何数据文件。" onConfirm={() => remove(ws)}>
                    <Button size="small" danger>
                      注销
                    </Button>
                  </Popconfirm>
                </>
              ),
            ]}
          >
            <Space direction="vertical" size={0} style={{ width: '100%' }}>
              <Typography.Text strong>{ws.name}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }} code>
                {ws.path}
              </Typography.Text>
            </Space>
          </List.Item>
        )}
      />

      <Form form={form} layout="inline" style={{ marginTop: 16 }} onFinish={create}>
        <Form.Item name="name" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="工作区名称（如：博士课题）" style={{ width: 180 }} />
        </Form.Item>
        <Form.Item name="path" rules={[{ required: true, message: '请输入绝对路径' }]} style={{ flex: 1 }}>
          <Input placeholder="数据目录绝对路径，如 D:\sciplat\thesis" />
        </Form.Item>
        <Button icon={<FolderOpenOutlined />} onClick={pickDir} title="桌面版可用系统目录选择器">
          选择文件夹
        </Button>
        <Button type="primary" icon={<PlusOutlined />} htmlType="submit" loading={creating}>
          创建并切换
        </Button>
      </Form>
      <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
        创建即进入该工作区；所有文献与附件将存储在该目录下（<ReloadOutlined /> 图标表示切换后自动刷新）。
      </Typography.Text>
    </Modal>
  )
}
