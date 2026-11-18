"""저장소의 고정 APT 데이터만 사용하는 stat 매칭."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from data import resource_path
from itemmodel import skeleton


@dataclass(frozen=True)
class Match:
    id: str = ""
    invert: bool = False
    reason: str = "거래소 옵션과 맞추지 못함"
    alternate_id: str = ""


class StatIndex:
    def __init__(self, data: dict):
        self.entries = data["entries"]
        self.groups = data["groups"]
        self.influences = data["influences"]
        self.by_skeleton: dict[str, list[dict]] = {}
        self.by_group: dict[int, list[int]] = {}
        for i, entry in enumerate(self.entries):
            if entry["group"] is not None:
                self.by_group.setdefault(entry["group"], []).append(i)
        for matcher in data["matchers"]:
            self.by_skeleton.setdefault(matcher["skeleton"], []).append(matcher)

    def match(self, text: str, kind: str, category: str) -> Match:
        if kind in ("scourge", "crucible"):
            return Match(reason="이번 버전은 미지원 종류")
        candidates = self.by_skeleton.get(skeleton(text), [])
        places = {("group", self.entries[m["entry"]]["group"])
                  if self.entries[m["entry"]]["group"] is not None else ("entry", m["entry"])
                  for m in candidates}
        if len(places) != 1:
            return Match(reason="후보가 여러 개" if places else "거래소 옵션과 맞추지 못함")
        place, number = next(iter(places))
        if place == "group":
            if self.groups[number]["strat"] != "select":
                return Match(reason="이번 버전은 미지원 옵션")
            entries = self.by_group[number]
            selected = [i for i in entries if self.entries[i]["test"] == category]
            if not selected:
                selected = [i for i in entries if self.entries[i]["test"] is None]
            if len(selected) != 1:
                return Match()
            number = selected[0]
        candidates = [m for m in candidates if m["entry"] == number]
        if not candidates or any(m["has_value"] for m in candidates):
            return Match()
        signs = {bool(self.entries[number]["inverted"]) ^ bool(m["negate"]) for m in candidates}
        ids = self.entries[number]["ids"].get(kind, [])
        if len(ids) != 1 or not ids[0].startswith(kind + ".") or len(signs) != 1:
            return Match(reason="후보가 여러 개" if len(ids) > 1 or len(signs) > 1 else "거래소 옵션과 맞추지 못함")
        other = {"explicit": "fractured", "fractured": "explicit"}.get(kind)
        alternate = self.entries[number]["ids"].get(other, []) if other else []
        alternate_id = alternate[0] if len(alternate) == 1 and alternate[0].startswith(other + ".") else ""
        return Match(ids[0], signs.pop(), "", alternate_id)


@lru_cache(maxsize=1)
def index() -> StatIndex:
    return StatIndex(json.loads(resource_path("data/trade_stats.json").read_text(encoding="utf-8")))
