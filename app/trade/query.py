"""아이템 머리·옵션 조건과 거래소 JSON 사이의 변환."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from statistics import median

import ko2en
from itemcheck import CLASS_NAMES
from itemmodel import (CORRUPT_FLAGS, EATER_FLAGS, EXARCH_FLAGS, ITEM_LEVEL_KEYS, SEP, ItemModel, badge, mod_en,
                       parse, skeleton)
from trade.config import KAKAO, OFFICIAL, validate_server
from trade import combine, heist, items, resistance, templates, unique_mods, viscera
from trade.stats import Match, index, option_gate

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
SUPPORTED_BY_KO = re.compile(r"장착된 젬에 ([1-9][0-9]*)레벨 (.+) 보조 효과 적용")
SUPPORTED_BY_EN = re.compile(r"Socketed Gems are Supported by Level ([1-9][0-9]*) \u200b?(.+)", re.I)
GRANTS_KO = re.compile(r"([1-9][0-9]*)레벨 (.+) 스킬 사용 가능")
GRANTS_EN = re.compile(r"Grants Level ([1-9][0-9]*) \u200b?(.+?)(?: Skill)?")
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
    viscera: viscera.Viscera | None = None
    template: str = ""
    unidentified_unique: bool = False
    unique_options: tuple[str, ...] = ()
    map_fragment_ref: str = ""

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
    detail: str = ""
    sources: tuple[str, ...] = ()
    combinable: bool = True

    def switch_kind(self) -> None:
        if self.kind not in ("explicit", "fractured") or not combine.can_switch(self):
            return
        self.kind = "fractured" if self.kind == "explicit" else "explicit"
        self.badge = ("분열" if self.kind == "fractured" else "일반") + " · 합산" if self.sources else (
            "분열" if self.kind == "fractured" else "explicit")
        self.match = replace(self.match, id=self.match.alternate_id, alternate_id=self.match.id)


def _normalized_class(label: str) -> str:
    return heist.CLASSES.get(label, CLASS_NAMES.get(label, EXTRA_CLASSES.get(label, "")))


def _typed_category(model: ItemModel, class_label: str) -> str:
    label = ko2en._dict().classes.get(class_label, class_label) if model.lang == "ko" else class_label
    return ("Map" if label == "Maps" else "Flask" if label in items.FLASK_CLASSES
            else "Gem" if label in items.GEM_CLASSES else "")


def _is_tome(model: ItemModel, class_label: str) -> bool:
    return (class_label, model.base) == TOME_COPY_NAMES.get(model.lang)


def owns_search_category(model: ItemModel, *, server: str = OFFICIAL, league: str = "") -> bool:
    """등급이나 검색 가능 여부가 아니라 기존 검색 분기의 소유 여부를 판정한다."""
    label = field(model.head, ("Item Class:", "아이템 종류:"))
    return bool(_normalized_class(label) in SUPPORTED or label in viscera.CLASSES
                or _is_tome(model, label) or _typed_category(model, label)
                or items.resolve_spectre(model, server, league))


def item_info(model: ItemModel | None, server: str = OFFICIAL, *, league: str = "") -> TradeItem:
    info = TradeItem(model)
    if model is None:
        return info
    validate_server(server, model.lang)
    info.class_label = field(model.head, ("Item Class:", "아이템 종류:"))
    cls = _normalized_class(info.class_label)
    info.category = "WEAPON" if cls in WEAPONS else "ARMOUR" if cls in ARMOUR else cls
    info.rarity = field(model.head, ("Rarity:", "아이템 희귀도:"))
    info.rarity = ko2en.RARITY.get(info.rarity, info.rarity)
    info.base, info.name = model.base, model.name
    if league and not owns_search_category(model) and (spectre := items.resolve_spectre(model, server, league)):
        info.identity = spectre
        info.category = items.SPECTRE_CATEGORY
        info.base, info.name = spectre.base, ""
        info.supported = True
        return info
    if cls in GEAR and info.rarity == "Unique" and items.UNIDENTIFIED_FLAGS.intersection(
        (*model.head, *model.flags),
    ):
        info.unidentified_unique = True
        category = ("One-Handed Sword" if cls == "Thrusting One Hand Sword" else
                    cls.replace("One Hand ", "One-Handed ").replace("Two Hand ", "Two-Handed "))
        try:
            info.unique_options, level = items.unidentified_unique_options(model, category)
            info.ilvl = level or 0
        except ValueError as error:
            info.blocked_reason = str(error)
        return info
    legacy = cls in GEAR and info.rarity == "Unique"
    if legacy:
        info.template = templates.EQUIPMENT
    if legacy and model.lang == "ko" and server == OFFICIAL:
        info.base = ko2en.translate_base(model.base) or ""
        if info.rarity == "Unique":
            translated = parse(ko2en.translate_item("\n".join(model.head) + "\n" + SEP).text)
            info.name = translated.name if translated else ""
            if re.search("[가-힣]", info.name):
                info.name = ""
    ilvl = field(model.head, ITEM_LEVEL_KEYS)
    info.ilvl = int(ilvl) if ilvl.isdigit() else 0
    if model.lang == "ko" and info.class_label == items.MAP_FRAGMENT_CLASS:
        info.category = items.MAP_FRAGMENT_CLASS
        info.map_fragment_ref = items.map_fragment_ref(model)
        info.supported = bool(info.map_fragment_ref and server == KAKAO and league == items.INVITATION_LEAGUE)
        if not info.supported:
            info.blocked_reason = ("절규하는 초대는 한국어 카카오 Covens에서만 검색할 수 있습니다"
                                   if info.map_fragment_ref else "검색 가능한 일반 절규하는 초대를 정확히 식별할 수 없습니다")
        return info
    if info.rarity == "Currency" and _is_tome(model, info.class_label):
        info.template = templates.OTHER
        info.category = FORBIDDEN_TOME
        info.base = FORBIDDEN_TOME if server == OFFICIAL else TOME_COPY_NAMES["ko"][1]
        info.name = ""
        info.supported = True
        return info
    if info.class_label in viscera.CLASSES:
        info.template = templates.OTHER
        info.category = viscera.CATEGORY
        row = viscera.find(model.base, {skeleton(mod.text) for mod in model.mods})
        if row is None or row.slot not in model.head:
            info.blocked_reason = "아직 지원하지 않는 살덩이입니다"
            return info
        info.viscera = row
        info.base = row.type_en if server == OFFICIAL else row.name
        info.name = ""
        values = [NUMBERS.findall(mod.text) for mod in model.mods if skeleton(mod.text) == row.skeleton]
        if row.blocked:
            info.blocked_reason = f"이 살덩이는 검색할 수 없습니다: {row.blocked}"
        elif (len(values) != 1 or len(values[0]) <= row.value_index
              or not row.low <= float(values[0][row.value_index]) <= row.high):
            info.blocked_reason = "살덩이 단계를 확인할 수 없습니다"
        elif row.tier not in viscera.VERIFIED_TIERS:
            info.blocked_reason = "아직 확인되지 않은 살덩이 종류입니다"
        else:
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
        info.template = templates.AREA_LEVEL
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
        category = _typed_category(model, info.class_label)
        equipment = cls in GEAR and info.rarity in ("Normal", "Magic", "Rare")
        if equipment:
            info.template = templates.EQUIPMENT
            category = ("One-Handed Sword" if cls == "Thrusting One Hand Sword" else
                        cls.replace("One Hand ", "One-Handed ").replace("Two Hand ", "Two-Handed "))
        else:
            info.template = {"Map": templates.AREA_LEVEL, "Gem": templates.GEM, "Flask": templates.FLASK}.get(category, "")
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


@lru_cache(maxsize=1)
def _gem_names() -> dict[str, str]:
    return {row[2]: row[1] for row in items.catalog()["items"]["ko"] if row[0] == "GEM"}


def _granted_gem(text: str) -> tuple[str, int] | None:
    """보조 젬·스킬 부여 줄을 거래소 영문 형식(레벨 수치 포함)으로 바꾼다."""
    gems = _gem_names()
    if match := SUPPORTED_BY_KO.fullmatch(text):
        level, name = match.groups()
        # 'X 보조 보조 효과'는 젬 이름 'X 보조' 그대로, 'X 보조 효과'는 무작위 보조 형식(Support 없음)이다.
        english = gems.get(name) or gems.get(name + " 보조", "").removesuffix(" Support")
        line = f"Socketed Gems are Supported by Level {level} \u200b{english}" if english else ""
    elif match := SUPPORTED_BY_EN.fullmatch(text):
        level, name = match.groups()
        line = f"Socketed Gems are Supported by Level {level} \u200b{name}"
    elif match := GRANTS_KO.fullmatch(text):
        level, name = match.groups()
        line = f"Grants Level {level} \u200b{gems[name]}" if name in gems else ""
    elif match := GRANTS_EN.fullmatch(text):
        level, name = match.groups()
        line = f"Grants Level {level} \u200b{name}"
    else:
        return None
    return (line, int(level)) if line else None


def _option_english(info: TradeItem, mod, support: tuple[str, int] | None) -> str | None:
    english = support[0] if support else mod_en(info.model, mod)
    if (support and info.model.lang == "ko" and info.rarity != "Unique"
            and info.category in GEAR | {"ARMOUR", "WEAPON"} and GRANTS_KO.fullmatch(mod.text)):
        gear_line = english.replace("\u200b", "") + " Skill"
        # 같은 종류의 매처가 모호하면 기존 부여 형식으로 우회하지 않는다.
        preferred = index().resolve(gear_line, mod.kind, info.category)
        if preferred.id or preferred.ambiguous or preferred.reason != Match().reason:
            return gear_line
    return english


def conditions(info: TradeItem, ratio: float = 0.9) -> list[StatCondition]:
    if not info.model or info.category in (FORBIDDEN_TOME, items.SPECTRE_CATEGORY, items.MAP_FRAGMENT_CLASS):
        return []
    if info.viscera:
        rows = []
        for mod in info.model.mods:
            if skeleton(mod.text) == info.viscera.skeleton:
                rows.append(StatCondition(mod.text, "viscera_tier", Match(info.viscera.stat_id, reason=""), True,
                                          info.viscera.low, info.viscera.high, badge="필수"))
                continue
            english = mod_en(info.model, mod)
            matched = index().match(english, mod.kind, viscera.CATEGORY) if english else Match()
            rows.append(StatCondition(mod.text, mod.kind, matched, False,
                                      default_minimum(english, ratio) if english else None,
                                      badge=badge(mod) or mod.kind, combinable=False))
        return rows
    if info.identity and info.identity.gem_level is not None:
        return [
            StatCondition("젬 레벨", "gem_filter", Match("gem_level", reason=""), True,
                          info.identity.gem_level, badge="젬"),
            StatCondition("퀄리티 (%)", "gem_filter", Match("quality", reason=""), True,
                          info.identity.quality, badge="젬"),
        ]
    result = heist_conditions(info)
    unique = unique_mods.unique_ref(info.model, info.rarity)
    mods = info.model.mods
    skip = None
    for pos, mod in enumerate(mods):
        if pos == skip:
            continue
        if unique == unique_mods.MONARCH and (mod.copy_parts or pos + 1 < len(mods)):
            first, following = mod.copy_parts or (mod, mods[pos + 1])
            paired = unique_mods.living_pair(info.model, first, following)
            if paired is not None:
                if paired.id:
                    result.append(StatCondition(first.text, first.kind, paired, True, badge=badge(first) or first.kind,
                                                detail=first.text + "\n" + following.text))
                else:
                    for line in (first, following):
                        result.append(StatCondition(line.text, line.kind, paired, badge=badge(line) or line.kind))
                if not mod.copy_parts:
                    skip = pos + 1
                continue
        if (info.identity and info.identity.apt_category == "Map"
                and (mod.text.startswith(MONSTER_LEVEL_KEYS) or items.map_identity_id(info.model.lang, mod.text))):
            continue
        stat_index = index()
        support = _granted_gem(mod.text)
        english = _option_english(info, mod, support)
        matched = (stat_index.bilingual(mod.text, english, mod.kind, info.category) if info.model.lang == "ko"
                   else stat_index.match(english, mod.kind, info.category) if english else Match())
        if unique == unique_mods.MONARCH and matched.id.startswith(unique_mods.MONARCH_PREFIX):
            matched = Match(reason="허용된 소환수 블록을 확인할 수 없습니다", candidate_refs=matched.candidate_refs)
        if mod.kind == "implicit" and mod.sub == "eldritch":
            matched = Match(reason="총주교·포식자 옵션의 출처가 모호합니다",
                            candidate_refs=matched.candidate_refs)
        blueprint_enchant = info.heist is not None and info.category == heist.BLUEPRINT and mod.kind == "enchant"
        minimum = None
        if matched.id and not blueprint_enchant:
            if support:
                minimum = support[1]
            elif matched.value is not None:
                minimum = matched.value
            elif not re.search(r"\b(reduced|less)\b", english or ""):
                minimum = default_minimum(" ".join(matched.rolls), ratio)
                if (minimum is not None and matched.rolls in (("1",), ("+1",))
                        and not (matched.invert or matched.inverted or matched.negate or matched.ids or info.heist)):
                    minimum = max(minimum, 1)
        destiny = (unique == unique_mods.DESTINY and mod.kind == "explicit" and not matched.ids
                   and (matched.ref, matched.id) in unique_mods.destiny_pool())
        result.append(StatCondition(mod.text, mod.kind, matched,
                                   bool(matched.id and (blueprint_enchant or (info.rarity == "Rare" and mod.kind in ("explicit", "fractured"))
                                                        or (info.rarity == "Magic" and mod.kind == "explicit") or destiny)),
                                   minimum,
                                   badge=badge(mod) or mod.kind,
                                   combinable=not (support or GRANTS_KO.fullmatch(mod.text)
                                                   or info.heist or unique == unique_mods.DESTINY
                                                   or re.search(r"\b(reduced|less)\b", english or ""))))
    return result


def resistance_rows(info, rows, ratio=0.9):
    if (not resistance.BROWSER_VERIFIED or not info.supported
            or info.category not in GEAR | {"ARMOUR", "WEAPON"} or not index().total_resistance_id):
        return rows, ""
    first, total, reason = resistance.copied_total(rows)
    if first is None:
        return rows, reason
    row = StatCondition(f"총 원소 저항 {total:+g}%", resistance.ROW_KIND,
                        Match(index().total_resistance_id, reason=""), True,
                        resistance.minimum(total, ratio), badge="합산")
    return [*rows[:first], row, *rows[first:]], ""


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


def _viscera_filter(info: TradeItem, stats: list[StatCondition]) -> dict:
    row = info.viscera
    condition = next((c for c in stats if c.kind == "viscera_tier"), None)
    bounds = []
    for value, edge in ((condition.minimum if condition else None, row.low),
                        (condition.maximum if condition else None, row.high)):
        value = edge if value is None else value
        if not math.isfinite(value) or int(value) != value or not row.low <= value <= row.high:
            raise ValueError(f"단계 범위는 {row.low}~{row.high} 사이의 정수로 입력하세요")
        bounds.append(int(value))
    if bounds[0] > bounds[1]:
        raise ValueError("최소값은 최대값보다 클 수 없습니다")
    return {"id": row.stat_id, "value": {"min": bounds[0], "max": bounds[1]}}


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
    if not info.supported and not info.viscera:
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


# APT v3.30.102: Config.ts's poeWebApi explicitly routes en→Official and ko→Kakao.
# Its pathofexile-trade.ts encodes name/type, identified.option = String(false),
# ilvl min/max and passes the body as POST JSON. That does not establish browser prefill.
_UNIDENTIFIED_API_PATHS = {(OFFICIAL, "en", "api"), (KAKAO, "ko", "api")}


def exact_unique_level(text: str) -> int:
    value = text.strip()
    if not re.fullmatch(r"[0-9]+", value) or not (level := int(value)):
        raise ValueError("아이템 레벨을 양의 정수로 입력하세요")
    return level


def build_unidentified_unique_query(info: TradeItem, name: str, level_text: str, server: str, mode: str) -> dict:
    if not info.unidentified_unique or not info.model or info.blocked_reason:
        raise ValueError(info.message)
    if not info.unique_options:
        raise ValueError("이 베이스에 연결된 고유 이름이 없습니다")
    if name not in info.unique_options:
        raise ValueError("이 베이스의 고유 이름을 선택하세요")
    level = exact_unique_level(level_text)
    validate_server(server, info.model.lang)
    if (server, info.model.lang, mode) not in _UNIDENTIFIED_API_PATHS:
        raise ValueError("이 거래소·언어·모드의 미확인 고유 검색은 지원하지 않습니다")
    return {"query": {
        "status": {"option": "securable"}, "name": name, "type": info.model.base,
        "stats": [{"type": "and", "filters": []}],
        "filters": {"misc_filters": {"filters": {
            "identified": {"option": "false"}, "ilvl": {"min": level, "max": level},
        }}},
    }, "sort": {"price": "asc"}}


def build_query(info: TradeItem, stats: list[StatCondition], *, ilvl: bool = False,
                links: bool = True, corrupted: bool = True,
                influences: set[str] | None = None, exact_base: bool | None = None,
                monster_level: bool = False, total_resistance: bool = False) -> dict:
    if not info.supported:
        raise ValueError(info.message)
    if info.category == items.SPECTRE_CATEGORY:
        return {"query": {"status": {"option": "securable"}, "type": info.base}, "sort": {"price": "asc"}}
    if info.map_fragment_ref:
        query = {"status": {"option": "securable"}, "type": info.base}
        if ilvl and info.can_filter_ilvl:
            query["filters"] = {"misc_filters": {"filters": {"ilvl": {"min": info.ilvl}}}}
        return {"query": query, "sort": {"price": "asc"}}
    filters = {}
    if ilvl and info.can_filter_ilvl:
        filters.setdefault("misc_filters", {"filters": {}})["filters"]["ilvl"] = {"min": info.ilvl}
    if corrupted and info.category not in (FORBIDDEN_TOME, viscera.CATEGORY):
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
    total_mode = (total_resistance and resistance.BROWSER_VERIFIED and info.category in GEAR | {"ARMOUR", "WEAPON"}
                  and any(row.kind == resistance.ROW_KIND and row.match.id == index().total_resistance_id
                          for row in stats)
                  and resistance.copied_total(stats)[0] is not None)
    count_groups = []
    not_enchanted = []
    monarch = unique_mods.unique_ref(info.model, info.rarity) == unique_mods.MONARCH
    for condition in stats:
        if resistance.excluded(condition, total_mode):
            continue
        if condition.kind in ("gem_filter", "viscera_tier") or not condition.checked or not condition.match.id:
            continue
        if monarch and condition.match.id.startswith(unique_mods.MONARCH_PREFIX):
            if (unique_mods.LIVING_BROWSER_VERIFIED and condition.match.id == unique_mods.LIVING_ID
                    and condition.match.ref == unique_mods.LIVING_REF and condition.detail):
                selected.append({"id": condition.match.id})
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
        if option_gate(condition.match, condition.kind):
            continue
        values = {}
        for key, value in (("min", condition.minimum), ("max", condition.maximum)):
            if value is not None:
                if not math.isfinite(value):
                    raise ValueError("최소·최대값은 유한한 숫자로 입력하세요")
                values[("max" if key == "min" else "min") if condition.match.invert else key] = -value if condition.match.invert else value
        if condition.match.ids:
            members = []
            roll = condition.match.value
            if roll is None and condition.match.rolls:
                nums = tuple(map(float, condition.match.rolls))
                roll = sum(nums[:2]) / min(len(nums), 2)
                if condition.match.negate:
                    roll = -roll
            for stat_id in condition.match.ids:
                prefix, brace, raw_id = stat_id.partition("}")
                member_values = values
                if prefix == "{empty_if_100" and roll == 100:
                    member_values = {}
                elif prefix == "{div_by_100":
                    member_values = {key: bound / 100 for key, bound in values.items()}
                members.append({"id": raw_id if brace else stat_id, "value": member_values, "disabled": False})
            count_groups.append({"type": "count", "value": {"min": 1}, "disabled": False, "filters": members})
        else:
            selected.append({"id": condition.match.id, **({"value": values} if values else {})})
    if info.viscera:
        selected.append(_viscera_filter(info, stats))
    if info.influences:
        ids = index().influences
        selected.extend({"id": ids[name]} for name in info.influences if influences is None or name in influences)
    if identity:
        selected.extend({"id": stat_id} for stat_id in identity.map_ids)
    target = search_target(info, exact_base)
    query = {"status": {"option": "securable"}, "type": target.base,
             "stats": [{"type": "and", "filters": selected}, *count_groups], "filters": filters}
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


def exact_invitation_results(entries, requested_ids):
    indexed = {}
    duplicates = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(key := entry.get("id"), str) or key not in requested_ids:
            continue
        if key in indexed:
            duplicates.add(key)
        indexed[key] = entry
    matched = []
    for key in dict.fromkeys(requested_ids):
        if key in duplicates or key not in indexed:
            continue
        entry = indexed[key]
        item = entry.get("item")
        if (isinstance(item, dict) and item.get("baseType") == item.get("typeLine") == items.INVITATION_NAME
                and type(item.get("frameType")) is int and item["frameType"] == 0):
            matched.append(entry)
    return matched


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
