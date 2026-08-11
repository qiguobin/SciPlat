/** 启发式 TLDR：摘要首句 + 截断（前端显示用） */
export function trackerTldr(abstract: string, maxLen = 220): string {
  if (!abstract) return ''
  const first = abstract.split(/[.。]\s/, 1)[0]
  return first.length > maxLen ? first.slice(0, maxLen) + '…' : first
}
