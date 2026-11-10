import { ArrowUpRight, BookOpen, ChevronDown, Database, FileCode2, Search, ShieldCheck, Swords, UsersRound } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { displayError, listResult, request } from '../api';
import type { Entity, Ruling, Snapshot } from '../types';
import { CitationList, EmptyState, ErrorNotice, Spinner, StatusTag } from './ui';

interface Props { token: string; snapshots: Snapshot[]; snapshotId: string; onSnapshotChange: (id: string) => void; onAsk: (question: string) => void }
const kinds = [{ id: 'general', label: '武将', icon: UsersRound }, { id: 'card', label: '卡牌', icon: Swords }, { id: 'skill', label: '技能', icon: FileCode2 }];
const packageLabels: Record<string, string> = { standard: '标准武将', standard_cards: '标准 / EX 牌', maneuvering: '军争' };
const attributeLabels: Record<string, string> = { hp: '体力', max_hp: '体力上限', kingdom: '势力', gender: '性别', skills: '技能', card_type: '类型', subtype: '子类型', range: '攻击范围', suit: '花色', number: '点数' };

export default function Library({ token, snapshots, snapshotId, onSnapshotChange, onAsk }: Props) {
  const [kind, setKind] = useState('general');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [rulings, setRulings] = useState<Ruling[]>([]);
  const [tab, setTab] = useState<'entities' | 'rulings'>('entities');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      if (tab === 'rulings') setRulings(listResult(await request<Ruling[] | { items: Ruling[] }>(`/catalog/rulings?snapshot_id=${encodeURIComponent(snapshotId)}`, token)));
      else setEntities(listResult(await request<Entity[] | { items: Entity[] }>(`/catalog/entities?kind=${kind}&query=${encodeURIComponent(search)}&snapshot_id=${encodeURIComponent(snapshotId)}`, token)));
    } catch (error) { setError(displayError(error)); }
    finally { setLoading(false); }
  }, [kind, search, snapshotId, tab, token]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { const timer = window.setTimeout(() => setSearch(query), 250); return () => clearTimeout(timer); }, [query]);
  const snapshot = snapshots.find(item => item.id === snapshotId);

  return <section className="standard-page library-page"><div className="page-heading"><div><span className="section-kicker">先找到依据，再形成结论</span><h1>游戏资料库</h1><p>查询武将、卡牌与技能，回看明确标注版本的规则证据</p></div><div className="snapshot-control"><Database size={14} /><label className="sr-only" htmlFor="library-snapshot">资料库快照</label><select id="library-snapshot" value={snapshotId} onChange={e => onSnapshotChange(e.target.value)}>{!snapshots.length && <option value="">暂无快照</option>}{snapshots.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><ChevronDown size={13} /></div></div>
    <div className="library-overview"><div className="overview-icon"><BookOpen size={28} strokeWidth={1.3} /></div><div><span className="eyebrow">CURRENT SNAPSHOT</span><h2>{snapshot?.label ?? '资料快照等待导入'}</h2><p>标准武将 <span>／</span> 标准与 EX 牌 <span>／</span> 军争</p></div><div className="snapshot-version"><span>源码标识</span><code>{snapshot?.commit?.slice(0, 12) ?? '待记录'}</code><small>每条资料保留独立来源</small></div></div>
    <div className="tab-row" role="tablist" aria-label="资料分类"><button role="tab" aria-selected={tab === 'entities'} className={tab === 'entities' ? 'active' : ''} onClick={() => setTab('entities')}><BookOpen size={16} />游戏图鉴</button><button role="tab" aria-selected={tab === 'rulings'} className={tab === 'rulings' ? 'active' : ''} onClick={() => setTab('rulings')}><ShieldCheck size={16} />复杂裁定</button></div>
    {error && <ErrorNotice message={error} onRetry={() => void load()} />}
    {tab === 'entities' ? <><div className="library-controls"><div className="segmented-control" role="group" aria-label="实体类型">{kinds.map(item => <button key={item.id} className={kind === item.id ? 'selected' : ''} onClick={() => { setKind(item.id); setExpanded(null); }}><item.icon size={14} />{item.label}</button>)}</div><div className="search-field"><Search size={16} /><label className="sr-only" htmlFor="entity-search">搜索资料</label><input id="entity-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索名称、技能或关键词" /></div></div>{loading ? <div className="panel-loading"><Spinner label="正在查找资料" /></div> : entities.length ? <><div className="results-meta">找到 <strong>{entities.length}</strong> 条资料<span>点击展开来源与属性</span></div><div className="entity-grid">{entities.map(entity => <article className={`entity-card ${expanded === entity.id ? 'expanded' : ''}`} key={entity.id}><button className="entity-heading" aria-expanded={expanded === entity.id} onClick={() => setExpanded(expanded === entity.id ? null : entity.id)}><span className={`entity-symbol ${entity.kind}`}>{entity.name?.slice(0, 1) ?? '?'}</span><span><small>{packageLabels[entity.package] ?? entity.package}</small><h3>{entity.name}</h3></span><ChevronDown size={16} className={expanded === entity.id ? 'rotated' : ''} /></button><p className="entity-description">{entity.description || '展开查看结构化属性与原始资料'}</p>{expanded === entity.id && <div className="entity-expanded"><dl>{Object.entries(entity.attributes ?? {}).map(([key, value]) => <div key={key}><dt>{attributeLabels[key] ?? key}</dt><dd>{Array.isArray(value) ? value.join('、') : typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>{entity.source && <CitationList items={[entity.source]} compact />}<button className="text-button teal" onClick={() => onAsk(`请介绍${entity.name}的规则与使用条件，并提供来源。`)}>问问轻归<ArrowUpRight size={14} /></button></div>}</article>)}</div></> : <EmptyState title={query ? '没有找到匹配资料' : '当前还没有图鉴记录'} detail={query ? '尝试更短的名称，或切换武将、卡牌、技能分类' : '先在后台任务中导入已配置的资料快照'} />}</> : <><div className="info-callout"><ShieldCheck size={18} /><p>只有附带规则引擎执行证据的场景才标为“引擎已验证”；裁定适用于所列前提和快照</p></div>{loading ? <div className="panel-loading"><Spinner label="加载裁定场景" /></div> : rulings.length ? <div className="ruling-grid">{rulings.map(ruling => <article className="ruling-card" key={ruling.id}><div className="ruling-card-top"><code>{ruling.id}</code><StatusTag status={ruling.status} /></div><h3>{ruling.title}</h3><p>{ruling.summary || '场景结论需结合完整条件与执行证据核对'}</p><button className="text-button" onClick={() => setExpanded(expanded === ruling.id ? null : ruling.id)} aria-expanded={expanded === ruling.id}>查看前提条件<ChevronDown size={13} className={expanded === ruling.id ? 'rotated' : ''} /></button>{expanded === ruling.id && <div className="ruling-conditions">{Array.isArray(ruling.required_conditions) ? <ul>{ruling.required_conditions.map((item, index) => <li key={index}>{item}</li>)}</ul> : <dl>{Object.entries(ruling.required_conditions ?? {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}<small>快照 {ruling.snapshot_id}</small></div>}<button className="ruling-ask" onClick={() => onAsk(`请核对 ${ruling.id}「${ruling.title}」的结算，先告诉我需要补充哪些局面条件。`)}>带着这个场景提问<ArrowUpRight size={14} /></button></article>)}</div> : <EmptyState title="裁定场景尚未载入" detail="请先检查规则场景和证据是否已导入；未执行场景不会显示为已验证" />}</>}
  </section>;
}
