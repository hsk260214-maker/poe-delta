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
from itemmodel import CORRUPT_FLAGS, EATER_FLAGS, EXARCH_FLAGS, ITEM_LEVEL_KEYS, SEP, ItemModel, badge, mod_en, parse
from trade.config import OFFICIAL, validate_server
from trade import heist, items
from trade.stats import Match, index

WEAPONS = {"One Hand Sword", "Thrusting One Hand Sword", "One Hand Axe", "One Hand Mace",
           "Sceptre", "Claw", "Dagger", "Rune Dagger", "Wand", "Two Hand Sword", "Two Hand Axe",
           "Two Hand Mace", "Bow", "Staff", "Warstaff", "Fishing Rod"}
ARMOUR = {"Helmet", "Body Armour", "Gloves", "Boots", "Shield"}
EXTRA_CLASSES = {"Jewels": "Jewel", "주얼": "Jewel", "Abyss Jewels": "Abyss Jewel",
                 "어비스 주얼": "Abyss Jewel", "심연 주얼": "Abyss Jewel",
                 "Fishing Rods": "Fishing Rod", "낚싯대": "Fishing Rod"}
GEAR = WEAPONS | ARMOUR | {"Ring", "Amulet", "Belt", "Quiver", "Jewel", "Abyss Jewel"}
SUPPORTED = GEAR | heist.CATEGORIES.keys()
FORBIDDEN_TOME = "Forbidden Tome"
TOME_COPY_NAMES = {"ko": ("성역 연구", "금지된 책"), "en": ("Sanctum Research", FORBIDDEN_TOME)}
NUMBERS = re.compile(r"[+-]?\d+(?:\.\d+)?")
MONSTER_LEVEL_KEYS = ("몬스터 레벨:", "Monster Level:")
FASTER_ATTACKS_KO = re.compile(r"장착된 젬에 ([1-9][0-9]*)레벨 공격 속도 증가( 보조)? 보조 효과 적용")
FASTER_ATTACKS_EN = re.compile(r"Socketed Gems are Supported by Level ([1-9][0-9]*) \u200b?Faster Attacks( Support)?")
INFLUENCE_LABELS = {"Shaper": "쉐이퍼", "Elder": "엘더", "Crusader": "십자군",
                    "Redeemer": "대속자", "Hunter": "사냥꾼", "Warlord": "전쟁군주"}


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
    influences: tuple[str, ...] = ()
    eldritch_sources: tuple[str, ...] = ()
    identity: items.Identity | None = None
    blocked_reason: str = ""
    equipment_category: str = ""
    heist: heist.Heist | None = None

    @property
    def can_filter_ilvl(self) -> bool:
        return self.supported and self.ilvl > 0

    @property
    def monster_level(self) -> int | None:
        if not self.supported or not self.identity or self.identity.apt_category != "Map" or not self.model:
            return None
        lines = (*self.model.head, *(mod.text for mod in self.model.mods))
        levels = {line.partition(":")[2].strip() for line in lines if line.startswith(MONSTER_LEVEL_KEYS)}
        if len(levels) == 1:
            value = next(iter(levels))
            if re.fullmatch(r"[1-9][0-9]*", value):
                return int(value)
        return None

    @property
    def message(self) -> str:
        return self.blocked_reason or f"이 아이템은 아직 시세 검색을 지원하지 않습니다 (종류: {self.class_label})"


@dataclass
class StatCondition:
    text: str
    kind: str
    match: Match
    checked: bool = False
    minimum: float | None = None
    maximum: float | None = None
    badge: str = ""

    def switch_kind(self) -> None:
        if self.kind not in ("explicit", "fractured") or not self.match.alternate_id:
            return
        self.kind = "fractured" if self.kind == "explicit" else "explicit"
        self.badge = "분열" if self.kind == "fractured" else "explicit"
        self.match = Match(self.match.alternate_id, self.match.invert, "", self.match.id)


