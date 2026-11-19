"""저장소의 고정 APT 데이터만 사용하는 stat 매칭."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from functools import lru_cache

from data import resource_path

# 번역 결과의 게임 표기 기호: [Blind] → Blind, [DamageFaster|Faster] → Faster
MARKUP = re.compile(r"\[(?:[^\]|]*\|)?([^\]|]+)\]")
NUMBER = re.compile(r"(?<![\d)])[+-]?\d+(?:\.\d+)?")
KEEP = (
    ((),), ((0,), ()), ((0, 1), (0,), (1,), ()),
    ((0, 1, 2), (1, 2), (0, 2), (0, 1), (2,), (1,), (0,)),
    ((0, 1, 2, 3), (1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2),
     (2, 3), (1, 3), (1, 2), (0, 3), (0, 2), (0, 1)),
)
R2 = {
    frozenset(pair) for pair in (
        ("2530372417", "1702195217"), ("561307714", "19803471"),
        ("2355741828", "3039589351"), ("1604736568", "1030153674"),
        ("3666934677", "57434274"), ("3023957681", "665823128"),
    )
}
R4 = {
    frozenset(("explicit.stat_654274615", "{empty_if_100}explicit.stat_338121249")),
    frozenset(("explicit.stat_2213584313", "{empty_if_100}explicit.stat_3967845372")),
}
# 2026-11-19 머성: 대표 링크 확인 — R2 인내 충전 하나당 공격 피해 막기 확률(투구),
# R4 명중 시 인화성 저주(반지)에서 해당 옵션만 나오는 것을 확인. R3·R5는 계속 닫는다.
BROWSER_VERIFIED = frozenset({"R2", "R4"})
RESISTANCE_COLLISIONS = {
    "화염 저항 #%": ("#% to Fire Resistance", "3372524247", "763311546"),
    "냉기 저항 #%": ("#% to Cold Resistance", "4220027924", "496075050"),
    "번개 저항 #%": ("#% to Lightning Resistance", "1671376347", "1942151132"),
}


def _normalize(text: str) -> str:
    text = MARKUP.sub(r"\1", text)
    return "\n".join(" ".join(line.split()) for line in text.replace("\u200b", "").splitlines()).strip()


def _variants(text):
    text = text.replace("()", "").replace("(...)", "")
    numbers = list(NUMBER.finditer(text))
    if len(numbers) >= len(KEEP):
        yield text, ()
        return
    for keep in KEEP[len(numbers)]:
        start, parts, rolls = 0, [], []
        for i, number in enumerate(numbers):
            parts.extend((text[start:number.start()], number[0] if i in keep else "#"))
            start = number.end()
            if i not in keep:
                rolls.append(number[0])
        parts.append(text[start:])
        yield "".join(parts), tuple(rolls)


@dataclass(frozen=True)
class Match:
    id: str = ""
    invert: bool = False
    reason: str = "거래소 옵션과 맞추지 못함"
    alternate_id: str = ""
    value: float | None = None
    ids: tuple[str, ...] = ()
    rolls: tuple[str, ...] = ()
    negate: bool = False
    inverted: bool = False
    ambiguous: bool = False
    ref: str = ""
    candidate_refs: frozenset[str] = frozenset()
    verified_korean_block_id: str = ""

    @property
    def meaning(self):
        # 고정 숫자는 현지 문구에서 이미 확인했다. 번역에서 생략되어도 전송할 값은 같다.
        return (frozenset(self.ids or (self.id,)), self.inverted, self.negate, self.value,
                tuple(float(n) for n in self.rolls))


def _count_rule(match: Match, kind: str) -> str:
    ids = frozenset(match.ids)
    prefix = kind + ".stat_"
    return ("R2" if kind in ("explicit", "crafted") and len(ids) == 2
            and all(i.startswith(prefix) for i in ids)
            and frozenset(i.removeprefix(prefix) for i in ids) in R2
            else "R4" if ids in R4 else "")


def option_gate(match: Match, kind: str) -> str:
    if match.verified_korean_block_id:
        if (kind != "explicit" or match.ids or match.id != match.verified_korean_block_id
                or match.id not in BLOCK_SUPPORTED_IDS or match.id not in BLOCK_BROWSER_VERIFIED):
            return "이 옵션 종류의 막기 ID는 아직 확인되지 않았습니다"
    if not match.ids:
        return ""
    rule = _count_rule(match, kind)
    if rule:
        return "" if rule in BROWSER_VERIFIED else "브라우저 확인 대기: " + rule
    return "이번 버전은 미지원 옵션"


def choose_match(korean: Match, english: Match) -> Match:
    if korean.ambiguous or english.ambiguous:
        return korean if korean.ambiguous else english
    if korean.id and english.id and korean.meaning != english.meaning:
        return Match(reason="한국어·번역 연결 불일치", ambiguous=True)
    return korean if korean.id else english


def _resistance_collision(text: str, english: str, kind: str, korean: Match, translated: Match) -> bool:
    if (kind not in ("explicit", "implicit") or korean.ambiguous or translated.ambiguous
            or len(korean.ids) != 2 or translated.ids or korean.meaning[1:] != translated.meaning[1:]):
        return False
    phrase = NUMBER.sub("#", _normalize(text))
    if phrase not in RESISTANCE_COLLISIONS:
        return False
    en_phrase, primary, other = RESISTANCE_COLLISIONS[phrase]
    prefix = kind + ".stat_"
    return (NUMBER.sub("#", _normalize(english)) == en_phrase and translated.id == prefix + primary
            and frozenset(korean.ids) == {prefix + primary, prefix + other})


@lru_cache(maxsize=1)
def _korean_aliases() -> dict:
    return json.loads(resource_path("data/ko_aliases.json").read_text(encoding="utf-8"))


BLOCK_MATCHERS = {
    "#%의 확률로 공격 피해를 막아냄": ("#% Chance to Block Attack Damage", "", "2530372417", "1702195217"),
    "공격 피해 막기 확률 #%": ("#% Chance to Block Attack Damage", "+", "1702195217", "2530372417"),
    "#%의 확률로 주문 피해를 막아냄": ("#% Chance to Block Spell Damage", "", "561307714", "19803471"),
    "주문 피해 막기 확률 #%": ("#% Chance to Block Spell Damage", "+", "19803471", "561307714"),
}
BLOCK_STAT_NUMBERS = frozenset(row[2] for row in BLOCK_MATCHERS.values())
BLOCK_SUPPORTED_IDS = frozenset({"explicit.stat_561307714", "explicit.stat_1702195217"})
# 2026-11-19 머성: 방패 주문 막기(min 13)·지팡이 공격 막기(min 18) 카카오 링크에서 해당 옵션 매물 확인.
# 같은 번호의 제작·고정·분열과 나머지 두 막기 번호는 확인하지 않아 계속 닫는다.
BLOCK_BROWSER_VERIFIED = frozenset({"explicit.stat_561307714", "explicit.stat_1702195217"})


def _korean_block_match(text, english, kind, korean, translated):
    for phrase, rolls in _variants(text):
        if phrase in BLOCK_MATCHERS:
            break
    else:
        if korean.id.removeprefix(kind + ".stat_") in BLOCK_STAT_NUMBERS:
            return Match(reason="한국어·번역 연결 불일치", ambiguous=True)
        return None
    en_phrase, ref_prefix, primary, other = BLOCK_MATCHERS[phrase]
    stat_id = "explicit.stat_" + primary
    if (kind == "explicit" and stat_id in BLOCK_SUPPORTED_IDS and stat_id in BLOCK_BROWSER_VERIFIED
            and not (korean.ambiguous or translated.ambiguous or korean.ids)
            and korean.id == stat_id and korean.ref == ref_prefix + en_phrase and korean.rolls == rolls
            and english and any(p == en_phrase for p, _ in _variants(_normalize(english)))
            and len(translated.ids) == 2 and frozenset(translated.ids) == {stat_id, "explicit.stat_" + other}
            and korean.invert == translated.invert and korean.meaning[1:] == translated.meaning[1:]):
        return replace(korean, verified_korean_block_id=stat_id)
    return Match(reason="한국어·번역 연결 불일치", ambiguous=True)


class StatIndex:
    def __init__(self, data: dict):
        self.entries = data["entries"]
        self.groups = data["groups"]
        self.influences = data.get("influences", {})
        self.enchant_count_id = data.get("enchant_count_id", "")
        self.total_resistance_id = data.get("total_resistance_id", "")
        self.ko = StatIndex(data["ko"]) if "ko" in data else None
        self.by_text: dict[str, list[dict]] = {}
        self.by_entry: dict[int, list[dict]] = {}
        self.by_group: dict[int, list[int]] = {}
        for i, entry in enumerate(self.entries):
            if entry["group"] is not None:
                self.by_group.setdefault(entry["group"], []).append(i)
        for matcher in data["matchers"]:
            self.by_entry.setdefault(matcher["entry"], []).append(matcher)
            for text in dict.fromkeys((matcher["string"], matcher.get("advanced"))):
                if isinstance(text, str):
                    self.by_text.setdefault(_normalize(text), []).append(matcher)

    def match(self, text: str, kind: str, category: str) -> Match:
        result = self.resolve(text, kind, category)
        reason = option_gate(result, kind)
        return Match(reason=reason, candidate_refs=result.candidate_refs) if reason else result

    def bilingual(self, text, english, kind, category):
        alias = _korean_aliases().get(text)
        korean = self.ko.resolve(alias["apt_ko"] if alias else text, kind, category)
        if alias and not english:
            english = alias["ref"]
        translated = self.resolve(english, kind, category) if english else Match()
        result = _korean_block_match(text, english, kind, korean, translated)
        if result is None:
            result = (translated if english and _resistance_collision(text, english, kind, korean, translated)
                      else choose_match(korean, translated))
        candidates = korean.candidate_refs | translated.candidate_refs
        if alias and not result.ambiguous and (
                result.ids or (kind, result.id, result.ref) != (alias["kind"], alias["id"], alias["ref"])):
            return Match(reason="검증된 한글 별칭의 종류·ID·ref가 일치하지 않습니다", candidate_refs=candidates)
        if _count_rule(result, kind) == "R2" and not (korean.ids and translated.ids):
            return Match(reason="한국어·번역 묶음 양쪽 확인이 필요합니다", candidate_refs=candidates)
        reason = option_gate(result, kind)
        return Match(reason=reason, candidate_refs=candidates) if reason else replace(result, candidate_refs=candidates)

    def resolve(self, text: str, kind: str, category: str) -> Match:
        if kind in ("scourge", "crucible"):
            return Match(reason="이번 버전은 미지원 종류")
        refs = set()
        for phrase, rolls in _variants(_normalize(text)):
            by_place = {}
            for matcher in self.by_text.get(phrase, ()):
                entry = matcher["entry"]
                if ref := self.entries[entry].get("ref"):
                    refs.add(ref)
                group = self.entries[entry]["group"]
                by_place.setdefault((group, None if group is not None else entry), []).append(matcher)
            results = []
            for (group, entry), candidates in by_place.items():
                result = self._resolve_place(group, entry, candidates, kind, category, rolls)
                if result.ambiguous:
                    return replace(result, candidate_refs=frozenset(refs))
                if result.id:
                    results.append(result)
            if len(results) > 1:
                return Match(reason="후보가 여러 개", ambiguous=True, candidate_refs=frozenset(refs))
            if results:
                return replace(results[0], candidate_refs=frozenset(refs))
        return Match(candidate_refs=frozenset(refs))

    def _resolve_place(self, group, entry, candidates, kind, category, rolls):
        by_entry = {}
        for matcher in candidates:
            by_entry.setdefault(matcher["entry"], []).append(matcher)
        ids_for = lambda i: self.entries[i]["ids"].get(kind, ())
        strategy = self.groups[group] if group is not None else {}
        members = self.by_group[group] if group is not None else [entry]
        traded = [i for i in members if ids_for(i)]
        if not traded:
            return Match()
        strat = strategy.get("strat")
        suffix = ()
        if strat == "select":
            chosen = [i for i in members if self.entries[i]["test"] == category]
            chosen = chosen or [i for i in members if self.entries[i]["test"] is None]
            if len(chosen) != 1:
                return Match(reason="부위로 옵션을 결정할 수 없습니다", ambiguous=True)
        elif len(traded) == 1:
            chosen = traded
        elif strat == "trivial-merge":
            chosen = [i for i in traded if i in by_entry]
        elif strat == "percent-merge":
            percent = members[strategy["kind"].index("percent")]
            value = members[strategy["kind"].index("value")]
            if any(m["value"] == 100 for m in by_entry.get(percent, ())):
                chosen = [percent]
                other = self.by_entry[value]
                prefix = "{empty_if_100}" if len(other) == 1 and "#" not in other[0]["string"] else "{div_by_100}"
                suffix = tuple(prefix + stat_id for stat_id in ids_for(value))
            else:
                chosen = [i for i in traded if i in by_entry]
                if len(chosen) > 1:
                    return Match(reason="후보가 여러 개", ambiguous=True)
        else:
            return Match(reason="이번 버전은 미지원 옵션", ambiguous=True)
        if not chosen or any(i not in by_entry or not ids_for(i) for i in chosen):
            return Match()
        signs = {(self.entries[i]["inverted"], m["negate"], m["value"])
                 for i in chosen for m in by_entry[i]}
        if len(signs) != 1:
            return Match(reason="후보가 여러 개", ambiguous=True)
        inverted, negate, fixed = signs.pop()
        ids = tuple(dict.fromkeys((*[stat_id for i in chosen for stat_id in ids_for(i)], *suffix)))
        if any(not i.split("}", 1)[-1].startswith(kind + ".") for i in ids):
            return Match(reason="이번 버전은 미지원 옵션", ambiguous=True)
        other = {"explicit": "fractured", "fractured": "explicit"}.get(kind)
        alternate = self.entries[chosen[0]]["ids"].get(other, []) if other and len(ids) == 1 else []
        alternate_id = alternate[0] if len(alternate) == 1 and alternate[0].startswith(other + ".") else ""
        refs = {self.entries[i].get("ref", "") for i in chosen}
        return Match(ids[0], inverted ^ negate, "", alternate_id, fixed if not rolls else None,
                     ids if len(ids) > 1 else (), rolls, negate, inverted,
                     ref=next(iter(refs)) if len(refs) == 1 else "")


@lru_cache(maxsize=1)
def index() -> StatIndex:
    return StatIndex(json.loads(resource_path("data/trade_stats.json").read_text(encoding="utf-8")))
