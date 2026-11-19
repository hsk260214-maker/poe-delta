"""3.30 살덩이(Viscera) 거래소 정체성. data/viscera.json(PoEDB 공식 거래소 링크 기준)의 단계별 행을 쓴다."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from data import resource_path
from itemmodel import VISCERA_CLASSES as CLASSES

CATEGORY = "Viscera"
# 한글 복사본 이름 앞의 단계 표기. 원문으로 확인한 단계만 둔다(일반·여왕은 확인 전).
TIER_PREFIX = {"Low": "하위", "High": "상위"}
TIER_LABEL = {"Low": "하위", "Med": "일반", "High": "상위", "Queen": "여왕"}
# 단계별 대표 1개를 카카오 거래소 브라우저 링크로 확인하면 그 단계 전체를 연다.
# 2026-11-19 머성: 하위 이글거리는 두개골(20~30)에서 하위 단계만 나오는 것을 확인.
# 2026-11-19 머성: 상위 이글거리는 두개골(처치 시 속성 획득 20~30)에서 상위 단계만 나오는 것을 확인.
# 2026-11-19 머성 결정: 여왕 단계는 매물이 없어 확인하지 못했지만 포함한다(이름 표기도 미확인).
VERIFIED_TIERS = frozenset({"Low", "High", "Queen"})


@dataclass(frozen=True)
class Viscera:
    name: str
    slot: str
    tier: str
    type_en: str
    stat_id: str
    low: int
    high: int
    skeleton: str
    value_index: int | None
    blocked: str

    @property
    def tier_label(self) -> str:
        return TIER_LABEL.get(self.tier, self.tier)


@lru_cache(maxsize=1)
def rows() -> tuple[Viscera, ...]:
    data = json.loads(resource_path("data/viscera.json").read_text(encoding="utf-8"))
    return tuple(Viscera(r["name"], r["slot"], r["tier"], r["type_en"], r["stat"],
                         r["low"], r["high"], r["skeleton"], r["value_index"], r["blocked"]) for r in data["rows"])


def find(copied: str, skeletons: set[str]) -> Viscera | None:
    exact = next((row for row in rows() if row.tier in TIER_PREFIX
                  and f"{TIER_PREFIX[row.tier]} {row.name}" == copied), None)
    if exact:
        return exact
    # 여왕 단계는 이름 표기를 모른다. 상위와 옵션 문구가 같으므로 하위·상위 표기가 아닌 이름에서
    # 여왕 단계 문구가 정확히 일치할 때만 여왕으로 본다.
    prefix = copied.split(" ", 1)[0]
    return next((row for row in rows() if row.tier == "Queen" and not row.blocked
                 and (copied == row.name or (copied.endswith(" " + row.name)
                                              and prefix not in TIER_PREFIX.values()))
                 and row.skeleton in skeletons), None)
