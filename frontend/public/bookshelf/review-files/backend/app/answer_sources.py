"""Resolve answer citations from the checked sources returned by this run's tools."""

import html
import re

MARKER = '[[sources:'
DECK_FIELDS = re.compile(r'花色|点数|牌堆|张数|印制|(?:有|共)(?:几|多少)张')
RULE_FIELDS = re.compile(r'时机|目标|效果|使用|打出|响应|抵消|区别|不同|对比|比较')
COMPARE = re.compile(r'区别|不同|对比|比较|分别')
IMPLEMENTATION_FIELDS = re.compile(r'实现|代码|源码|内部.?ID|关联技能')


class SourceTail:
    """Keep the model's final citation selection out of the visible token stream."""

    def __init__(self):
        self.buffer = ''
        self.in_tail = False

    def feed(self, text: str) -> str:
        self.buffer += text
        if self.in_tail:
            return ''
        body, marker, tail = self.buffer.partition(MARKER)
        if marker:
            self.buffer = tail
            self.in_tail = True
            return body
        keep = next((length for length in range(len(MARKER) - 1, 0, -1)
                     if MARKER.startswith(self.buffer[-length:]) and len(self.buffer) >= length), 0)
        if keep:
            body, self.buffer = self.buffer[:-keep], self.buffer[-keep:]
            return body
        self.buffer = ''
        return body

    def finish(self) -> tuple[str, list[str] | None]:
        if not self.in_tail:
            return self.buffer, None
        joined, separator, extra = self.buffer.partition(']]')
        if not separator or extra.strip():
            return '', None
        return '', [part.strip() for part in joined.split(',') if part.strip()]


def unique_sources(sources):
    """Canonicalize the same source range across catalog and passage IDs."""
    seen = set()
    result = []
    for source in sources:
        bounds = source.get('line_start'), source.get('line_end')
        location = (*bounds, source.get('evidence_type')) if all(bounds) else (source['id'],)
        key = (source['snapshot_id'], source.get('path'), *location)
        if key not in seen:
            seen.add(key)
            result.append(source)
    return result


def card_tool_context(items, question):
    """Expose card fields suited to the question while preserving full tool audit."""
    deck = bool(DECK_FIELDS.search(question))
    rules = bool(RULE_FIELDS.search(question))
    visible = []
    for item in items:
        if item.get('kind') != 'card' or (deck and rules):
            visible.append(item)
        elif deck:
            visible.append({key: item[key] for key in ('id', 'name', 'kind', 'package', 'attribute_sources') if key in item}
                           | {'attributes': {'deck_specs': item.get('attributes', {}).get('deck_specs', [])}})
        elif rules and item.get('description_sources') and not IMPLEMENTATION_FIELDS.search(question):
            visible.append({key: item[key] for key in ('id', 'name', 'kind', 'package', 'description', 'description_sources')})
        else:
            attributes = {key: value for key, value in item['attributes'].items() if key != 'deck_specs'}
            visible.append({**item, 'attributes': attributes, 'attribute_sources': []})
    return visible


def _card_pattern(card_names):
    # Match longer names first so the 闪 inside 闪电 cannot add a second subject.
    return re.compile('|'.join(re.escape(name) for name in sorted(card_names, key=lambda n: (-len(n), n))))


def card_answer_mode(question, card_names):
    if not card_names or DECK_FIELDS.search(question) or IMPLEMENTATION_FIELDS.search(question):
        return None
    subjects = set(_card_pattern(card_names).findall(question))
    if len(subjects) == 1 and all(field in question for field in ('时机', '目标', '效果')):
        return 'rules'
    if len(subjects) == 2 and COMPARE.search(question):
        return 'compare'
    if len(subjects) == 2 and re.search(r'能(?:否|不能)?用.+响应吗[？?]?$', question):
        return 'response'
    return None


def _plain_card_text(excerpt):
    lines = re.sub(r'<br\s*/?>', '\n', excerpt, flags=re.IGNORECASE)
    return html.unescape(re.sub(r'</?b>', '', lines, flags=re.IGNORECASE))