def item_info(model: ItemModel | None, server: str = OFFICIAL) -> TradeItem:
    info = TradeItem(model)
    if model is None:
        return info
    validate_server(server, model.lang)
    info.class_label = field(model.head, ("Item Class:", "아이템 종류:"))
    cls = heist.CLASSES.get(info.class_label, CLASS_NAMES.get(info.class_label, EXTRA_CLASSES.get(info.class_label, "")))
    info.category = "WEAPON" if cls in WEAPONS else "ARMOUR" if cls in ARMOUR else cls
    info.rarity = field(model.head, ("Rarity:", "아이템 희귀도:"))
    info.rarity = ko2en.RARITY.get(info.rarity, info.rarity)
    info.base, info.name = model.base, model.name
    legacy = cls in GEAR and info.rarity == "Unique"
    if legacy and model.lang == "ko" and server == OFFICIAL:
        info.base = ko2en.translate_base(model.base) or ""
        if info.rarity == "Unique":
            translated = parse(ko2en.translate_item("\n".join(model.head) + "\n" + SEP).text)
            info.name = translated.name if translated else ""
            if re.search("[가-힣]", info.name):
                info.name = ""
    ilvl = field(model.head, ITEM_LEVEL_KEYS)
    info.ilvl = int(ilvl) if ilvl.isdigit() else 0
    if info.rarity == "Currency" and (info.class_label, model.base) == TOME_COPY_NAMES.get(model.lang):
        info.category = FORBIDDEN_TOME
        info.base = FORBIDDEN_TOME if server == OFFICIAL else TOME_COPY_NAMES["ko"][1]
        info.name = ""
        info.supported = True
        return info
    sockets = field(model.head, property_keys("Sockets"))
    info.links = max((len(group.split("-")) for group in sockets.split()), default=0)
    info.corrupted = any(flag in model.flags for flag in CORRUPT_FLAGS)
    flags = {ko2en.FLAGS.get(flag, flag) for flag in model.flags}
    info.influences = tuple(name for name in INFLUENCE_LABELS if f"{name} Item" in flags)
    info.eldritch_sources = tuple(label for aliases, label in (
        (EXARCH_FLAGS, "작열의 총주교"), (EATER_FLAGS, "세계 포식자"),
    ) if flags.intersection(aliases))
    info.supported = bool(cls in SUPPORTED and info.rarity in ("Rare", "Unique") and info.base
                          and (info.rarity != "Unique" or info.name)
                          and not {"Unidentified", "미확인"}.intersection(model.flags))
    if cls in heist.CATEGORIES:
        info.supported = False
        try:
            info.identity = items.resolve_heist(model, cls, info.rarity, server)
            info.base, info.name = info.identity.base, info.identity.name
            if info.rarity != "Unique":
                info.heist = heist.read(model.head, model.lang, cls)
                if cls == heist.CONTRACT and not info.heist.job:
                    raise ValueError("강탈 계약의 필요 직업 또는 레벨을 확인할 수 없습니다")
                if cls == heist.BLUEPRINT:
                    if not info.heist.wings:
                        raise ValueError("도면의 공개·전체 구역 수를 확인할 수 없습니다")
                    if any(c.kind == "enchant" and not c.match.id for c in conditions(info)):
                        raise ValueError("도면 인챈트를 거래소 옵션과 맞추지 못했습니다")
                    if not index().enchant_count_id:
                        raise ValueError("도면 인챈트 개수 ID를 확인할 수 없습니다")
            info.supported = True
        except ValueError as error:
            info.blocked_reason = str(error)
        return info
    if not legacy:
        label = ko2en._dict().classes.get(info.class_label, info.class_label) if model.lang == "ko" else info.class_label
        category = ("Map" if label == "Maps" else "Flask" if label in items.FLASK_CLASSES
                    else "Gem" if label in items.GEM_CLASSES else "")
        equipment = cls in GEAR and info.rarity in ("Normal", "Magic", "Rare")
        if equipment:
            category = ("One-Handed Sword" if cls == "Thrusting One Hand Sword" else
                        cls.replace("One Hand ", "One-Handed ").replace("Two Hand ", "Two-Handed "))
        if category:
            try:
                identity = items.resolve(model, category, info.rarity, server, equipment=equipment)
                info.identity = None if equipment and info.rarity == "Rare" else identity
                info.base, info.name = identity.base, identity.name
                if equipment:
                    info.equipment_category = items.EQUIPMENT_TRADE_IDS.get(identity.apt_category, "")
                info.blocked_reason = items.blocked(identity, info.rarity)
                info.supported = not info.blocked_reason
            except ValueError as error:
                if equipment and info.rarity == "Rare" and isinstance(error, items.BaseNotFound):
                    if model.lang == "ko" and server == OFFICIAL:
                        info.base = ko2en.translate_base(model.base) or ""
                    info.supported = info.supported and bool(info.base)
                    if not info.supported:
                        info.blocked_reason = str(error)
                else:
                    info.blocked_reason = str(error)
                    info.supported = False
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


