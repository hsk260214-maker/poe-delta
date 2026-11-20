"""검증된 같은 종류·ID의 양의 정수 옵션만 합친다."""
import re
from collections import defaultdict
from dataclasses import replace

from trade import resistance
from trade.stats import NUMBER, index, option_gate

VERIFIED = frozenset()
# 2026-11-20 머성 결정: 실검증을 건너뛰고 조건을 갖춘 모든 (종류, ID)에 합산을 켠다.
OPEN_ALL = True
KINDS = frozenset({"explicit", "implicit", "crafted", "fractured", "enchant"})
POSITIVE_INTEGER = re.compile(r"\+?[0-9]+")


def allowed(kind, stat_id):
    return OPEN_ALL or (kind, stat_id) in VERIFIED


def can_switch(row):
    other = {"explicit": "fractured", "fractured": "explicit"}.get(row.kind)
    return bool(row.match.alternate_id and (not row.sources or allowed(other, row.match.alternate_id)))


def _roll_span(row, lang, category):
    roll = row.match.rolls[0]
    candidates = [number for number in NUMBER.finditer(row.text) if number[0] == roll]
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    # 줄에 같은 고정 숫자가 있으면, 같은 stat에서 실제로 캡처되는 위치만 사용한다.
    matcher = index().ko if lang == "ko" else index()
    probe = "987654321"
    found = []
    for number in candidates:
        start, stop = number.span()
        sample = row.text[:start] + probe + row.text[stop:]
        result = matcher.resolve(sample, row.kind, category)
        if (result.id, result.ref, result.rolls) == (row.match.id, row.match.ref, (probe,)):
            found.append(number)
    return found[0] if len(found) == 1 else None


def apply(rows, ratio, default_minimum, *, lang, category):
    if not OPEN_ALL and not VERIFIED:
        return rows
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        m = row.match
        key = (row.kind, m.id)
        if (not allowed(*key) or row.kind not in KINDS or not m.id or m.ids
                or len(m.rolls) != 1 or not POSITIVE_INTEGER.fullmatch(m.rolls[0]) or int(m.rolls[0]) <= 0
                or m.invert or m.inverted or m.negate or m.value is not None
                or not row.combinable or row.detail or row.sources or option_gate(m, row.kind)
                or resistance.role(row) in ("elemental", "hybrid", "total")):
            continue
        groups[key].append(i)
    replacements, omitted = {}, set()
    for positions in groups.values():
        first, *rest = positions
        row = rows[first]
        if not rest or any((rows[i].checked, rows[i].match.alternate_id) !=
                           (row.checked, row.match.alternate_id) for i in rest):
            continue
        span = _roll_span(row, lang, category)
        if span is None:
            continue
        total = sum(int(rows[i].match.rolls[0]) for i in positions)
        value = f"+{total}" if span[0].startswith("+") else str(total)
        start, stop = span.span()
        badge = "일반" if row.badge == "explicit" else row.badge
        replacements[first] = replace(
            row, text=row.text[:start] + value + row.text[stop:], badge=f"{badge} · 합산",
            match=replace(row.match, rolls=(value,)), minimum=default_minimum(str(total), ratio),
            sources=tuple(rows[i].text for i in positions),
        )
        omitted.update(rest)
    return [replacements.get(i, row) for i, row in enumerate(rows) if i not in omitted] if omitted else rows
