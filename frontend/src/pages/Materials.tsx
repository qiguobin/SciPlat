import { useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, List, message, Modal, Popconfirm, Select, Space, Table, Tabs, Tag, Upload,
} from 'antd'
import {
  DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, PlusOutlined, UploadOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAppStore } from '../store'
import { fmtDateTime, fmtSize, splitTags } from '../utils'
import FilePreview from '../components/FilePreview'
import ResourcePanel from '../components/ResourcePanel'
import type { Material, MaterialVersion, Project } from '../types'

const CATEGORY_OPTIONS = ['数据', '代码', '图表', '实验记录', '文档', '其他']
const CATEGORY_COLORS: Record<string, string> = {
  数据: 'geekblue', 代码: 'purple', 图表: 'cyan', 实验记录: 'green', 文档: 'blue', 其他: 'default',
}

export default function Materials() {
  const nav = useNavigate()
  const { sub = 'list' } = useParams()
  const [params] = useSearchParams()
  const [list, setList] = useState<Material[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [projectFilter, setProjectFilter] = useState<number | undefined>(
    params.get('project_id') ? Number(params.get('project_id')) : undefined,
  )
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>()
  const [search, setSearch] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [fileList, setFileList] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<Material | null>(null)
  const [editTarget, setEditTarget] = useState<Material | null>(null)
  const [versions, setVersions] = useState<MaterialVersion[]>([])
  const [editForm] = Form.useForm()
  const [upForm] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)
  const bump = useAppStore((s) => s.bump)

  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [batchCategory, setBatchCategory] = useState<string | undefined>()

  const batchAction = (action: string) => {
    if (selectedIds.length === 0) { message.warning('请先选择材料'); return }
    const body: Record<string, unknown> = { ids: selectedIds, action }
    if (action === 'category') {
      if (!batchCategory) { message.warning('请选择分类'); return }
      body.category = batchCategory
    }
    if (action === 'tags') {
      const tags = prompt('输入要添加的标签（逗号分隔）：')
      if (!tags) return
      body.tags = tags
    }
    api.post('/materials/batch', body).then(() => {
      message.success('批量操作完成')
      setSelectedIds([])
      bump()
    }).catch((e) => message.error(e.response?.data?.detail ?? '操作失败'))
  }

  const load = () => {
    setLoading(true)
    api
      .get<Material[]>('/materials', {
        params: { project_id: projectFilter, category: categoryFilter, q: search || undefined },
      })
      .then((r) => setList(r.data))
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }
  useEffect(load, [refreshKey, projectFilter, categoryFilter, search])

  useEffect(() => {
    api.get<Project[]>('/projects').then((r) => setProjects(r.data)).catch(() => {})
  }, [])

  const doUpload = () => {
    if (fileList.length === 0) {
      message.warning('请选择文件')
      return
    }
    setUploading(true)
    const fd = new FormData()
    fileList.forEach((f) => fd.append('files', f))
    const v = upForm.getFieldsValue()
    if (v.project_id) fd.append('project_id', String(v.project_id))
    fd.append('category', v.category ?? '其他')
    fd.append('tags', (v.tags ?? []).join(','))
    fd.append('description', v.description ?? '')
    api.post('/materials', fd)
      .then((r) => {
        message.success(`已上传 ${r.data.length} 个文件`)
        setUploadOpen(false)
        setFileList([])
        upForm.resetFields()
        bump()
      })
      .catch((e) => message.error(e.response?.data?.detail ?? '上传失败'))
      .finally(() => setUploading(false))
  }

  const saveEdit = () => {
    editForm.validateFields().then((v) => {
      api.put(`/materials/${editTarget!.id}`, {
        name: v.name,
        category: v.category,
        tags: (v.tags ?? []).join(','),
        description: v.description ?? '',
      }).then(() => {
        message.success('已更新')
        setEditTarget(null)
        bump()
      })
    })
  }

  return (
    <Tabs
      activeKey={sub}
      onChange={(k) => nav(`/materials/${k}`)}
      items={[
        {
          key: 'list',
          label: '材料列表',
          children: (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Select
            placeholder="按项目筛选"
            allowClear
            style={{ width: 220 }}
            value={projectFilter}
            onChange={(v) => setProjectFilter(v)}
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
          />
          <Select
            placeholder="按分类筛选"
            allowClear
            style={{ width: 140 }}
            value={categoryFilter}
            onChange={(v) => setCategoryFilter(v)}
            options={CATEGORY_OPTIONS.map((c) => ({ value: c, label: c }))}
          />
          <Input.Search
            placeholder="搜索名称 / 标签"
            allowClear
            style={{ width: 220 }}
            onSearch={(v) => setSearch(v)}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            上传材料
          </Button>
          {selectedIds.length > 0 && (
            <>
              <Select
                placeholder="批量改分类" allowClear style={{ width: 130 }} value={batchCategory}
                onChange={(v) => setBatchCategory(v)}
                options={CATEGORY_OPTIONS.map((c) => ({ value: c, label: c }))}
              />
              <Button onClick={() => batchAction('category')} disabled={!batchCategory}>应用分类</Button>
              <Button onClick={() => batchAction('tags')}>批量加标签</Button>
              <Popconfirm title={`删除选中的 ${selectedIds.length} 个材料？`} onConfirm={() => batchAction('delete')}>
                <Button danger>批量删除</Button>
              </Popconfirm>
            </>
          )}
        </Space>
      </Card>

      <Card size="small">
        <Table<Material>
          rowKey="id"
          loading={loading}
          dataSource={list}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys as number[]),
          }}
          columns={[
            { title: '名称', dataIndex: 'name', ellipsis: true },
            {
              title: '分类',
              dataIndex: 'category',
              width: 100,
              render: (c: string) => <Tag color={CATEGORY_COLORS[c] ?? 'default'}>{c}</Tag>,
            },
            { title: '所属项目', dataIndex: 'project_title', width: 170, ellipsis: true, render: (v) => v || '—' },
            {
              title: '标签',
              dataIndex: 'tags',
              width: 180,
              ellipsis: true,
              render: (t: string) => splitTags(t).map((x) => <Tag key={x}>{x}</Tag>),
            },
            { title: '文件', dataIndex: 'file_name', width: 200, ellipsis: true },
            { title: '大小', dataIndex: 'size', width: 90, render: (v: number) => fmtSize(v) },
            { title: '上传时间', dataIndex: 'created_at', width: 150, render: (v) => fmtDateTime(v) },
            {
              title: '操作',
              width: 170,
              render: (_, m) => (
                <Space>
                  <Button size="small" icon={<EyeOutlined />} onClick={() => setPreview(m)} title="预览" />
                  <Button size="small" icon={<DownloadOutlined />} href={`/api/materials/${m.id}/download`} title="下载" />
                  <Button
                    size="small" icon={<EditOutlined />}
                    onClick={() => {
                      setEditTarget(m)
                      editForm.setFieldsValue({
                        name: m.name,
                        category: m.category,
                        tags: splitTags(m.tags),
                        description: m.description,
                      })
                      api.get<MaterialVersion[]>(`/materials/${m.id}/versions`).then((r) => setVersions(r.data)).catch(() => {})
                    }}
                  />
                  <Popconfirm title="删除该材料及文件？" onConfirm={() => {
                    api.delete(`/materials/${m.id}`).then(() => {
                      message.success('已删除')
                      bump()
                    })
                  }}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
          locale={{ emptyText: '暂无材料' }}
        />
      </Card>

      {/* 上传弹窗 */}
      <Modal
        title="上传科研材料"
        open={uploadOpen}
        onOk={doUpload}
        onCancel={() => setUploadOpen(false)}
        okText="上传"
        confirmLoading={uploading}
        destroyOnClose
      >
        <Form form={upForm} layout="vertical">
          <Form.Item label="文件（可多选）" required>
            <Upload
              multiple
              beforeUpload={(f) => {
                setFileList((prev) => [...prev, f])
                return false
              }}
              onRemove={(f) => setFileList((prev) => prev.filter((x) => x.name !== f.name))}
              fileList={fileList.map((f) => ({ uid: f.name, name: f.name }))}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="project_id" label="所属项目">
            <Select
              allowClear
              placeholder="可选"
              options={projects.map((p) => ({ value: p.id, label: p.title }))}
            />
          </Form.Item>
          <Form.Item name="category" label="分类" initialValue="其他">
            <Select options={CATEGORY_OPTIONS.map((c) => ({ value: c, label: c }))} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入后回车" open={false} suffixIcon={null} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
        {versions.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>历史版本（{versions.length}）</div>
            <List
              size="small"
              dataSource={versions}
              renderItem={(v) => (
                <List.Item
                  style={{ paddingInline: 4 }}
                  actions={[
                    <Button key="dl" size="small" type="link" href={`/api/materials/versions/${v.id}/download`}>下载</Button>,
                    <Popconfirm key="rb" title="回滚到此版本？当前文件将存为新版本。" onConfirm={() => {
                      api.post(`/materials/${editTarget!.id}/versions/${v.id}/restore`).then(() => {
                        message.success('已回滚')
                        bump()
                        setEditTarget(null)
                      })
                    }}>
                      <Button size="small" type="link">回滚</Button>
                    </Popconfirm>,
                  ]}
                >
                  <Space size={8}>
                    <Tag>v{v.version_no}</Tag>
                    <span style={{ fontSize: 12 }}>{v.file_name}</span>
                    <span style={{ fontSize: 12, color: '#8a94a3' }}>{fmtDateTime(v.created_at)}</span>
                  </Space>
                </List.Item>
              )}
            />
          </div>
        )}
      </Modal>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑材料信息"
        open={!!editTarget}
        onOk={saveEdit}
        onCancel={() => setEditTarget(null)}
        okText="保存"
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Select options={CATEGORY_OPTIONS.map((c) => ({ value: c, label: c }))} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" open={false} suffixIcon={null} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
        {versions.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>历史版本（{versions.length}）</div>
            <List
              size="small"
              dataSource={versions}
              renderItem={(v) => (
                <List.Item
                  style={{ paddingInline: 4 }}
                  actions={[
                    <Button key="dl" size="small" type="link" href={`/api/materials/versions/${v.id}/download`}>下载</Button>,
                    <Popconfirm key="rb" title="回滚到此版本？当前文件将存为新版本。" onConfirm={() => {
                      api.post(`/materials/${editTarget!.id}/versions/${v.id}/restore`).then(() => {
                        message.success('已回滚')
                        bump()
                        setEditTarget(null)
                      })
                    }}>
                      <Button size="small" type="link">回滚</Button>
                    </Popconfirm>,
                  ]}
                >
                  <Space size={8}>
                    <Tag>v{v.version_no}</Tag>
                    <span style={{ fontSize: 12 }}>{v.file_name}</span>
                    <span style={{ fontSize: 12, color: '#8a94a3' }}>{fmtDateTime(v.created_at)}</span>
                  </Space>
                </List.Item>
              )}
            />
          </div>
        )}
      </Modal>

      <FilePreview material={preview} onClose={() => setPreview(null)} />
    </Space>
          ),
        },
        {
          key: 'resources',
          label: '资源库存',
          children: <ResourcePanel />,
        },
      ]}
    />
  )
}