def heist_conditions(info: TradeItem) -> list[StatCondition]:
    data = info.heist
    if data is None:
        return []
    rows = []
    if info.category == heist.CONTRACT:
        rows.append(StatCondition(data.job_text or "필요 직업", "heist_job",
                                  Match("heist_" + data.job, reason="") if data.job else Match(reason=info.message),
                                  bool(data.job), data.job_level))
        if data.priceless:
            rows.append(StatCondition("목표물 가치: " + heist.PRICELESS["ko"], "heist_option",
                                      Match("heist_objective_value", reason=""), True))
    elif data.wings:
        for label, key, count in zip(("공개 구역", "전체 구역"), ("heist_wings", "heist_max_wings"), data.wings):
            rows.append(StatCondition(label, "heist_range", Match(key, reason=""), True, count, count))
        if not any(mod.kind == "enchant" for mod in info.model.mods) and index().enchant_count_id:
            rows.append(StatCondition("인챈트 없음", "heist_not", Match(index().enchant_count_id, reason=""), True))
    if data.area is not None and heist.area_enabled(info.category):
        rows.append(StatCondition("지역 레벨", "heist_area", Match("area_level", reason=""), False, data.area))
    return rows


def _faster_attacks(text: str) -> tuple[str, int] | None:
    match = FASTER_ATTACKS_KO.fullmatch(text) or FASTER_ATTACKS_EN.fullmatch(text)
    if not match:
        return None
    level = int(match[1])
    suffix = " Support" if match[2] else ""
    return f"Socketed Gems are Supported by Level {level} \u200bFaster Attacks{suffix}", level


def conditions(info: TradeItem, ratio: float = 0.9) -> list[StatCondition]:
    if not info.model or info.category == FORBIDDEN_TOME:
        return []
    if info.identity and info.identity.gem_level is not None:
        return [
            StatCondition("젬 레벨", "gem_filter", Match("gem_level", reason=""), True,
                          info.identity.gem_level, badge="젬"),
            StatCondition("퀄리티 (%)", "gem_filter", Match("quality", reason=""), True,
                          info.identity.quality, badge="젬"),
        ]
    result = heist_conditions(info)
    for mod in info.model.mods:
        if (info.identity and info.identity.apt_category == "Map"
                and (mod.text.startswith(MONSTER_LEVEL_KEYS) or items.map_identity_id(info.model.lang, mod.text))):
            continue
        support = _faster_attacks(mod.text)
        english = support[0] if support else mod_en(info.model, mod)
        matched = index().match(english, mod.kind, info.category) if english else Match()
        if mod.kind == "implicit" and mod.sub == "eldritch":
            matched = Match(reason="총주교·포식자 옵션의 출처가 모호합니다")
        blueprint_enchant = info.heist is not None and info.category == heist.BLUEPRINT and mod.kind == "enchant"
        minimum = (support[1] if support else default_minimum(english, ratio)) if english and not blueprint_enchant else None
        result.append(StatCondition(mod.text, mod.kind, matched,
                                   bool(matched.id and (blueprint_enchant or (info.rarity == "Rare" and mod.kind in ("explicit", "fractured"))
                                                        or (info.rarity == "Magic" and mod.kind == "explicit"))),
                                   minimum,
                                   badge=badge(mod) or mod.kind))
    return result


