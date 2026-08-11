import { useEffect, useState } from 'react'
import {
  Button, Checkbox, Collapse, Input, List, message, Modal, Popconfirm, Progress, Select, Space, Tag, Typography,
} from 'antd'
import { CommentOutlined, DeleteOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime } from '../utils'
import type { Experiment, ExperimentComment, ExperimentStep, ExperimentTemplate } from '../types'

const STEP_COLORS: Record<string, string> = { 未开始: 'default', 进行中: 'blue', 已完成: 'green' }

/** 实验记录增强：步骤 checklist + 完成度 + 评论区 + 模板套用 */
export default function ExperimentExtras({ experiment, onTemplateApplied }: {
  experiment: Experiment
  onTemplateApplied?: () => void
}) {
  const [steps, setSteps] = useState<ExperimentStep[]>([])
  const [comments, setComments] = useState<ExperimentComment[]>([])
  const [templates, setTemplates] = useState<ExperimentTemplate[]>([])
  const [stepInput, setStepInput] = useState('')
  const [commentInput, setCommentInput] = useState('')
  const [templateOpen, setTemplateOpen] = useState(false)
  const [templateSel, setTemplateSel] = useState<number | undefined>()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const load = () => {
    api.get<ExperimentStep[]>(`/experiments/${experiment.id}/steps`).then((r) => setSteps(r.data)).catch(() => {})
    api.get<ExperimentComment[]>(`/experiments/${experiment.id}/comments`).then((r) => setComments(r.data)).catch(() => {})
    api.get<ExperimentTemplate[]>('/experiment-templates').then((r) => setTemplates(r.data)).catch(() => {})
  }
  useEffect(load, [experiment.id, refreshKey])

  const addStep = () => {
    if (!stepInput.trim()) return
    api.post(`/experiments/${experiment.id}/steps`, { title: stepInput.trim(), order_no: steps.length })
      .then(() => { setStepInput(''); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const toggleStep = (s: ExperimentStep, done: boolean) => {
    api.put(`/experiments/steps/${s.id}`, { status: done ? '已完成' : '未开始' }).then(() => bump())
  }

  const addComment = () => {
    if (!commentInput.trim()) return
    api.post(`/experiments/${experiment.id}/comments`, { content: commentInput.trim() })
      .then(() => { setCommentInput(''); bump() })
      .catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
  }

  const applyTemplate = () => {
    if (!templateSel) return
    api.post(`/experiment-templates/${templateSel}/apply`, { phase_id: experiment.phase_id })
      .then(() => {
        message.success('已按模板创建新实验')
        setTemplateOpen(false)
        bump()
        onTemplateApplied?.()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '套用失败'))
  }

  const done = steps.filter((s) => s.status === '已完成').length
  const percent = steps.length ? Math.round((done / steps.length) * 100) : 0

  return (
    <div>
      {/* 步骤进度 */}
      {steps.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '8px 0' }}>
          <Progress percent={percent} size="small" style={{ flex: 1, maxWidth: 200, margin: 0 }} strokeColor="#34D399" />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{done}/{steps.length} 步骤</Typography.Text>
        </div>
      )}

      {/* 步骤列表 */}
      <Space wrap style={{ marginBottom: 6 }}>
        <Typography.Text strong style={{ fontSize: 13 }}>步骤（{steps.length}）</Typography.Text>
        <Input
          size="small" placeholder="添加步骤…" value={stepInput}
          onChange={(e) => setStepInput(e.target.value)} onPressEnter={addStep}
          style={{ width: 200 }}
        />
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={addStep}>添加</Button>
        <Button size="small" onClick={() => setTemplateOpen(true)}>从模板创建</Button>
      </Space>
      {steps.length === 0 && <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无步骤（eLabFTW 式工作流）</Typography.Text>}
      <List
        size="small"
        dataSource={steps}
        renderItem={(s) => (
          <List.Item
            style={{ paddingInline: 4 }}
            actions={[
              <Checkbox key="c" checked={s.status === '已完成'} onChange={(e) => toggleStep(s, e.target.checked)} />,
              s.duration_min ? <Tag key="t" style={{ fontSize: 11 }}>{s.duration_min}min</Tag> : null,
              <Popconfirm key="d" title="删除该步骤？" onConfirm={() => api.delete(`/experiments/steps/${s.id}`).then(() => bump())}>
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>,
            ]}
          >
            <span style={{ textDecoration: s.status === '已完成' ? 'line-through' : 'none', color: s.status === '已完成' ? '#64748B' : undefined }}>
              <Tag color={STEP_COLORS[s.status]}>{s.status}</Tag>
              {s.title}
            </span>
          </List.Item>
        )}
      />

      {/* 评论 */}
      <Collapse
        size="small"
        ghost
        style={{ marginTop: 8 }}
        items={[{
          key: 'comments',
          label: <span style={{ fontSize: 13 }}><CommentOutlined style={{ marginRight: 6 }} />评论（{comments.length}）</span>,
          children: (
            <div>
              <Space style={{ marginBottom: 8 }}>
                <Input
                  size="small" placeholder="写评论/讨论…" value={commentInput}
                  onChange={(e) => setCommentInput(e.target.value)} onPressEnter={addComment}
                  style={{ width: 260 }}
                />
                <Button size="small" icon={<SendOutlined />} onClick={addComment}>评论</Button>
              </Space>
              <List
                size="small"
                dataSource={comments}
                renderItem={(c) => (
                  <List.Item
                    style={{ paddingInline: 4 }}
                    actions={[
                      <Popconfirm key="d" title="删除评论？" onConfirm={() => api.delete(`/experiments/comments/${c.id}`).then(() => bump())}>
                        <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                      </Popconfirm>,
                    ]}
                  >
                    <Space direction="vertical" size={0}>
                      <span style={{ fontSize: 13 }}>{c.content}</span>
                      <Typography.Text type="secondary" style={{ fontSize: 11, fontFamily: 'var(--mono)' }}>
                        {fmtDateTime(c.created_at)}
                      </Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            </div>
          ),
        }]}
      />

      {/* 模板弹窗 */}
      <Modal title="从实验模板创建" open={templateOpen} onCancel={() => setTemplateOpen(false)}
        onOk={applyTemplate} okText="创建" width={480} destroyOnClose>
        {templates.length === 0 ? (
          <Typography.Text type="secondary">暂无实验模板。可在实验记录旁通过「从模板创建」前的模板库管理添加。</Typography.Text>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Select
              style={{ width: '100%' }} placeholder="选择模板"
              value={templateSel} onChange={setTemplateSel}
              options={templates.map((t) => ({ value: t.id, label: `${t.category} · ${t.title}` }))}
            />
            {templateSel && (() => {
              const t = templates.find((x) => x.id === templateSel)!
              return (
                <div style={{ fontSize: 12, color: '#94A3B8' }}>
                  <div>目的：{t.body.purpose || '—'}</div>
                  <div>方法：{t.body.method || '—'}</div>
                  <div>步骤：{(t.body.steps ?? []).map((s) => s.title).join(' → ') || '—'}</div>
                </div>
              )
            })()}
          </Space>
        )}
      </Modal>
    </div>
  )
}
