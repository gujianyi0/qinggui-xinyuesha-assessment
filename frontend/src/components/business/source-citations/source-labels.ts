const LABELS: Record<string, string> = {
  rule: '规则说明',
  rules: '规则说明',
  skill: '技能描述',
  description: '资料说明',
  implementation: '实现代码',
  code: '实现代码',
  verified_ruling: '已验证裁定',
  ruling: '裁定记录',
  rule_text: '规则说明',
  skill_description: '技能说明',
  project_scope: '项目范围',
  conversation: '本会话陈述',
  user_statement: '本会话陈述',
}
export function sourceLabel(kind?: string) {
  return LABELS[kind ?? ''] ?? '资料来源'
}
