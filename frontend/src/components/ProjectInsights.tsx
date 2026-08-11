import { useEffect, useState } from 'react'
import {
  Button, Card, Descriptions, Form, Input, List, message, Modal, Popconfirm, Select, Space, Tag, Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, TrophyOutlined, WarningOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime } from '../utils'
import type { ProjectReview, ProjectRisk } from '../types'

const SEVERITY_COLORS: Record<string, string> = { 高: 'red', 中: 'orange', 低: 'default' }
const RISK_STATUS_COLORS: Record<string, string> = { 未解决: 'red', 处理中: 'gold', 已解决: 'green' }

/** 项目结项复盘 + 风险与阻塞跟踪 */
export default function ProjectInsights({ projectId }: { projectId: number }) {
  const [review, setReview] = useState<ProjectReview | null>(null)
  const [risks, setRisks] = useState<ProjectRisk[]>([])
  const [reviewOpen, setReviewOpen] = useState(false)
  const [riskOpen, setRiskOpen] = useState(false)
  const [editingRisk, setEditingRisk] = useState<ProjectRisk | null>(null)
  const [reviewForm] = Form.useForm()
  const [riskForm] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    api.get<ProjectReview>(`/projects/${projectId}/review`).then((r) => setReview(r.data)).catch(() => {})
    api.get<ProjectRisk[]>(`/projects/${projectId}/risks`).then((r) => setRisks(r.data)).catch(() => {})
  }
  useEffect(load, [projectId, refreshKey])

  const openRisk = (r?: ProjectRisk) => {
    setEditingRisk(r ?? null)
    riskForm.setFieldsValue(r
      ? { title: r.title, severity: r.severity, status: r.status, resolution: r.resolution }
      : { severity: '中', status: '未解决' })
    setRiskOpen(true)
  }

  const saveRisk = () => {
    riskForm.validateFields().then((v) => {
      const req = editingRisk ? api.put(`/projects/risks/${editingRisk.id}`, v) : api.post(`/projects/${projectId}/risks`, v)
      req.then(() => { message.success('已保存'); setRiskOpen(false); bump() })
        .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const hasReview = review && [review.goal_achievement, review.difficulties, review.lessons, review.reusable_methods].some(Boolean)

  return (
    <Card size="small" title="结项复盘与风险跟踪">
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* 复盘 */}
        <div>
          <Space style={{ marginBottom: 8 }}>
            <Typography.Text strong style={{ fontSize: 13 }}>
              <TrophyOutlined style={{ color: '#34D399', marginRight: 6 }} />结项复盘
            </Typography.Text>
            <Button size="small" type="link" onClick={() => {
              reviewForm.setFieldsValue(review ?? {})
              setReviewOpen(true)
            }}>
              {hasReview ? '编辑' : '填写'}
            </Button>
          </Space>
          {hasReview ? (
            <Descriptions column={1} size="small">
              {review!.goal_achievement && <Descriptions.Item label="目标达成">{review!.goal_achievement}</Descriptions.Item>}
              {review!.difficulties && <Descriptions.Item label="困难与对策">{review!.difficulties}</Descriptions.Item>}
              {review!.lessons && <Descriptions.Item label="经验教训">{review!.lessons}</Descriptions.Item>}
              {review!.reusable_methods && <Descriptions.Item label="可复用方法">{review!.reusable_methods}</Descriptions.Item>}
            </Descriptions>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              项目完成后填写复盘：目标达成情况、困难与对策、经验教训、可复用方法，沉淀科研方法论。
            </Typography.Text>
          )}
        </div>

        {/* 风险 */}
        <div>
          <Space style={{ marginBottom: 8 }}>
            <Typography.Text strong style={{ fontSize: 13 }}>
              <WarningOutlined style={{ color: '#F87171', marginRight: 6 }} />风险与阻塞（{risks.length}）
            </Typography.Text>
            <Button size="small" type="link" icon={<PlusOutlined />} onClick={() => openRisk()}>添加</Button>
          </Space>
          {risks.length === 0 ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无风险记录</Typography.Text>
          ) : (
            <List
              size="small"
              dataSource={risks}
              renderItem={(r) => (
                <List.Item
                  style={{ paddingInline: 4 }}
                  actions={[
                    <Button key="e" size="small" type="text" icon={<EditOutlined />} onClick={() => openRisk(r)} />,
                    <Popconfirm key="d" title="删除该风险？" onConfirm={() => api.delete(`/projects/risks/${r.id}`).then(() => bump())}>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>,
                  ]}
                >
                  <Space direction="vertical" size={2}>
                    <Space>
                      <Tag color={SEVERITY_COLORS[r.severity]}>{r.severity}</Tag>
                      <Tag color={RISK_STATUS_COLORS[r.status]}>{r.status}</Tag>
                      <Typography.Text strong>{r.title}</Typography.Text>
                    </Space>
                    {r.resolution && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>解决：{r.resolution}</Typography.Text>
                    )}
                  </Space>
                </List.Item>
              )}
            />
          )}
        </div>
      </Space>

      {/* 复盘弹窗 */}
      <Modal title="结项复盘" open={reviewOpen} onOk={() => {
        reviewForm.validateFields().then((v) => {
          api.put(`/projects/${projectId}/review`, v).then(() => {
            message.success('已保存')
            setReviewOpen(false)
            bump()
          }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
        })
      }} onCancel={() => setReviewOpen(false)} width={560} destroyOnClose>
        <Form form={reviewForm} layout="vertical">
          <Form.Item name="goal_achievement" label="目标达成情况"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="difficulties" label="困难与对策"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="lessons" label="经验教训"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="reusable_methods" label="可复用方法"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {/* 风险弹窗 */}
      <Modal title={editingRisk ? '编辑风险' : '添加风险'} open={riskOpen} onOk={saveRisk} onCancel={() => setRiskOpen(false)} destroyOnClose>
        <Form form={riskForm} layout="vertical">
          <Form.Item name="title" label="问题描述" rules={[{ required: true, message: '请输入问题' }]}>
            <Input placeholder="如：GPU 资源不足 / 数据标注进度滞后" />
          </Form.Item>
          <Form.Item label="严重度 / 状态">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="severity" noStyle>
                <Select style={{ width: '50%' }} options={['高', '中', '低'].map((x) => ({ value: x, label: x }))} />
              </Form.Item>
              <Form.Item name="status" noStyle>
                <Select style={{ width: '50%' }} options={['未解决', '处理中', '已解决'].map((x) => ({ value: x, label: x }))} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="resolution" label="解决记录"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
