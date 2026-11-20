"""Offline bilingual stash search using bundled regex fragments."""
from collections.abc import Sequence
from dataclasses import dataclass
import json
import re

from data import resource_path


LIMIT = 250
CLIPBOARD_MIME = "application/x-poe-delta-map-regex"
Patterns = dict[str, list[tuple[str | None, str | None]]]
LIMIT_NAMES = {"drops": "아틀라스 획득물", "pack": "몬스터 무리 규모", "rarity": "아이템 희귀도",
               "currency": "화폐 더 많음", "map": "지도 더 많음"}
PREFIXES = dict(zip(LIMIT_NAMES, ("획득물:.*", "규모:.*", "희귀도:.*", "화폐 더 많음: .", "지도 더 많음: .")))
CATALOG_UNAVAILABLE = "지도 옵션 목록을 읽을 수 없어요."
FRAGMENTS_UNAVAILABLE = "앱에 내장된 지도 정규식 데이터를 읽을 수 없어요."


def load_patterns(catalog: list[dict]) -> Patterns:
    keys = {row["key"] for row in catalog}
    try:
        rows = json.loads(resource_path("data/map_regex_fragments.json").read_text(encoding="utf-8"))["fragments"]
        patterns = {}
        for key, pair in rows.items():
            if not isinstance(pair, list) or len(pair) != 2 or not all(
                term is None or (isinstance(term, str) and term) for term in pair
            ):
                return {}
            if key in keys:
                patterns[key] = [tuple(pair)]
        return patterns
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
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
    column = 1 if language == "en" else 0
    terms_by_key = {key: list(dict.fromkeys(pair[column] for pair in patterns.get(key, ()) if pair[column]))
                    for key in (*selected, *wanted)}
    unsupported = [key for key, terms in terms_by_key.items() if not terms]
    if unsupported:
        names = ", ".join(labels.get(key, key) for key in sorted(unsupported))
        return Result(issue=f"선택한 언어에서 모든 등급에 맞고 다른 옵션과 겹치지 않는 정규식을 찾지 못했어요: {names}")
    wants = [terms_by_key[key] for key in wanted]
    if wants and mode != "all":
        wants = [dict.fromkeys(term for group in wants for term in group)]
    parts = ['"' + "|".join(group) + '"' for group in wants]
    terms: dict[str, None] = {}
    for key in selected:
        for term in terms_by_key[key]:
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
