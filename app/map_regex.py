"""Offline bilingual stash search from the user's POE Regex KR exports."""
from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from mapcheck import skel


LIMIT = 250
CLIPBOARD_MIME = "application/x-poe-delta-map-regex"
FILE_STEM = "poeregexkr-poe1-map-options"
Patterns = dict[str, list[tuple[str, str]]]


def load_patterns(catalog: list[dict], directory: Path | None = None) -> Patterns:
    if directory is None:
        if getattr(sys, "frozen", False):
            from paths import LOCAL

            directory = LOCAL
        else:
            directory = Path(__file__).resolve().parents[2] / "design"
    by_text = {(row["key"], row["ko_sk"]): row["key"] for row in catalog}
    out: Patterns = {}
    try:
        source = json.loads((directory / f"{FILE_STEM}.json").read_text(encoding="utf-8"))["groups"]
        english = json.loads((directory / f"{FILE_STEM}-en.json").read_text(encoding="utf-8"))["groups"]
        for kind in ("prefix", "suffix"):
            ko_rows = source[kind]["rows"]
            en_rows = english[kind]["rows"]
            by_number = {row["no"]: row for row in en_rows}
            if len(ko_rows) != len(en_rows) or len(by_number) != len(en_rows):
                return {}
            for row in ko_rows:
                en = by_number[row["no"]]
                if (en["lv"], en["mod"], en["regex"]) != (row["lv"], row["engMod"], row["engRegex"]):
                    return {}
                key = by_text.get((skel(en["mod"]), skel(row["mod"])))
                if key:
                    pair = (row["regex"], en["regex"])
                    if all(term and not any(char in term for char in '"\r\n') for term in pair):
                        out.setdefault(key, []).append(pair)
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return out


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
        return Result(issue="POE Regex KR 한글·영문 옵션 파일을 불러오지 못했어요.")
    labels = {row["key"]: row["ko"] for row in catalog}
    unsupported = set(selected) - patterns.keys()
    if unsupported:
        names = ", ".join(labels.get(key, key) for key in sorted(unsupported))
        return Result(issue=f"사이트 옵션과 정확히 연결되지 않은 항목: {names}")
    column = 1 if language == "en" else 0
    terms: dict[str, None] = {}
    for key in selected:
        for pair in patterns[key]:
            term = pair[column]
            terms.pop(term, None)
            terms[term] = None
    return fit('"!' + "|".join(terms) + '"')
