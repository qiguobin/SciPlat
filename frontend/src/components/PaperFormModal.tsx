import { useEffect, useState } from 'react'
import { Button, DatePicker, Form, Input, Modal, Select, Space, message } from 'antd'
import dayjs from 'dayjs'
import { api } from '../api/client'
import type { Journal, Paper, Project } from '../types'

const TYPE_OPTIONS = ['期刊', '会议', '学位论文', '预印本']
const STATUS_OPTIONS = ['Draft', 'Submitted', 'Under Review', 'Revision', 'Resubmitted', 'Accepted', 'Published', 'Rejected']

/** 论文新建/编辑共用表单弹窗 */
export default function PaperFormModal({
  open,
  initial,
  onClose,
  onSaved,
}: {
  open: boolean
  initial: Paper | null
  onClose: () => void
  onSaved: () => void
}) {
  const [form] = Form.useForm()
  const [projects, setProjects] = useState<Project[]>([])
  const [journals, setJournals] = useState<Journal[]>([])
  const [journalOpen, setJournalOpen] = useState(false)
  const [journalForm] = Form.useForm()

  useEffect(() => {
    if (!open) return
    api.get<Project[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
    api.get<Journal[]>('/papers/journals').then((r) => setJournals(r.data)).catch(() => {})
    form.setFieldsValue(
      initial
        ? {
            title: initial.title,
            project_id: initial.project_id ?? undefined,
            paper_type: initial.paper_type,
            paper_scale: initial.paper_scale ?? '小论文',
            target_journal: initial.target_journal,
            journal_quartile: initial.journal_quartile,
            journal_if: initial.journal_if,
            submission_deadline: initial.submission_deadline ? dayjs(initial.submission_deadline) : null,
            keywords: initial.keywords ? initial.keywords.split(',').map((s) => s.trim()).filter(Boolean) : [],
            abstract: initial.abstract,
            status: initial.status,
          }
        : { paper_type: '期刊', paper_scale: '小论文', status: 'Draft', keywords: [] },
    )
  }, [open, initial, form])

  /** 从期刊库选择：自动填充分区与影响因子 */
  const onJournalChange = (name: string) => {
    const j = journals.find((x) => x.name === name)
    if (j) {
      form.setFieldsValue({ journal_quartile: j.quartile, journal_if: j.impact_factor })
    }
  }

  const saveJournal = () => {
    journalForm.validateFields().then((v) => {
      api.post('/papers/journals', v).then((r) => {
        message.success('期刊已加入库')
        setJournals([...journals, r.data])
        setJournalOpen(false)
        journalForm.resetFields()
      }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
    })
  }

  const save = () => {
    form.validateFields().then((v) => {
      const body = {
        ...v,
        keywords: (v.keywords ?? []).join(','),
        submission_deadline: v.submission_deadline?.format('YYYY-MM-DD') ?? null,
      }
      const req = initial ? api.put(`/papers/${initial.id}`, body) : api.post('/papers', body)
      req
        .then(() => {
          onSaved()
          onClose()
        })
        .catch(() => {})
    })
  }

  return (
    <>
    <Modal
      title={initial ? '编辑论文' : '新建论文'}
      open={open}
      onOk={save}
      onCancel={onClose}
      okText="保存"
      destroyOnClose
      width={640}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入论文标题' }]}>
          <Input placeholder="论文完整标题" />
        </Form.Item>
        <Form.Item name="project_id" label="所属项目">
          <Select
            allowClear
            placeholder="可选：关联到某个项目"
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
          />
        </Form.Item>
        <Form.Item name="paper_type" label="类型">
          <Select options={TYPE_OPTIONS.map((t) => ({ value: t, label: t }))} />
        </Form.Item>
        <Form.Item name="paper_scale" label="论文规模">
          <Select options={[
            { value: '小论文', label: '小论文（期刊/会议短文）' },
            { value: '大论文', label: '大论文（学位论文/长篇）' },
          ]} />
        </Form.Item>
        <Form.Item name="status" label="当前状态">
          <Select options={STATUS_OPTIONS.map((s) => ({ value: s, label: s }))} />
        </Form.Item>
        <Form.Item name="target_journal" label="目标期刊 / 会议">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="target_journal" noStyle rules={[{ required: true, message: '请输入期刊名' }]}>
              <Select
                showSearch
                placeholder="从期刊库选择或输入（自动填充分区/IF）"
                options={journals.map((j) => ({
                  value: j.name,
                  label: `${j.name}${j.quartile ? `（${j.quartile}）` : ''}${j.impact_factor ? ` IF ${j.impact_factor}` : ''}`,
                }))}
                onChange={onJournalChange}
              />
            </Form.Item>
            <Button onClick={() => setJournalOpen(true)}>期刊库</Button>
          </Space.Compact>
        </Form.Item>
        <Form.Item label="期刊分区 / 影响因子">
          <Input.Group compact>
            <Form.Item name="journal_quartile" noStyle>
              <Input placeholder="分区（如 Q1）" style={{ width: '45%' }} />
            </Form.Item>
            <Form.Item name="journal_if" noStyle>
              <Input placeholder="影响因子" style={{ width: '55%' }} />
            </Form.Item>
          </Input.Group>
        </Form.Item>
        <Form.Item name="submission_deadline" label="投稿截止日期（期刊截稿提醒用）">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="keywords" label="关键词">
          <Select mode="tags" placeholder="输入后回车" open={false} suffixIcon={null} />
        </Form.Item>
        <Form.Item name="abstract" label="摘要">
          <Input.TextArea rows={5} />
        </Form.Item>
      </Form>
    </Modal>

    {/* 期刊库管理弹窗 */}
    <Modal
      title="目标期刊库"
      open={journalOpen}
      onCancel={() => setJournalOpen(false)}
      footer={
        <Space>
          <Form form={journalForm} layout="inline" style={{ display: 'flex', gap: 8 }}>
            <Form.Item name="name" rules={[{ required: true, message: '期刊名' }]}>
              <Input placeholder="期刊名" style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="quartile" noStyle>
              <Select placeholder="分区" allowClear style={{ width: 90 }}
                options={['Q1', 'Q2', 'Q3', 'Q4'].map((q) => ({ value: q, label: q }))} />
            </Form.Item>
            <Form.Item name="impact_factor" noStyle>
              <Input placeholder="IF" style={{ width: 70 }} />
            </Form.Item>
            <Button type="primary" onClick={saveJournal}>添加</Button>
          </Form>
          <Button onClick={() => setJournalOpen(false)}>关闭</Button>
        </Space>
      }
      width={640}
    >
      <div style={{ maxHeight: 320, overflow: 'auto' }}>
        {journals.map((j) => (
          <div key={j.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 4px', borderBottom: '1px solid #1E293B' }}>
            <span>{j.name}</span>
            <span style={{ color: '#94A3B8', fontSize: 12 }}>
              {j.quartile && <span style={{ marginRight: 8 }}>{j.quartile}</span>}
              {j.impact_factor && <span style={{ marginRight: 8 }}>IF {j.impact_factor}</span>}
              {j.review_weeks && <span>审稿约 {j.review_weeks} 周</span>}
            </span>
          </div>
        ))}
      </div>
    </Modal>
    </>
  )
}
