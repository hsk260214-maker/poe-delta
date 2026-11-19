"""고정 APT 원소 저항 ref를 기반으로 합산 범위를 결정한다."""
from decimal import Decimal, ROUND_FLOOR

# 2026-11-19 머성: 총 원소 저항 최소 66 목걸이 링크에서 화염·냉기 등 다른 배분의 매물도 함께 나오는 것을 확인.
BROWSER_VERIFIED = True
ROW_KIND = "elemental_resistance_total"
INCLUDED = "총 원소 저항에 포함"
HYBRID_HINT = "체크하면 원소 저항까지 포함한 원래 혼합 옵션을 추가로 요구합니다"
ELEMENTS = {
    "+#% to All Resistances": (3, True),
    "+#% to all Elemental Resistances": (3, False),
    "+#% to Fire Resistance": (1, False),
    "+#% to Cold Resistance": (1, False),
    "+#% to Lightning Resistance": (1, False),
    "+#% to Fire and Lightning Resistances": (2, False),
    "+#% to Fire and Cold Resistances": (2, False),
    "+#% to Cold and Lightning Resistances": (2, False),
    "+#% to Fire and Chaos Resistances": (1, True),
    "+#% to Cold and Chaos Resistances": (1, True),
    "+#% to Lightning and Chaos Resistances": (1, True),
}


def role(row):
    if row.kind == ROW_KIND:
        return "total"
    match = row.match
    if match.id and match.ref in ELEMENTS:
        return "hybrid" if ELEMENTS[match.ref][1] else "elemental"
    if not match.id and (ELEMENTS.keys() & match.candidate_refs
                         or (not match.candidate_refs and "저항" in row.text)):
        return "unresolved"
    return ""


def copied_total(rows):
    total = Decimal(0)
    first = None
    for pos, row in enumerate(rows):
        source = role(row)
        if source == "unresolved":
            return None, None, f"총합을 계산할 수 없는 저항: {row.text}"
        if source not in ("elemental", "hybrid"):
            continue
        rolls = row.match.rolls
        if len(rolls) != 1:
            return None, None, f"복사한 저항 수치를 확인할 수 없습니다: {row.text}"
        first = pos if first is None else first
        amount = Decimal(rolls[0])
        total += amount * ELEMENTS[row.match.ref][0] * (-1 if row.match.negate else 1)
    return first, total, ""


def minimum(total, ratio):
    return int((total * Decimal(str(ratio))).to_integral_value(rounding=ROUND_FLOOR))


def excluded(row, total_mode):
    return role(row) == ("elemental" if total_mode else "total")
