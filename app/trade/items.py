"""새 범위의 품목 정체성 및 출시 게이트. 로컬 APT 자료만 사용한다."""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import takewhile

from data import resource_path
from itemmodel import mod_en
from trade.config import OFFICIAL
from trade.stats import index

MAP_TIER = re.compile(r"\s*\((?:Tier\s+(\d+)|(\d+)\s*등급)\)", re.I)
VARIANT = re.compile(r"^(?:Synthesised|Foulborn|Vestigial|결합된|삿된|흔적(?:이 남은)?)\s")
UNKNOWN_MAP = re.compile(r"occupied by|influenced by|citadel|시타델|성채|점령|영향을 받|손에 넘어", re.I)
ORIGINATOR_MEMORIES_ID = "implicit.stat_2696470877"
REQUIREMENTS = {"Requirements:", "요구 사항:", "요구사항:"}
GUARDIAN_NAMES = {"Shaper Guardian Map", "쉐이퍼 수호자 지도", "Lair of the Hydra Map",
                  "Pit of the Chimera Map", "Maze of the Minotaur Map", "Forge of the Phoenix Map",
                  "히드라의 소굴 지도", "키메라의 구덩이 지도", "미노타우로스의 미로 지도", "불사조의 대장간 지도"}
MAP_BASES = {"Map", "Nightmare Map", "Vaal Temple Map"}
FLASK_CLASSES = {"Life Flasks", "Mana Flasks", "Hybrid Flasks", "Utility Flasks", "Critical Utility Flasks"}
GEM_CLASSES = {"Skill Gems", "Support Gems"}
EQUIPMENT_TRADE_IDS = {
    "Abyss Jewel": "jewel.abyss", "Amulet": "accessory.amulet", "Belt": "accessory.belt",
    "Body Armour": "armour.chest", "Boots": "armour.boots", "Bow": "weapon.bow",
    "Claw": "weapon.claw", "Cluster Jewel": "jewel.cluster", "Dagger": "weapon.dagger",
    "Fishing Rod": "weapon.rod", "Gloves": "armour.gloves", "Helmet": "armour.helmet",
    "Jewel": "jewel", "One-Handed Axe": "weapon.oneaxe", "One-Handed Mace": "weapon.onemace",
    "One-Handed Sword": "weapon.onesword", "Quiver": "armour.quiver", "Ring": "accessory.ring",
    "Rune Dagger": "weapon.runedagger", "Sceptre": "weapon.sceptre", "Shield": "armour.shield",
    "Staff": "weapon.staff", "Two-Handed Axe": "weapon.twoaxe", "Two-Handed Mace": "weapon.twomace",
    "Two-Handed Sword": "weapon.twosword", "Wand": "weapon.wand", "Warstaff": "weapon.warstaff",
}

# 값별 API·브라우저 증거가 모두 있어야 검색을 허용한다.
API_VERIFIED = frozenset({
    "normal",
    "implicit.stat_1792283443|1", "implicit.stat_1792283443|2",
    "implicit.stat_2563183002|1", "implicit.stat_2563183002|2",
    "implicit.stat_2563183002|3", "implicit.stat_2563183002|4",
    "implicit.stat_3624393862|1", "implicit.stat_3624393862|2",
    "implicit.stat_3624393862|3", "implicit.stat_3624393862|4",
})
# 2026-11-18 머성이 카카오 거래소(Standard) 브라우저 링크 11개로 확인: 전부 통과.
BROWSER_VERIFIED = frozenset({
    "normal",
    "implicit.stat_1792283443|1", "implicit.stat_1792283443|2",
    "implicit.stat_2563183002|1", "implicit.stat_2563183002|2",
    "implicit.stat_2563183002|3", "implicit.stat_2563183002|4",
    "implicit.stat_3624393862|1", "implicit.stat_3624393862|2",
    "implicit.stat_3624393862|3", "implicit.stat_3624393862|4",
})


@dataclass(frozen=True)
class Identity:
    base: str
    name: str = ""
    discriminator: str | None = None
    tier: int | None = None
    gem_level: int | None = None
    quality: int | None = None
    map_ids: tuple[str, ...] = ()
    apt_category: str = ""


