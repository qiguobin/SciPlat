import { useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Select, Tabs, message } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'

/** 全局快捷键 / 快速录入：待办 / 灵感 */
export default function QuickAdd() {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('todo')
  const [projects, setProjects] = useState<{ id: number; title: string }[]>([])
  const [form] = Form.useForm()
  const bump = useAppStore((s) => s.bump)

  useEffect(() => {
    api.get<{ id: number; title: string }[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
  }, [open])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName ?? '').toLowerCase()
      if (e.key === '/' && tag !== 'input' && tag !== 'textarea' && !(document.activeElement as HTMLElement)?.isContentEditable) {
        e.preventDefault()
        setOpen((v) => !v)
        form.setFieldsValue({ date: new Date().toISOString().slice(0, 10), priority: '中', repeat: 'none' })
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [form])

  const save = () => {
    form.validateFields().then((v) => {
      if (tab === 'todo') {
        api.post('/todos', v).then(() => {
          message.success('待办已添加')
          setOpen(false)
          bump()
        }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
      } else {
        api.post('/ideas', { content: v.content, tags: (v.tags ?? []).join(',') }).then(() => {
          message.success('灵感已收录')
          setOpen(false)
          bump()
        }).catch(() => message.error('保存失败'))
      }
    })
  }

  return (
    <Modal
      title={<span><ThunderboltOutlined style={{ color: '#c8873a', marginRight: 8 }} />快速录入（按 / 随时唤起）</span>}
      open={open}
      onOk={save}
      onCancel={() => setOpen(false)}
      okText="保存"
      destroyOnClose
    >
      <Tabs activeKey={tab} onChange={setTab} items={[
        {
          key: 'todo',
          label: '待办',
          children: (
            <Form form={form} layout="vertical">
              <Form.Item name="title" label="内容" rules={[{ required: true, message: '请输入待办内容' }]}>
                <Input placeholder="如：跑完消融实验" autoFocus />
              </Form.Item>
              <Form.Item label="日期 / 优先级 / 重复">
                <div style={{ display: 'flex', gap: 8 }}>
                  <Form.Item name="date" noStyle rules={[{ required: true }]}>
                    <Input type="date" style={{ flex: 1 }} />
                  </Form.Item>
                  <Form.Item name="priority" noStyle>
                    <Select style={{ width: 90 }} options={['高', '中', '低'].map((p) => ({ value: p, label: p }))} />
                  </Form.Item>
                  <Form.Item name="repeat" noStyle>
                    <Select style={{ width: 110 }} options={[
                      { value: 'none', label: '不重复' },
                      { value: 'daily', label: '每天 ♻' },
                      { value: 'weekly', label: '每周 ♻' },
                    ]} />
                  </Form.Item>
                </div>
              </Form.Item>
              <Form.Item name="project_id" label="关联项目">
                <Select allowClear options={projects.map((p) => ({ value: p.id, label: p.title }))} />
              </Form.Item>
            </Form>
          ),
        },
        {
          key: 'idea',
          label: '灵感',
          children: (
            <Form form={form} layout="vertical">
              <Form.Item name="content" label="想法" rules={[{ required: true, message: '请输入想法' }]}>
                <Input.TextArea rows={3} placeholder="快速记下一个想法…" />
              </Form.Item>
              <Form.Item name="tags" label="标签">
                <Select mode="tags" open={false} suffixIcon={null} placeholder="输入后回车" />
              </Form.Item>
            </Form>
          ),
        },
      ]} />
    </Modal>
  )
}
