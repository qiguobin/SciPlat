/** 操作通知：写操作成功后自动生成可读消息并上报（原生 fetch，绕开 axios 拦截器防递归） */

interface Rule {
  pattern: RegExp
  message: string
  targetType: (m: RegExpMatchArray) => string
  targetId: (m: RegExpMatchArray) => number | null
}

const RULES: Rule[] = [
  { pattern: /^\/api\/todos\/\d+\/status$/, message: '更新了待办状态', targetType: () => 'todo', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/todos\/\d+$/, message: '更新了待办', targetType: () => 'todo', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/todos$/, message: '创建了待办', targetType: () => 'todo', targetId: () => null },
  { pattern: /^\/api\/projects\/\d+\/milestones$/, message: '添加了里程碑', targetType: () => 'project', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/projects\/\d+$/, message: '更新了项目', targetType: () => 'project', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/projects$/, message: '创建了项目', targetType: () => 'project', targetId: () => null },
  { pattern: /^\/api\/projects\/phases\/\d+\/experiments$/, message: '添加了实验记录', targetType: () => 'project', targetId: () => null },
  { pattern: /^\/api\/papers\/\d+$/, message: '更新了论文', targetType: () => 'paper', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/papers$/, message: '创建了论文', targetType: () => 'paper', targetId: () => null },
  { pattern: /^\/api\/references\/\d+$/, message: '更新了文献', targetType: () => 'reference', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/references$/, message: '添加了文献', targetType: () => 'reference', targetId: () => null },
  { pattern: /^\/api\/materials\/\d+$/, message: '更新了材料', targetType: () => 'material', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/materials$/, message: '上传了材料', targetType: () => 'material', targetId: () => null },
  { pattern: /^\/api\/achievements\/\d+$/, message: '更新了成果', targetType: () => 'achievement', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/achievements$/, message: '新增了成果', targetType: () => 'achievement', targetId: () => null },
  { pattern: /^\/api\/ideas\/\d+\/convert$/, message: '转化了灵感', targetType: () => 'idea', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/ideas\/\d+$/, message: '更新了灵感', targetType: () => 'idea', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/ideas$/, message: '收录了灵感', targetType: () => 'idea', targetId: () => null },
  { pattern: /^\/api\/notes\/\d+$/, message: '更新了笔记', targetType: () => 'note', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/notes$/, message: '写了笔记', targetType: () => 'note', targetId: () => null },
  { pattern: /^\/api\/resources\/\d+\/adjust$/, message: '调整了库存', targetType: () => 'resource', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/resources\/\d+$/, message: '更新了资源', targetType: () => 'resource', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/resources$/, message: '新增了资源', targetType: () => 'resource', targetId: () => null },
  { pattern: /^\/api\/canvas\/nodes\/\d+$/, message: '移动了画布卡片', targetType: () => 'canvas', targetId: () => null },
  { pattern: /^\/api\/canvas\/nodes$/, message: '添加了画布卡片', targetType: () => 'canvas', targetId: () => null },
  { pattern: /^\/api\/canvas\/edges$/, message: '连接了画布卡片', targetType: () => 'canvas', targetId: () => null },
  { pattern: /^\/api\/writing-logs\/\d+$/, message: '更新了写作打卡', targetType: () => 'writing', targetId: (m) => Number(m[1]) },
  { pattern: /^\/api\/writing-logs$/, message: '写作打卡成功', targetType: () => 'writing', targetId: () => null },
]

/** 画布节点拖拽会高频触发 PUT，节流：短时间内同路径只报一次 */
const throttle = new Map<string, number>()

function report(message: string, category: string, targetType: string, targetId: number | null) {
  const key = `${targetType}:${targetId ?? ''}:${message}`
  const now = Date.now()
  const last = throttle.get(key) ?? 0
  if (now - last < 3000) return  // 3 秒节流
  throttle.set(key, now)
  try {
    fetch('/api/notifications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, category, target_type: targetType, target_id: targetId }),
    }).catch(() => { /* 静默失败，不影响主流程 */ })
  } catch { /* ignore */ }
}

/** 由写操作 URL 生成通知并上报；无法识别的操作返回 null */
export function notifyOperation(method: string, url: string): void {
  const u = url.split('?')[0]
  const m = method.toUpperCase()
  // 只记录写操作
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(m)) return
  // 排除通知自身与静默类操作
  if (u.includes('/api/notifications')) return
  if (u.includes('/api/settings')) return
  if (u.includes('/api/reading-session')) return
  if (u.includes('/api/profile')) return
  if (u.includes('/import-')) return
  if (u.includes('/fetch-')) return
  if (u.includes('/backup')) return

  for (const rule of RULES) {
    const match = u.match(rule.pattern)
    if (match) {
      // DELETE 语义调整
      const message = m === 'DELETE' ? rule.message.replace('创建了', '删除了').replace('添加了', '删除了').replace('新增了', '删除了').replace('收录了', '删除了').replace('写了', '删除了').replace('上传了', '删除了').replace('连接了', '断开了').replace('移动了', '移动了') : rule.message
      report(message, m === 'DELETE' ? 'warning' : 'success', rule.targetType(match), rule.targetId(match))
      return
    }
  }
  // 兜底：通用消息
  const generic = `${m === 'DELETE' ? '删除了' : '更新了'} ${u.split('/').filter(Boolean).pop() ?? '内容'}`
  report(generic, 'info', '', null)
}
