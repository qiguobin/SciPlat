import { Tag } from 'antd'

/** 论文状态 → 标签文案 / antd 色 / 圆点色 */
export const PAPER_STATUS: Record<string, { label: string; color: string; dot: string }> = {
  Draft: { label: '草稿', color: 'default', dot: '#64748B' },
  Submitted: { label: '已投稿', color: 'blue', dot: '#38BDF8' },
  'Under Review': { label: '审稿中', color: 'gold', dot: '#FBBF24' },
  Revision: { label: '修改中', color: 'orange', dot: '#FB923C' },
  Resubmitted: { label: '已重投', color: 'purple', dot: '#A78BFA' },
  Accepted: { label: '已接收', color: 'green', dot: '#34D399' },
  Published: { label: '已发表', color: 'cyan', dot: '#22D3EE' },
  Rejected: { label: '已拒稿', color: 'red', dot: '#F87171' },
}

export const PROJECT_STATUS: Record<string, { label: string; color: string; dot: string }> = {
  进行中: { label: '进行中', color: 'green', dot: '#34D399' },
  暂停: { label: '暂停', color: 'orange', dot: '#FBBF24' },
  已完成: { label: '已完成', color: 'blue', dot: '#38BDF8' },
  已放弃: { label: '已放弃', color: 'default', dot: '#64748B' },
}

export const MILESTONE_STATUS: Record<string, { label: string; color: string; dot: string }> = {
  未开始: { label: '未开始', color: 'default', dot: '#64748B' },
  进行中: { label: '进行中', color: 'blue', dot: '#2f54eb' },
  已完成: { label: '已完成', color: 'green', dot: '#12b886' },
  延期: { label: '延期', color: 'red', dot: '#F87171' },
}

export const READ_STATUS: Record<string, { label: string; color: string; dot: string }> = {
  未读: { label: '未读', color: 'default', dot: '#8a94a6' },
  在读: { label: '在读', color: 'gold', dot: '#FBBF24' },
  已读: { label: '已读', color: 'green', dot: '#34D399' },
}

function DotTag({ meta, text }: { meta: { label: string; color: string; dot: string }; text?: string }) {
  return (
    <Tag color={meta.color} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: meta.dot,
          display: 'inline-block',
          flexShrink: 0,
        }}
      />
      {text ?? meta.label}
    </Tag>
  )
}

export function PaperStatusTag({ status }: { status: string }) {
  const meta = PAPER_STATUS[status] ?? { label: status, color: 'default', dot: '#8a94a6' }
  return <DotTag meta={meta} />
}

export function ProjectStatusTag({ status }: { status: string }) {
  const meta = PROJECT_STATUS[status] ?? { label: status, color: 'default', dot: '#8a94a6' }
  return <DotTag meta={meta} />
}
