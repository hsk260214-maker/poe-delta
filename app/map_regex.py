"""Offline bilingual stash search using bundled regex fragments."""
from collections.abc import Sequence
from dataclasses import dataclass
import json

from data import resource_path


LIMIT = 250
CLIPBOARD_MIME = "application/x-poe-delta-map-regex"
Patterns = dict[str, list[tuple[str, str]]]


def load_patterns(catalog: list[dict]) -> Patterns:
    keys = {row["key"] for row in catalog}
    try:
        rows = json.loads(resource_path("data/map_regex_fragments.json").read_text(encoding="utf-8"))
        return {key: [(ko, en) for ko, en in pairs] for key, pairs in rows.items() if key in keys}
    except (OSError, ValueError, TypeError, AttributeError):
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


def build(selected: Sequence[str], catalog: list[dict], patterns: Patterns, language: str = "ko") -> Result:
    if not catalog:
        return Result(issue="지도 옵션 목록 파일이 없어요.")
    if not selected:
        return Result(issue="피하려는 지도 옵션을 골라 주세요.")
    if not patterns:
        return Result(issue="앱에 내장된 지도 정규식 데이터를 읽을 수 없어요.")
    labels = {row["key"]: row["ko"] for row in catalog}
    unsupported = set(selected) - patterns.keys()
    if unsupported:
        names = ", ".join(labels.get(key, key) for key in sorted(unsupported))
        return Result(issue=f"정규식이 지원되지 않는 옵션: {names}")
    column = 1 if language == "en" else 0
    terms: dict[str, None] = {}
    for key in selected:
        for pair in patterns[key]:
            term = pair[column]
            terms.pop(term, None)
            terms[term] = None
    return fit('"!' + "|".join(terms) + '"')
