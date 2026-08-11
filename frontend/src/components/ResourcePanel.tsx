import { useEffect, useState } from 'react'
import {
  Button, Card, DatePicker, Form, Input, InputNumber, message, Modal, Popconfirm, Select, Space, Table, Tag,
} from 'antd'
import { DeleteOutlined, EditOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDate } from '../utils'
import type { LabResource } from '../types'

const STATUS_COLORS: Record<string, string> = { 正常: 'green', 低库存: 'gold', 已耗尽: 'red', 过期: 'red' }
const TYPE_OPTIONS = ['试剂', '设备', '耗材', '其他']

/** 实验室资源库存（eLabFTW 资源库）：数量/位置/有效期/低库存提醒 */
export default function ResourcePanel() {
  const [list, setList] = useState<LabResource[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<LabResource | null>(null)
  const [form] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    setLoading(true)
    api.get<LabResource[]>('/resources').then((r) => setList(r.data)).catch(() => {})
      .finally(() => setLoading(false))
  }
  useEffect(load, [refreshKey])

  const openModal = (r?: LabResource) => {
    setEditing(r ?? null)
    form.setFieldsValue(r
      ? {
          name: r.name, rtype: r.rtype, quantity: r.quantity, unit: r.unit,
          low_threshold: r.low_threshold, location: r.location,
          expiry_date: r.expiry_date ? dayjs(r.expiry_date) : null, notes: r.notes,
        }
      : { rtype: '试剂', quantity: 0, unit: '个' })
    setModalOpen(true)
  }

  const save = () => {
    form.validateFields().then((v) => {
      const body = { ...v, expiry_date: v.expiry_date?.format('YYYY-MM-DD') ?? null }
      const req = editing ? api.put(`/resources/${editing.id}`, body) : api.post('/resources', body)
      req.then(() => {
        message.success('已保存')
        setModalOpen(false)
        bump()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const adjust = (r: LabResource, delta: number) => {
    api.post(`/resources/${r.id}/adjust`, { delta })
      .then(() => bump())
      .catch((e) => message.error(e.response?.data?.detail ?? '操作失败'))
  }

  return (
    <Card size="small" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>新增资源</Button>}>
      <Table<LabResource>
        rowKey="id"
        loading={loading}
        dataSource={list}
        size="small"
        pagination={{ pageSize: 15 }}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '类型', dataIndex: 'rtype', width: 90, render: (v: string) => <Tag>{v}</Tag> },
          {
            title: '数量',
            dataIndex: 'quantity',
            width: 150,
            render: (v: number, r) => (
              <Space>
                <Button size="small" icon={<MinusOutlined />} onClick={() => adjust(r, -1)} title="消耗 1" />
                <span style={{ fontFamily: 'var(--mono)', fontWeight: 700 }}>{v} {r.unit}</span>
                <Button size="small" icon={<PlusOutlined />} onClick={() => adjust(r, 1)} title="补充 1" />
              </Space>
            ),
          },
          { title: '位置', dataIndex: 'location', width: 110, ellipsis: true, render: (v) => v || '—' },
          { title: '有效期', dataIndex: 'expiry_date', width: 110, render: (v: string | null) => fmtDate(v) },
          { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v}</Tag> },
          { title: '备注', dataIndex: 'notes', ellipsis: true, render: (v) => v || '—' },
          {
            title: '操作',
            width: 90,
            render: (_, r) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => openModal(r)} />
                <Popconfirm title="删除该资源？" onConfirm={() => api.delete(`/resources/${r.id}`).then(() => bump())}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal title={editing ? '编辑资源' : '新增资源'} open={modalOpen} onOk={save} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}><Input /></Form.Item>
          <Form.Item label="类型 / 单位">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="rtype" noStyle>
                <Select style={{ width: '50%' }} options={TYPE_OPTIONS.map((t) => ({ value: t, label: t }))} />
              </Form.Item>
              <Form.Item name="unit" noStyle><Input placeholder="单位（瓶/盒/个）" style={{ width: '50%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item label="数量 / 低库存阈值">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="quantity" noStyle><InputNumber min={0} style={{ width: '50%' }} /></Form.Item>
              <Form.Item name="low_threshold" noStyle><InputNumber placeholder="低库存阈值" style={{ width: '50%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item label="存放位置 / 有效期">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="location" noStyle><Input placeholder="如 -20℃ 冰箱 B 层" style={{ width: '55%' }} /></Form.Item>
              <Form.Item name="expiry_date" noStyle><DatePicker style={{ width: '45%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