def render_card_answer(mode, question, citations, card_names):
    """For simple card questions reproduce the source's actual action words."""
    if not mode:
        return None
    subjects = tuple(dict.fromkeys(_card_pattern(card_names).findall(question)))
    descriptions = {source['title']: _plain_card_text(source['excerpt']) for source in citations
                    if source.get('evidence_type') == 'skill_description'
                    and source.get('title') in subjects and source.get('excerpt')}
    if mode == 'response':
        if len(citations) != 1 or subjects[0] not in descriptions:
            return None
        effect = next((line.removeprefix('效果：') for line in descriptions[subjects[0]].splitlines()
                       if line.startswith('效果：')), '')
        obligation = f'每名目标角色需打出一张【{subjects[1]}】'
        if effect.startswith(obligation):
            return f'可以。按【{subjects[0]}】的牌面说明，{effect}'
        return None
    if len(citations) != len(subjects) or len(descriptions) != len(subjects):
        return None
    if any(not all(f'{field}：' in descriptions[name] for field in ('时机', '目标', '效果')) for name in subjects):
        return None
    return '\n\n'.join(f'【{name}】\n{descriptions[name].strip()}' for name in subjects)


def _card_sources(question, answer, candidates, card_names):
    deck = bool(DECK_FIELDS.search(question))
    rules = bool(RULE_FIELDS.search(question))
    if not deck and not rules:
        return None
    names = _card_pattern(card_names)
    subjects = tuple(dict.fromkeys(names.findall(question))) if card_names else ()
    if not subjects or not set(subjects).intersection(names.findall(answer)):
        return None
    if IMPLEMENTATION_FIELDS.search(question) or any(
        len(title) >= 2 and title in question and title in answer and title not in card_names and not title.endswith('牌堆配置')
        for title in (source.get('title', '') for source in candidates)
    ):
        return None  # Questions about code or named skills need the ordinary evidence selection.
    selected = []
    descriptions = [s for s in candidates if s.get('evidence_type') == 'skill_description'
                    and s.get('title') in subjects and s.get('excerpt')]
    if rules and len(subjects) > 1 and not COMPARE.search(question):
        # A rule for the interacting card can be sufficient to answer both names.
        relation = next((s for s in descriptions if set(subjects) <= set(names.findall(s['excerpt'])) | {s['title']}), None)
        if relation:
            descriptions = [relation]
    for name in subjects:
        if deck:
            selected.extend(s for s in candidates if s.get('title') == name + '牌堆配置')
        if rules:
            options = [s for s in descriptions if s.get('title') == name]
            selected.extend(options)
    return selected if selected or deck else None


def _phrases(text, length=4):
    return {word[start:start + length] for word in re.findall(r'[\w\u4e00-\u9fff]+', text.lower())
            for start in range(len(word) - length + 1)}


def select_answer_sources(question, answer, candidates, selected_ids, card_names):
    if not candidates:
        return []
    if selected_ids == []:
        return []  # The response explicitly says it used no source.
    scoped = [s for s in candidates if s.get('evidence_type') == 'project_scope']
    if scoped:
        return unique_sources(scoped)
    card = _card_sources(question, answer, candidates, card_names)
    if card is not None:
        return unique_sources(card)
    if selected_ids is not None:
        by_id = {s['id']: s for s in candidates}
        return unique_sources(by_id[item] for item in selected_ids if item in by_id)

    # A provider may omit the footer. Fall back to named entities or actual
    # overlapping words in rules, never the first N retrieval hits.
    answer_phrases = _phrases(answer)
    question_phrases = _phrases(question, 2)
    selected = []
    for source in candidates:
        title, excerpt = source.get('title', ''), source.get('excerpt', '')
        if title.endswith('牌堆配置'):
            continue
        if len(title) >= 2 and title in answer and title in question:
            selected.append(source)
        elif len(answer_phrases & _phrases(excerpt)) >= 2 and len(question_phrases & _phrases(excerpt, 2)) >= 2:
            selected.append(source)
    return unique_sources(selected)