@lru_cache(maxsize=1)
def catalog():
    return json.loads(resource_path("data/trade_items.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=2)
def map_identity_lines(lang):
    return {text: stat_id for stat_id, texts in catalog()["map_identity"][lang].items() for text in texts}


def map_identity_id(lang, text):
    known = map_identity_lines(lang)
    if stat_id := known.get(text):
        return stat_id
    if lang == "ko":
        normalized = re.sub(r"\((?:\.\.\.|…)\)(?= 등장$)", "", text, count=1)
        stat_id = known.get(normalized, "")
        if stat_id.startswith("implicit.stat_2563183002|"):
            return stat_id
    return ""


class BaseNotFound(ValueError):
    pass


def _confirmed_trade_rows(rows, confirmed_base):
    matching = [row for row in rows if row[:2] == ["ITEM", confirmed_base]]
    return list({tuple(row): row for row in matching}.values()) if matching else rows


def _lookup(lang, namespace, category, name, magic=False, *, confirmed_base=""):
    categories = (category,) if isinstance(category, str) else category
    rows = [row for row in catalog()["items"][lang]
            if row[0] == namespace and row[3] in categories]
    candidates = [row for row in rows if row[2] == name]
    if not candidates and magic:
        separator = " " if " " in name else ""
        words = name.split(separator) if separator else name
        spans = {separator.join(words[i:j]) for i in range(len(words)) for j in range(i + 1, len(words) + 1)}
        candidates = [row for row in rows if row[2] in spans]
        if candidates:
            length = max(len(row[2]) for row in candidates)
            candidates = [row for row in candidates if len(row[2]) == length]
    if not candidates:
        raise BaseNotFound("정확한 베이스 또는 품목 변형을 식별할 수 없습니다")
    candidates = _confirmed_trade_rows(candidates, confirmed_base)
    if len(candidates) != 1:
        raise ValueError("정확한 베이스 또는 품목 변형을 식별할 수 없습니다")
    return candidates[0]


def _localized(row, lang, *, confirmed_base=""):
    # refName만이 아니라 분류·discriminator까지 동일한 상대 레코드를 선택한다.
    targets = [other for other in catalog()["items"][lang]
               if other[:2] == row[:2] and other[3:] == row[3:]]
    targets = _confirmed_trade_rows(targets, confirmed_base)
    if len(targets) != 1:
        raise ValueError("동일한 현지화 품목을 식별할 수 없습니다")
    return targets[0][2]


def _number(lines, keys, pattern):
    values = []
    for line in lines:
        key, _, value = line.partition(":")
        if key in keys:
            match = re.fullmatch(pattern, value.strip())
            if not match:
                raise ValueError("품목의 등급 또는 수치를 읽을 수 없습니다")
            values.append(int(match[1]))
    if len(set(values)) > 1:
        raise ValueError("품목의 수치가 서로 일치하지 않습니다")
    return values[0] if values else None


def resolve_heist(model, category, rarity, server):
    if {"Unidentified", "미확인"}.intersection([*model.head, *model.flags]):
        raise ValueError("미확인 품목은 검색할 수 없습니다")
    if rarity not in {"Normal", "Magic", "Rare", "Unique"}:
        raise ValueError("지원하지 않는 품목 등급입니다")
    target = "en" if server == OFFICIAL else "ko"
    base = _lookup(model.lang, "ITEM", category, model.base, rarity == "Magic")
    name = ""
    if rarity == "Unique":
        unique = _lookup(model.lang, "UNIQUE", category, model.name)
        if unique[5] != base[1]:
            raise ValueError("고유 이름과 베이스를 함께 확인할 수 없습니다")
        name = _localized(unique, target)
    return Identity(_localized(base, target), name, base[4])


def _confirmed_equipment_base(model, category):
    if category not in {"Ring", "Boots", "Quiver"}:
        return ""
    implicits = [mod_en(model, mod) or "" for mod in model.mods if mod.kind == "implicit" and not mod.sub]
    if category in {"Ring", "Boots"}:
        matches = sum(bool(re.fullmatch(
            r"\+\d+% to (?:Fire and Cold|Fire and Lightning|Cold and Lightning) Resistances",
            text, re.I,
        )) for text in implicits)
        if matches == 1:
            return "Two-Stone Ring" if category == "Ring" else "Two-Toned Boots"
    elif len(implicits) == 1:
        match = re.fullmatch(r"Adds (\d+) to (\d+) Physical Damage to Attacks", implicits[0], re.I)
        if match:
            low, high = map(int, match.groups())
            # 현행 베이스와 단종 베이스의 기본 고정 피해 범위가 겹치지 않는다.
            if 12 <= low <= 15 and 24 <= high <= 27:
                return "Heavy Arrow Quiver"
            if (low, high) == (1, 4):
                return "Heavy Quiver"
    return ""


def resolve(model, category, rarity, server, *, equipment=False):
    lang = model.lang
    target = "en" if server == OFFICIAL else "ko"
    lines = [*model.head, *model.flags, *(m.text for m in model.mods)]
    if {"Unidentified", "미확인"}.intersection(lines):
        raise ValueError("미확인 품목은 검색할 수 없습니다")
    name = model.base
    if category == "Gem":
        gem = _lookup(lang, "GEM", "Gem", name)
        if gem[4] or gem[5] or any(re.match(r"^(?:Vaal |바알 )", line) for line in lines):
            raise ValueError("변형·바알 젬은 아직 시세 검색을 지원하지 않습니다")
        properties = list(takewhile(lambda line: line not in REQUIREMENTS, lines))
        level = _number(properties, {"Level", "레벨"}, r"(\d+)(?:\s*\((?:Max|최대)\))?(?:\s*\(augmented\))?")
        if not level:
            raise ValueError("젬 레벨을 읽을 수 없습니다")
        quality = _number(properties, {"Quality", "퀄리티"}, r"\+?(\d+)%(?:\s*\(augmented\))?")
        return Identity(_localized(gem, target), gem_level=level, quality=quality or 0)
    if rarity not in {"Normal", "Magic", "Rare", "Unique"}:
        raise ValueError("지원하지 않는 품목 등급입니다")
    if rarity in {"Normal", "Magic"}:
        if VARIANT.match(name) or {"Synthesised Item", "결합된 아이템"}.intersection(lines):
            raise ValueError("정체성을 바꾸는 변형 품목은 검색할 수 없습니다")
        name = re.sub(r"^(?:Superior|상급)\s+", "", name, count=1)
    tier = None
    if category == "Map":
        if any(label in name for label in GUARDIAN_NAMES):
            raise ValueError("이 지도는 아직 시세 검색을 지원하지 않습니다")
        if re.search(r"blight|역병", name, re.I):
            raise ValueError("역병 지도는 아직 시세 검색을 지원하지 않습니다")
        tiers = list(MAP_TIER.finditer(name))
        name = MAP_TIER.sub("", name)
        tier = _number(lines, {"Map Tier", "지도 등급"}, r"(\d+)")
        for match in tiers:
            suffix_tier = int(match[1] or match[2])
            if tier is not None and tier != suffix_tier:
                raise ValueError("지도 등급이 서로 일치하지 않습니다")
            tier = suffix_tier
    classes = ("Jewel", "Cluster Jewel") if equipment and category == "Jewel" else category
    confirmed_base = _confirmed_equipment_base(model, category)
    base = _lookup(lang, "ITEM", classes, name, rarity == "Magic", confirmed_base=confirmed_base)
    if base[4] or category == "Map" and base[1] not in MAP_BASES:
        raise ValueError("이 품목 변형은 아직 시세 검색을 지원하지 않습니다")
    if category == "Map" and (tier == 0 or (tier is None and base[1] != "Nightmare Map")):
        raise ValueError("지도 등급을 읽을 수 없습니다")
    unique_name = ""
    if rarity == "Unique":
        unique = _lookup(lang, "UNIQUE", category, model.name)
        if unique[4] or unique[5] != base[1]:
            raise ValueError("고유 이름과 베이스를 함께 확인할 수 없습니다")
        unique_name = _localized(unique, target)
    map_ids = ()
    if category == "Map":
        identities = {line: map_identity_id(lang, line) for line in lines}
        map_ids = tuple(dict.fromkeys(stat_id for stat_id in identities.values() if stat_id))
        unresolved = {line for line, stat_id in identities.items() if UNKNOWN_MAP.search(line) and not stat_id}
        ordinary_implicits = {
            mod.text for mod in model.mods
            if mod.text in unresolved and mod.kind == "implicit"
            and (english := mod_en(model, mod))
            and index().match(english, mod.kind, "Map").id == ORIGINATOR_MEMORIES_ID
        }
        if unresolved - ordinary_implicits:
            raise ValueError("지도 정체성을 정확히 식별할 수 없습니다")
    return Identity(_localized(base, target, confirmed_base=confirmed_base), unique_name,
                    "map" if category == "Map" and base[1] == "Map" else None, tier,
                    map_ids=map_ids, apt_category=base[3])


def blocked(identity, rarity):
    required = set(identity.map_ids)
    if rarity == "Normal":
        required.add("normal")
    if required - API_VERIFIED:
        return "공식 거래소 검증이 끝나지 않아 검색할 수 없습니다"
    if required - BROWSER_VERIFIED:
        return "브라우저 확인 대기: 아직 이 조건으로 검색할 수 없습니다"
    return ""
