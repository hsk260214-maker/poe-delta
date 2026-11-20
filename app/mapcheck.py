"""지도 Ctrl+C → 비선호(위험) 옵션 확인.

옵션 목록은 data/map_mods.json (tools/build_map_mods.py 로 RePoE 에서 만듦: 일반 지도 · 17티어 · 메이븐 초대장).
티어마다 수치만 다른 옵션은 수치를 '#' 로 바꾼 골격(key)이 같아서 하나로 묶임 → 하나만 골라도 모든 티어에 걸림.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from data import resource_path

SEP = "--------"
MAP_CLASSES = {"지도", "Maps"}
_RANGE = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*\)")
_NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")
_TAG = re.compile(r"\s*\((?:implicit|crafted|fractured|enchant|augmented|unmet|scourge|crucible)\)\s*$", re.I)
_MARK = re.compile(r"\[([^\]|]+)\|([^\]]+)\]")
_MARK1 = re.compile(r"\[([^\]|]+)\]")
_UNSCALABLE = re.compile(r"\s*[—-]+\s*(변경이 불가능한 값|Unscalable Value)\s*$", re.I)
TIER_KO = {"map": "일반", "maven": "메이븐", "t17": "17티어"}


def skel(s: str) -> str:
    """tools/build_map_mods.py 의 skel 과 같은 규칙 (범위·수치 → '#', 부호 무시, 소문자)."""
    s = _MARK1.sub(r"\1", _MARK.sub(r"\2", s)).strip()
    s = re.sub(r"(?<=\d)" + _RANGE.pattern, "", s)  # 고급 설명(Ctrl+Alt+C): 86(70-89) → 86
    s = _RANGE.sub("#", s)
    s = _NUM.sub("#", s)
    s = re.sub(r"[+-]#", "#", s)
    return re.sub(r"\s+", " ", s).strip().lower()


_CAT: list[dict] | None = None
_BY_SK: dict[str, dict] | None = None


def catalog() -> list[dict]:
    """[{key, en, ko, ko_sk, tiers}] — 파일이 없으면 빈 목록."""
    global _CAT, _BY_SK
    if _CAT is None:
        try:
            rows = json.loads(resource_path("data/map_mods.json").read_text(encoding="utf-8"))["lines"]
            if not isinstance(rows, list) or any(
                not isinstance(row, dict)
                or not all(isinstance(row.get(key), str) and row[key] for key in ("key", "ko", "en"))
                or not isinstance(row.get("ko_sk", ""), str)
                or not isinstance(row.get("tiers"), list)
                or not all(tier in TIER_KO for tier in row["tiers"])
                for row in rows
            ):
                raise ValueError("잘못된 지도 옵션 목록")
            _CAT = rows
        except (OSError, ValueError, KeyError, TypeError):
            _CAT = []
        _BY_SK = {}
        for e in _CAT:
            _BY_SK[e["key"]] = e
            if e.get("ko_sk"):
                _BY_SK.setdefault(e["ko_sk"], e)
    return _CAT


def entry_for(line: str) -> dict | None:
    catalog()
    return (_BY_SK or {}).get(skel(_TAG.sub("", line)))


@dataclass
class MapInfo:
    name: str
    base: str
    rarity: str
    tier: int | None
    unidentified: bool
    corrupted: bool
    lines: list[str] = field(default_factory=list)  # 옵션 줄 (원문)


def is_map(text: str) -> bool:
    first = (text or "").replace("\r", "").lstrip().split("\n", 1)[0]
    head, _, cls = first.partition(":")
    return head.strip() in ("Item Class", "아이템 종류") and cls.strip() in MAP_CLASSES


def parse_map(text: str) -> MapInfo | None:
    if not is_map(text) or SEP not in text:
        return None
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    rarity = lines[1].partition(":")[2].strip() if len(lines) > 1 and ":" in lines[1] else ""
    names = []
    i = 2
    while i < len(lines) and lines[i] != SEP:
        if lines[i]:
            names.append(lines[i])
        i += 1
    name = names[0] if names else ""
    base = names[-1] if names else ""
    tier = None
    unid = corrupted = False
    mods: list[str] = []
    for ln in lines[i:]:
        if not ln or ln == SEP or ln.startswith("{"):
            continue  # 고급 설명의 { 접두어 속성 부여 … } 머리줄
        if "지도 장치" in ln or "Map Device" in ln:
            continue  # 아이템 설명문
        ln = _UNSCALABLE.sub("", ln)
        if ln in ("미확인", "Unidentified"):
            unid = True
            continue
        if ln in ("타락", "Corrupted"):
            corrupted = True
            continue
        k, sep, v = ln.partition(": ")
        if sep and k in ("지도 등급", "Map Tier"):
            try:
                tier = int(re.sub(r"\D", "", v) or 0) or None
            except ValueError:
                pass
            continue
        if sep and len(k) <= 20:
            continue  # 속성 줄 (아이템 수량: +80% 등)
        mods.append(_TAG.sub("", ln))
    if tier is None:  # 새 형식: 베이스 이름에 '지도 (10등급)' / 'Map (Tier 10)'
        mt = re.search(r"\((\d+)\s*등급\)|\(Tier\s*(\d+)\)", base, re.I)
        if mt:
            tier = int(mt.group(1) or mt.group(2))
    return MapInfo(name, base, rarity, tier, unid, corrupted, mods)


def check(info: MapInfo, avoid: set[str]) -> list[tuple[dict, str]]:
    """지도의 옵션 줄 중 비선호(avoid: key 집합)에 걸린 것 [(옵션 목록 항목, 지도에 적힌 줄)]."""
    out = []
    for ln in info.lines:
        e = entry_for(ln)
        if e is not None and e["key"] in avoid:
            out.append((e, ln))
    return out