def _gem_filters(identity: items.Identity, stats: list[StatCondition]) -> dict:
    rows = {row.match.id: row for row in stats if row.kind == "gem_filter"}
    filters = {}
    for key, default, floor in (("gem_level", identity.gem_level, 1), ("quality", identity.quality, 0)):
        if key not in rows:
            filters[key] = {"min": default}
            continue
        row = rows[key]
        if not row.checked:
            continue
        bounds = {}
        for bound, value in (("min", row.minimum), ("max", row.maximum)):
            if value is None:
                continue
            if not math.isfinite(value) or value < floor or int(value) != value:
                raise ValueError(f"{row.text}: {floor} 이상의 정수를 입력하세요")
            bounds[bound] = int(value)
        if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
            raise ValueError(f"{row.text}: 최소값은 최대값보다 클 수 없습니다")
        if bounds:
            filters[key] = bounds
    return filters


CATEGORY_LABELS = {
    "accessory.amulet": "목걸이", "accessory.belt": "허리띠", "accessory.ring": "반지",
    "armour.boots": "장화", "armour.chest": "갑옷", "armour.gloves": "장갑",
    "armour.helmet": "투구", "armour.quiver": "화살통", "armour.shield": "방패",
    "weapon.bow": "활", "weapon.claw": "클로", "weapon.dagger": "단검",
    "weapon.rod": "낚싯대", "weapon.oneaxe": "한손 도끼", "weapon.onemace": "한손 철퇴",
    "weapon.onesword": "한손 검", "weapon.runedagger": "룬 단검", "weapon.sceptre": "셉터",
    "weapon.staff": "지팡이", "weapon.twoaxe": "양손 도끼", "weapon.twomace": "양손 철퇴",
    "weapon.twosword": "양손 검", "weapon.wand": "마법봉", "weapon.warstaff": "전쟁지팡이",
    "jewel": "주얼", "jewel.abyss": "어비스 주얼", "jewel.cluster": "성단 주얼",
    "heistmission.contract": "계약", "heistmission.blueprint": "도면",
}


@dataclass(frozen=True)
class SearchTarget:
    base: str | None = None
    name: str | None = None
    category: str | None = None
    discriminator: str | None = None

    @property
    def label(self) -> str:
        if self.category:
            return CATEGORY_LABELS.get(self.category, self.category)
        return " · ".join(part for part in (self.name, self.base) if part) or "검색할 수 없음"


def search_target(info: TradeItem, exact_base: bool | None = None) -> SearchTarget:
    if not info.supported:
        return SearchTarget()
    if info.heist:
        if exact_base is None:
            exact_base = info.category == heist.BLUEPRINT
        if not exact_base:
            return SearchTarget(category=heist.CATEGORIES[info.category])
    if info.equipment_category and not exact_base:
        return SearchTarget(category=info.equipment_category)
    return SearchTarget(info.base, info.name if info.rarity == "Unique" else None,
                        discriminator=info.identity.discriminator if info.identity else None)


