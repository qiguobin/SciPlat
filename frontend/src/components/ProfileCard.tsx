import { useEffect, useState } from 'react'
import { Avatar, Button, Card, Form, Input, Modal, Progress, Space, Tag, Upload, message } from 'antd'
import { CameraOutlined, EditOutlined, UserOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAppStore } from '../store'
import type { Profile } from '../types'

/** 学生信息卡：仪表盘顶部展示 + 可编辑（含头像上传） */
export default function ProfileCard() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const refreshKey = useAppStore((s) => s.refreshKey)

  const load = () => {
    api.get<Profile>('/profile').then((r) => setProfile(r.data)).catch(() => {})
  }
  useEffect(load, [refreshKey])

  const openEditor = (p: Profile) => {
    form.setFieldsValue({
      name: p.name, student_id: p.student_id, school: p.school,
      college: p.college, major: p.major, advisor: p.advisor,
      research_direction: p.research_direction,
      enrollment_year: p.enrollment_year, expected_graduation: p.expected_graduation,
      contact: p.contact,
    })
    setOpen(true)
  }

  if (!profile) return <Card loading style={{ marginBottom: 16 }} />

  const filled = profile.name || profile.school || profile.major || profile.research_direction
  const yearNow = new Date().getFullYear()
  const enr = profile.enrollment_year
  const exp = profile.expected_graduation
  const years = enr && exp ? Math.max(1, exp - enr) : 0
  const progress = enr && exp ? Math.min(100, Math.round(((yearNow - enr) / years) * 100)) : 0
  const currentYear = enr ? Math.min(years, Math.max(1, yearNow - enr + 1)) : 0

  return (
    <>
      <Card size="small" style={{ height: '100%' }} hoverable={!filled} onClick={() => !filled && openEditor(profile)}>
        {filled ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', height: '100%' }}>
            <Avatar size={48} src={profile.photo_path ? `/api/profile/photo` : undefined} icon={<UserOutlined />} />
            <div style={{ flex: 1, minWidth: 220 }}>
              <Space wrap size={4}>
                <span style={{ fontSize: 16, fontWeight: 700 }}>{profile.name}</span>
                {profile.major && <Tag>{profile.major}</Tag>}
                {profile.research_direction && <Tag color="blue">{profile.research_direction}</Tag>}
              </Space>
              <div style={{ color: '#5b6675', fontSize: 12, marginTop: 1 }}>
                {[profile.school, profile.college, profile.student_id].filter(Boolean).join(' · ')}
                {profile.advisor && ` · 导师：${profile.advisor}`}
              </div>
              {years > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 3 }}>
                  <Progress
                    percent={progress}
                    size="small"
                    style={{ flex: 1, maxWidth: 240, margin: 0 }}
                    strokeColor="#34D399"
                  />
                  <span style={{ fontSize: 12, color: '#5b6675', whiteSpace: 'nowrap' }}>
                    {enr} 级 · 学制第 {currentYear} 年 / 预计 {exp} 毕业
                  </span>
                </div>
              )}
            </div>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(profile)}>
              编辑资料
            </Button>
          </div>
        ) : (
          <Space>
            <Avatar size={44} icon={<UserOutlined />} />
            <div>
              <div style={{ fontWeight: 600 }}>还没有学生档案</div>
              <div style={{ color: '#8a94a3', fontSize: 13 }}>
                点击填写姓名、研究方向、导师等信息，仪表盘将展示你的学制进度
              </div>
            </div>
          </Space>
        )}
      </Card>

      <Modal
        title="编辑学生档案"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          form.validateFields().then((v) => {
            api.put('/profile', v).then(() => {
              message.success('已保存')
              setOpen(false)
              api.get<Profile>('/profile').then((r) => setProfile(r.data))
            }).catch((e) => message.error(e.response?.data?.detail ?? '保存失败'))
          })
        }}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item label="头像">
            <Upload
              showUploadList={false}
              accept="image/*"
              beforeUpload={(f) => {
                const fd = new FormData()
                fd.append('file', f)
                api.post('/profile/photo', fd).then(() => {
                  message.success('头像已更新')
                  api.get<Profile>('/profile').then((r) => setProfile(r.data))
                }).catch(() => message.error('头像上传失败'))
                return false
              }}
            >
              <Button icon={<CameraOutlined />}>上传头像</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="name" label="姓名"><Input /></Form.Item>
          <Form.Item name="student_id" label="学号"><Input /></Form.Item>
          <Form.Item label="学校 / 学院">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="school" noStyle><Input placeholder="学校" style={{ width: '50%' }} /></Form.Item>
              <Form.Item name="college" noStyle><Input placeholder="学院" style={{ width: '50%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item label="专业 / 导师">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="major" noStyle><Input placeholder="专业" style={{ width: '50%' }} /></Form.Item>
              <Form.Item name="advisor" noStyle><Input placeholder="导师" style={{ width: '50%' }} /></Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="research_direction" label="研究方向"><Input /></Form.Item>
          <Form.Item label="入学年份 / 预计毕业年份">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="enrollment_year" noStyle>
                <Input type="number" placeholder="如 2024" style={{ width: '50%' }} />
              </Form.Item>
              <Form.Item name="expected_graduation" noStyle>
                <Input type="number" placeholder="如 2028" style={{ width: '50%' }} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item name="contact" label="联系方式"><Input placeholder="邮箱 / 电话" /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
