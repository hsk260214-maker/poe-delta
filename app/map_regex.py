"""Offline bilingual stash search using bundled regex fragments."""
from collections.abc import Sequence
from dataclasses import dataclass
import json
import re

from data import resource_path


LIMIT = 250
CLIPBOARD_MIME = "application/x-poe-delta-map-regex"
Patterns = dict[str, list[tuple[str, str]]]
LIMIT_NAMES = {"drops": "아틀라스 획득물", "pack": "몬스터 무리 규모", "rarity": "아이템 희귀도",
               "currency": "화폐 더 많음", "map": "지도 더 많음"}
PREFIXES = dict(zip(LIMIT_NAMES, ("획득물:.*", "규모:.*", "희귀도:.*", "화폐 더 많음: .", "지도 더 많음: .")))
CATALOG_UNAVAILABLE = "지도 옵션 목록을 읽을 수 없어요."
FRAGMENTS_UNAVAILABLE = "앱에 내장된 지도 정규식 데이터를 읽을 수 없어요."
PREFERENCE_ISSUES = {"missing": "해당 옵션을 놓칠 수 있음", "collision": "다른 옵션도 검색됨",
                     "unverified": "검증 자료 없음"}


def load_patterns(catalog: list[dict]) -> Patterns:
    keys = {row["key"] for row in catalog}
    try:
        rows = json.loads(resource_path("data/map_regex_fragments.json").read_text(encoding="utf-8"))
        patterns = {}
        for key, pairs in rows.items():
            if not isinstance(pairs, list) or not pairs or not all(
                isinstance(pair, list) and len(pair) == 2 and all(isinstance(term, str) and term for term in pair)
                for pair in pairs
            ):
                return {}
            if key in keys:
                patterns[key] = [tuple(pair) for pair in pairs]
        return patterns
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def load_preference_audit(language: str) -> dict:
    try:
        entries = json.loads(resource_path("data/map_regex_preference_audit.json").read_text(encoding="utf-8"))[language]
        return entries if isinstance(entries, dict) else {}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


@dataclass(frozen=True)
class Result:
    text: str = ""
    length: int = 0
    issue: str = ""


def fit(text: str) -> Result:
    length = len(text)
    if length > LIMIT:
        return Result(length=length, issue=f"{LIMIT}자를 {length - LIMIT}자 초과했어요. 옵션을 줄여 주세요.")
    return Result(text=text, length=length)


def regex_calc(n: int) -> str:
    """참고 사이트 fnRegexCalc의 지원 범위(10~999)."""
    if not 10 <= n <= 999:
        raise ValueError("10~999만 지원합니다")
    h, tail = divmod(n, 100)
    t, o = divmod(tail, 10)
    if h:
        upper = [] if h == 9 else ["[2-9].." if h == 1 else f"[{h + 1}-9].."]
        if not t and not o:
            terms = ["1..", *upper] if h == 1 else ["9.." if h == 9 else f"[{h}-9].."]
        elif not o:
            terms = [f"{h}[{t}-9].", *upper]
        else:
            terms = [f"{h}{t}[{o}-9]"]
            if t < 9:
                terms.append(f"{h}[{t + 1}-9].")
            terms.extend(upper)
    else:
        if not o:
            terms = ["9." if t == 9 else f"[{t}-9]."]
        else:
            terms = [f"{t}9" if o == 9 else f"{t}[{o}-9]"]
            if t < 9:
                terms.append("9." if t == 8 else f"[{t + 1}-9].")
        terms.append("[1-9]..")
    return "(" + "|".join(terms) + ")%"


def build(selected: Sequence[str], catalog: list[dict], patterns: Patterns, language: str = "ko",
          *, wanted: Sequence[str] = (), mode="any", limits=None, limit_mode="or") -> Result:
    if not catalog:
        return Result(issue=CATALOG_UNAVAILABLE)
    if not patterns:
        return Result(issue=FRAGMENTS_UNAVAILABLE)
    limits = limits or {}
    numeric = {}
    for key in LIMIT_NAMES:
        value = limits.get(key, "").strip()
        if not value:
            continue
        significant = value.lstrip("0")
        if not re.fullmatch(r"[0-9]+", value) or not 2 <= len(significant) <= 3:
            return Result(issue=f"{LIMIT_NAMES[key]}: 10~999 사이의 정수를 입력해 주세요.")
        numeric[key] = int(significant)
    if language == "en" and numeric:
        return Result(issue="3.30 영문 지도 원문 확인 전에는 영문 수치 조건을 지원하지 않아요.")
    if not (selected or wanted or numeric):
        return Result(issue="지도 옵션을 고르거나 수치 조건을 입력해 주세요.")
    labels = {row["key"]: row["ko"] for row in catalog}
    unsupported = (set(selected) | set(wanted)) - patterns.keys()
    if unsupported:
        names = ", ".join(labels.get(key, key) for key in sorted(unsupported))
        return Result(issue=f"정규식이 지원되지 않는 옵션: {names}")
    column = 1 if language == "en" else 0
    wants = [list(dict.fromkeys(pair[column] for pair in patterns[key])) for key in wanted]
    if wanted:
        audit = load_preference_audit("en" if column else "ko")
        failures = []
        for key, terms in zip(wanted, wants):
            entry = audit.get(key)
            reasons = entry[1] if (
                isinstance(entry, list) and len(entry) == 2 and entry[0] == terms
                and isinstance(entry[1], list) and all(reason in ("missing", "collision") for reason in entry[1])
            ) else ["unverified"]
            if reasons:
                failures.append(f"{labels.get(key, key)} ({', '.join(PREFERENCE_ISSUES[reason] for reason in reasons)})")
        if failures:
            return Result(issue="선호로 복사할 수 없는 옵션: " + ", ".join(failures))
    if wants and mode != "all":
        wants = [dict.fromkeys(term for group in wants for term in group)]
    parts = ['"' + "|".join(group) + '"' for group in wants]
    terms: dict[str, None] = {}
    for key in selected:
        for pair in patterns[key]:
            term = pair[column]
            terms.pop(term, None)
            terms[term] = None
    if terms:
        parts.append('"!' + "|".join(terms) + '"')
    numeric = {key: PREFIXES[key] + regex_calc(value) for key, value in numeric.items()}
    parts.extend(f'"{numeric[key]}"' for key in ("drops", "pack", "rarity") if key in numeric)
    extras = [numeric[key] for key in ("currency", "map") if key in numeric]
    if extras:
        parts.extend(f'"{part}"' for part in (extras if limit_mode == "and" else ["|".join(extras)]))
    return fit(" ".join(parts))