def build_query(info: TradeItem, stats: list[StatCondition], *, ilvl: bool = False,
                links: bool = True, corrupted: bool = True,
                influences: set[str] | None = None, exact_base: bool | None = None,
                monster_level: bool = False) -> dict:
    if not info.supported:
        raise ValueError(info.message)
    filters = {}
    if ilvl and info.can_filter_ilvl:
        filters.setdefault("misc_filters", {"filters": {}})["filters"]["ilvl"] = {"min": info.ilvl}
    if corrupted and info.category != FORBIDDEN_TOME:
        filters.setdefault("misc_filters", {"filters": {}})["filters"]["corrupted"] = {"option": "true" if info.corrupted else "false"}
    if links and info.links >= 5:
        filters["socket_filters"] = {"filters": {"links": {"min": info.links}}}
    identity = info.identity
    if identity:
        if info.heist:
            filters["type_filters"] = {"filters": {"rarity": {"option": "nonunique"}}}
        elif info.rarity in ("Normal", "Magic"):
            filters["type_filters"] = {"filters": {"rarity": {"option": info.rarity.lower()}}}
        elif identity.gem_level is None and info.rarity == "Rare":
            filters["type_filters"] = {"filters": {"rarity": {"option": "nonunique"}}}
        if identity.apt_category == "Map":
            map_filters = {}
            if identity.tier is not None:
                map_filters["map_tier"] = {"min": identity.tier, "max": identity.tier}
            if monster_level and (area_level := info.monster_level) is not None:
                map_filters["area_level"] = {"min": area_level, "max": area_level}
            map_filters["map_blighted"] = {"option": "false"}
            filters["map_filters"] = {"filters": map_filters}
        if identity.gem_level is not None:
            gem_filters = _gem_filters(identity, stats)
            if gem_filters:
                filters.setdefault("misc_filters", {"filters": {}})["filters"].update(gem_filters)
    selected = []
    not_enchanted = []
    for condition in stats:
        if condition.kind == "gem_filter" or not condition.checked or not condition.match.id:
            continue
        if info.heist and condition.kind.startswith("heist_"):
            key = condition.match.id
            if condition.kind == "heist_not":
                not_enchanted.append({"id": key, "value": {}, "disabled": False})
                continue
            if condition.kind == "heist_area" and not heist.area_enabled(info.category):
                continue
            group = "map_filters" if condition.kind == "heist_area" else "heist_filters"
            if condition.kind == "heist_option":
                value = {"option": "priceless"}
            else:
                bounds = {"min": condition.minimum}
                if condition.kind != "heist_job":
                    bounds["max"] = condition.maximum
                if any(not math.isfinite(n) or n < 0 or int(n) != n for n in bounds.values() if n is not None):
                    raise ValueError("강탈 조건은 0 이상의 정수로 입력하세요")
                value = {bound: int(n) for bound, n in bounds.items() if n is not None}
                if condition.kind == "heist_job" and not value.get("min"):
                    raise ValueError("필요 직업의 최소 레벨을 입력하세요")
            if value:
                filters.setdefault(group, {"filters": {}})["filters"][key] = value
            continue
        values = {}
        for key, value in (("min", condition.minimum), ("max", condition.maximum)):
            if value is not None:
                if not math.isfinite(value):
                    raise ValueError("최소·최대값은 유한한 숫자로 입력하세요")
                values[("max" if key == "min" else "min") if condition.match.invert else key] = -value if condition.match.invert else value
        selected.append({"id": condition.match.id, **({"value": values} if values else {})})
    if info.influences:
        ids = index().influences
        selected.extend({"id": ids[name]} for name in info.influences if influences is None or name in influences)
    if identity:
        selected.extend({"id": stat_id} for stat_id in identity.map_ids)
    target = search_target(info, exact_base)
    query = {"status": {"option": "securable"}, "type": target.base,
             "stats": [{"type": "and", "filters": selected}], "filters": filters}
    if not_enchanted:
        query["stats"].append({"type": "not", "filters": not_enchanted})
    if target.category:
        del query["type"]
        kinds = filters.setdefault("type_filters", {"filters": {}})["filters"]
        kinds["category"] = {"option": target.category}
        if not info.heist and info.rarity == "Rare":
            kinds["rarity"] = {"option": "nonunique"}
    if target.name is not None:
        query["name"] = target.name
    if target.discriminator:
        for key in ("name", "type"):
            if key in query:
                query[key] = {"option": query[key], "discriminator": target.discriminator}
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
