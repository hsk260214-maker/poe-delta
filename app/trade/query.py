"""아이템 머리·옵션 조건과 거래소 JSON 사이의 변환."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from statistics import median

import ko2en
from itemcheck import CLASS_NAMES
from itemmodel import CORRUPT_FLAGS, ITEM_LEVEL_KEYS, SEP, ItemModel, mod_en, parse
from trade.config import OFFICIAL, validate_server
from trade.stats import Match, index

WEAPONS = {"One Hand Sword", "Thrusting One Hand Sword", "One Hand Axe", "One Hand Mace",
           "Sceptre", "Claw", "Dagger", "Rune Dagger", "Wand", "Two Hand Sword", "Two Hand Axe",
           "Two Hand Mace", "Bow", "Staff", "Warstaff", "Fishing Rod"}
ARMOUR = {"Helmet", "Body Armour", "Gloves", "Boots", "Shield"}
EXTRA_CLASSES = {"Jewels": "Jewel", "주얼": "Jewel", "Abyss Jewels": "Abyss Jewel",
                 "어비스 주얼": "Abyss Jewel", "심연 주얼": "Abyss Jewel",
                 "Fishing Rods": "Fishing Rod", "낚싯대": "Fishing Rod"}
SUPPORTED = WEAPONS | ARMOUR | {"Ring", "Amulet", "Belt", "Quiver", "Jewel", "Abyss Jewel"}
NUMBERS = re.compile(r"[+-]?\d+(?:\.\d+)?")


def field(head: list[str], keys: tuple[str, ...]) -> str:
    return next((line.partition(":")[2].strip() for line in head if line.startswith(keys)), "")


def property_keys(english: str) -> tuple[str, ...]:
    return (english + ":",) + tuple(k + ":" for k, v in ko2en.PROPS.items() if v == english)


@dataclass
class TradeItem:
    model: ItemModel | None
    class_label: str = "해석 실패"
    category: str = ""
    rarity: str = ""
    base: str = ""
    name: str = ""
    ilvl: int = 0
    links: int = 0
    corrupted: bool = False
    supported: bool = False

    @property
    def message(self) -> str:
        return f"이 아이템은 아직 시세 검색을 지원하지 않습니다 (종류: {self.class_label})"


@dataclass
class StatCondition:
    text: str
    kind: str
    match: Match
    checked: bool = False
    minimum: float | None = None
    maximum: float | None = None


def item_info(model: ItemModel | None, server: str = OFFICIAL) -> TradeItem:
    info = TradeItem(model)
    if model is None:
        return info
    validate_server(server, model.lang)
    info.class_label = field(model.head, ("Item Class:", "아이템 종류:"))
    cls = CLASS_NAMES.get(info.class_label, EXTRA_CLASSES.get(info.class_label, ""))
    info.category = "WEAPON" if cls in WEAPONS else "ARMOUR" if cls in ARMOUR else cls
    info.rarity = field(model.head, ("Rarity:", "아이템 희귀도:"))
    info.rarity = ko2en.RARITY.get(info.rarity, info.rarity)
    info.base, info.name = model.base, model.name
    if model.lang == "ko" and server == OFFICIAL:
        info.base = ko2en.translate_base(model.base) or ""
        if info.rarity == "Unique":
            translated = parse(ko2en.translate_item("\n".join(model.head) + "\n" + SEP).text)
            info.name = translated.name if translated else ""
            if re.search("[가-힣]", info.name):
                info.name = ""
    ilvl = field(model.head, ITEM_LEVEL_KEYS)
    info.ilvl = int(ilvl) if ilvl.isdigit() else 0
    sockets = field(model.head, property_keys("Sockets"))
    info.links = max((len(group.split("-")) for group in sockets.split()), default=0)
    info.corrupted = any(flag in model.flags for flag in CORRUPT_FLAGS)
    info.supported = bool(cls in SUPPORTED and info.rarity in ("Rare", "Unique") and info.base
                          and (info.rarity != "Unique" or info.name)
                          and not {"Unidentified", "미확인"}.intersection(model.flags))
    return info


def default_minimum(text: str, ratio: float = 0.9) -> float | None:
    numbers = NUMBERS.findall(text)
    if not numbers or len(numbers) > 2 or re.search(r"\b(reduced|less)\b", text, re.I):
        return None
    values = [Decimal(n) for n in numbers]
    if any(v <= 0 for v in values):
        return None
    value = sum(values) / len(values) * Decimal(str(ratio))
    quantum = Decimal("0.1") if any("." in n for n in numbers) else Decimal("1")
    rounded = value.quantize(quantum, rounding=ROUND_FLOOR)
    return int(rounded) if quantum == Decimal("1") else float(rounded)


def conditions(info: TradeItem, ratio: float = 0.9) -> list[StatCondition]:
    if not info.model:
        return []
    result = []
    for mod in info.model.mods:
        english = mod_en(info.model, mod)
        matched = index().match(english, mod.kind, info.category) if english else Match()
        result.append(StatCondition(mod.text, mod.kind, matched,
                                   bool(matched.id and info.rarity == "Rare" and mod.kind in ("explicit", "fractured")),
                                   default_minimum(english, ratio) if english else None))
    return result


def build_query(info: TradeItem, stats: list[StatCondition], *, ilvl: bool = False,
                links: bool = True, corrupted: bool = True) -> dict:
    if not info.supported:
        raise ValueError(info.message)
    filters = {}
    if ilvl and info.rarity == "Rare":
        filters.setdefault("misc_filters", {"filters": {}})["filters"]["ilvl"] = {"min": info.ilvl}
    if corrupted:
        filters.setdefault("misc_filters", {"filters": {}})["filters"]["corrupted"] = {"option": "true" if info.corrupted else "false"}
    if links and info.links >= 5:
        filters["socket_filters"] = {"filters": {"links": {"min": info.links}}}
    selected = []
    for condition in stats:
        if not condition.checked or not condition.match.id:
            continue
        values = {}
        for key, value in (("min", condition.minimum), ("max", condition.maximum)):
            if value is not None:
                if not math.isfinite(value):
                    raise ValueError("최소·최대값은 유한한 숫자로 입력하세요")
                values[("max" if key == "min" else "min") if condition.match.invert else key] = -value if condition.match.invert else value
        selected.append({"id": condition.match.id, **({"value": values} if values else {})})
    query = {"status": {"option": "securable"}, "type": info.base,
             "stats": [{"type": "and", "filters": selected}], "filters": filters}
    if info.rarity == "Unique":
        query["name"] = info.name
    return {"query": query, "sort": {"price": "asc"}}


def league_for(source: dict | None, saved: str) -> str:
    source = source or {}
    return (source.get("character", {}).get("league") or saved) if source.get("type") == "account" else saved


def result_rows(response: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = []
    for entry in response.get("result", [])[:20]:
        listing, item = entry.get("listing", {}), entry.get("item", {})
        price = listing.get("price") or {}
        indexed = listing.get("indexed", "")
        try:
            minutes = max(0, int((now - datetime.fromisoformat(indexed.replace("Z", "+00:00"))).total_seconds() // 60))
            age = f"{minutes}분 전"
        except (ValueError, TypeError):
            age = "알 수 없음"
        rows.append({"amount": price.get("amount"), "currency": price.get("currency", ""),
                     "seller": listing.get("account", {}).get("name", ""),
                     "age": age, "ilvl": item.get("ilvl", ""), "id": entry.get("id", "")})
    return rows


def summary(total: int, rows: list[dict]) -> str:
    priced = [r for r in rows[:10] if isinstance(r["amount"], (int, float)) and r["currency"]]
    if not priced:
        return f"전체 {total}개 · " + ("검색 결과가 없습니다" if total == 0 else "표시할 가격이 없습니다")
    counts = Counter(r["currency"] for r in priced)
    currency = counts.most_common(1)[0][0]
    amounts = [r["amount"] for r in priced if r["currency"] == currency]
    first = next((r for r in rows if isinstance(r["amount"], (int, float)) and r["currency"]), priced[0])
    mixed = " (가장 많은 화폐 기준)" if len(counts) > 1 else ""
    return f"전체 {total}개 · 최저가 {first['amount']:g} {first['currency']} · 상위 10개 중간값 {median(amounts):g} {currency}{mixed}"
