import { AlertCircle, BookOpen, Check, ChevronDown, FileText, LoaderCircle, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import type { Citation } from '../types';

export function Spinner({ label = '加载中' }: { label?: string }) {
  return <span className="inline-loading"><LoaderCircle size={16} className="spin" aria-hidden="true" />{label}</span>;
}

export function ErrorNotice({ message, onRetry, onDismiss }: { message: string; onRetry?: () => void; onDismiss?: () => void }) {
  return <div className="error-notice" role="alert"><AlertCircle size={18} aria-hidden="true" /><span>{message}</span>
    {onRetry && <button className="text-button" onClick={onRetry}><RefreshCw size={14} />重试</button>}
    {onDismiss && <button className="text-button" onClick={onDismiss}>关闭</button>}
  </div>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><div className="empty-symbol"><BookOpen size={26} strokeWidth={1.4} /></div><h3>{title}</h3><p>{detail}</p></div>;
}

export const statusLabels: Record<string, string> = {
  queued: '等待处理', pending: '等待处理', running: '正在处理', retry_wait: '等待重试',
  cancel_requested: '正在取消', succeeded: '已完成', completed: '已完成', failed: '失败',
  cancelled: '已取消', draft: '待确认', confirmed: '已确认', submitted: '已提交',
  verified: '引擎已验证', unverified: '待引擎验证', pending_verification: '待引擎验证',
};

export function StatusTag({ status }: { status: string }) {
  const tone = ['succeeded', 'completed', 'confirmed', 'submitted', 'verified'].includes(status) ? 'success'
    : status === 'failed' ? 'danger' : ['running', 'retry_wait', 'cancel_requested'].includes(status) ? 'working' : 'neutral';
  return <span className={`status-tag ${tone}`}>{tone === 'success' ? <Check size={12} /> : <span className="status-dot" />}{statusLabels[status] ?? status}</span>;
}

const evidenceLabels: Record<string, string> = {
  rule: '规则说明', rules: '规则说明', skill: '技能描述', description: '资料说明',
  implementation: '实现代码', code: '实现代码', verified_ruling: '已验证裁定', ruling: '裁定记录',
};

export function CitationList({ items, compact = false }: { items: Citation[]; compact?: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!items?.length) return null;
  return <div className={`citation-list ${compact ? 'compact' : ''}`}>
    {!compact && <div className="eyebrow citation-heading"><BookOpen size={13} />依据与来源 <span>{items.length}</span></div>}
    {items.map((item, index) => <div className="citation-item" key={`${item.id}-${index}`}>
      <button className="citation-trigger" onClick={() => setExpanded(expanded === `${item.id}-${index}` ? null : `${item.id}-${index}`)} aria-expanded={expanded === `${item.id}-${index}`}>
        <span className="citation-number">{index + 1}</span><span className="citation-name">{item.title || item.path}<small>{evidenceLabels[item.evidence_type ?? ''] ?? item.evidence_type ?? '资料来源'}</small></span><ChevronDown size={14} className={expanded === `${item.id}-${index}` ? 'rotated' : ''} />
      </button>
      {expanded === `${item.id}-${index}` && <div className="citation-detail"><p><FileText size={12} />{item.path}{item.line_start ? `:${item.line_start}${item.line_end && item.line_end !== item.line_start ? `–${item.line_end}` : ''}` : ''}</p><p className="mono">快照 {item.snapshot_id}</p>{item.excerpt && <blockquote>{item.excerpt}</blockquote>}</div>}
    </div>)}
  </div>;
}

export function relativeDate(value?: string): string {
  if (!value) return '';
  // The database stores naive UTC timestamps; browsers otherwise treat them as local time.
  const date = new Date(/Z$|[+-]\d{2}:\d{2}$/i.test(value) ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }).format(date);
}
