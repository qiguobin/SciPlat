import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import { FACTOR_LABELS } from '../types'
import type { NetworkData, NetworkLink, NetworkNode } from '../types'

const READ_COLORS: Record<string, string> = {
  未读: '#475569',
  在读: '#FBBF24',
  已读: '#34D399',
}

/** 文献关联图谱：力导向图（节点=文献，边=关联强度） */
export default function NetworkGraph({
  data,
  onNodeClick,
  height = 560,
}: {
  data: NetworkData
  onNodeClick: (node: NetworkNode) => void
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)

  const option = useMemo(() => {
    // 度数 → 节点大小
    const degree = new Map<number, number>()
    data.links.forEach((l) => {
      degree.set(l.source, (degree.get(l.source) ?? 0) + 1)
      degree.set(l.target, (degree.get(l.target) ?? 0) + 1)
    })

    const nodes = data.nodes.map((n) => ({
      id: n.id,
      name: n.title,
      symbolSize: 16 + Math.min((degree.get(n.id) ?? 0) * 2.5, 26),
      itemStyle: { color: READ_COLORS[n.read_status] ?? '#8a94a3' },
      label: { show: false },
      data: n,
    }))

    const links = data.links.map((l) => ({
      source: l.source,
      target: l.target,
      value: l.weight,
      lineStyle: {
        width: Math.max(1.5, l.weight / 25),
        color: l.citation ? '#b03a2e' : l.ai ? '#A78BFA' : '#8fa3c0',
        opacity: 0.55,
        type: l.citation ? ('dashed' as const) : ('solid' as const),
      },
      data: l,
    }))

    return {
      tooltip: {
        trigger: 'item' as const,
        formatter: (p: { dataType?: string; data?: { data?: NetworkNode | NetworkLink } }) => {
          if (p.dataType === 'edge') {
            const l = p.data?.data as NetworkLink
            const detail = (l.factors ?? []).map((f) => FACTOR_LABELS[f] ?? f).join(' · ')
            const aiInfo = l.ai && l.reason
              ? `<br/><span style="color:#A78BFA">🤖 ${l.reason}</span>${(l.ai_tags ?? []).map((t) => ` <span style="color:#A78BFA">#${t}</span>`).join('')}`
              : ''
            return `<b>关联强度 ${l.weight}</b><br/>${detail}${aiInfo}`
          }
          const n = p.data?.data as NetworkNode
          if (!n) return ''
          return `<b>${n.title}</b><br/>${n.tags || '无标签'}`
        },
      },
      series: [{
        type: 'graph' as const,
        layout: 'force' as const,
        roam: true,
        draggable: true,
        data: nodes,
        links,
        force: {
          repulsion: 220,
          edgeLength: [60, 160],
          gravity: 0.08,
        },
        emphasis: {
          focus: 'adjacency' as const,
          label: { show: true, fontSize: 12, fontWeight: 600 },
          lineStyle: { opacity: 1 },
        },
        label: {
          show: false,
          position: 'right' as const,
          color: '#202a3a',
        },
      }],
    }
  }, [data])

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(option)
    chart.on('click', (params: echarts.ECElementEvent) => {
      const p = params as unknown as { dataType?: string; data?: { data?: NetworkNode } }
      if (p.dataType === 'node' && p.data?.data) {
        onNodeClick(p.data.data)
      }
    })
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [option, onNodeClick])

  return <div ref={ref} style={{ height, width: '100%' }} />
}
