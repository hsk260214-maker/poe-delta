"""한글 클라이언트 아이템 텍스트(Ctrl+C) → 영문 아이템 텍스트 변환 (PoB 는 영문만 해석).

- 옵션 줄: 게임 공식 stat 번역(영·한, 같은 stat id 끼리 짝) 템플릿으로 변환. 수치는 '{i}' 순서로 옮겨
  한글/영문 어순이 달라도 맞는 자리에 들어간다.
- 베이스 이름 / 아이템 종류: RePoE 영·한 데이터.
- 머리글·속성 줄: 클라이언트 문자열 (Awakened PoE Trade 한글 데이터 기준).
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field

from data import resource_path

SEP = "--------"
NUM = r"[+-]?\d+(?:\.\d+)?"
NUM_RE = re.compile(NUM)
PH_RE = re.compile(r"([+-]?)\{(\d+)\}")
TAG_RE = re.compile(r"\s*(\((?:implicit|crafted|fractured|enchant|scourge|crucible)\))\s*$", re.IGNORECASE)

RARITY = {"일반": "Normal", "마법": "Magic", "희귀": "Rare", "고유": "Unique", "젬": "Gem", "화폐": "Currency",
          "점술 카드": "Divination Card", "퀘스트": "Quest"}
PROPS = {
    "아이템 레벨": "Item Level", "퀄리티": "Quality", "홈": "Sockets", "방어도": "Armour", "회피": "Evasion Rating",
    "에너지 보호막": "Energy Shield", "수호": "Ward", "막기 확률": "Chance to Block", "물리 피해": "Physical Damage",
    "원소 피해": "Elemental Damage", "치명타 확률": "Critical Strike Chance", "초당 공격 횟수": "Attacks per Second",
    "레벨": "Level",
}
FLAGS = {
    "타락": "Corrupted", "두 번 타락": "Corrupted", "미확인": "Unidentified", "복제": "Mirrored", "분할됨": "Split",
    "쉐이퍼 아이템": "Shaper Item", "엘더 아이템": "Elder Item", "십자군 아이템": "Crusader Item",
    "사냥꾼 아이템": "Hunter Item", "대속자 아이템": "Redeemer Item", "전쟁군주 아이템": "Warlord Item",
    "결합된 아이템": "Synthesised Item", "세계 포식자 아이템": "Eater of Worlds Item",
    "작열의 총주교 아이템": "Searing Exarch Item",
}
# 촉매 특수 퀄리티: (키, PoB 설명어, PoB 촉매 태그, 한글 키워드, 영문 키워드) — 순서대로 첫 일치
#   PoB Classes/Item.lua catalystDescriptorList / catalystTags 와 같은 태그
CATALYSTS = [
    ("physchaos", "Physical and Chaos", ("physical_damage", "chaos_damage"), ("물리", "카오스"), ("physical", "chaos")),
    ("lifemana", "Life and Mana", ("life", "mana", "resource"), ("생명력", "마나"), ("life", "mana")),
    ("resistance", "Resistance", ("jewellery_resistance", "resistance"), ("저항",), ("resist",)),
    ("elemental", "Elemental", ("jewellery_elemental", "elemental_damage"), ("원소",), ("elemental",)),
    ("attribute", "Attribute", ("jewellery_attribute", "attribute"), ("능력치",), ("attribute",)),
    ("defence", "Defence", ("jewellery_defense", "defences", "armour", "evasion", "energyshield"), ("방어",), ("defen",)),
    ("caster", "Caster", ("caster",), ("주문", "시전"), ("caster",)),
    ("critical", "Critical", ("critical",), ("치명",), ("critical",)),
    ("speed", "Speed", ("speed",), ("속도",), ("speed",)),
    ("attack", "Attack", ("attack",), ("공격",), ("attack",)),
    ("prefix", "Prefix", ("prefix",), ("접두",), ("prefix",)),
    ("suffix", "Suffix", ("suffix",), ("접미",), ("suffix",)),
]
CAT_KO = {"physchaos": "물리·카오스", "lifemana": "생명력·마나", "resistance": "저항", "elemental": "원소 피해",
          "attribute": "능력치", "defence": "방어", "caster": "주문", "critical": "치명타", "speed": "속도",
          "attack": "공격", "prefix": "접두어", "suffix": "접미어"}
QUALITY_RE = re.compile(r"^(?:Quality|퀄리티) \((.+?)\): \+?(\d+)%")


def catalyst_of(line: str) -> tuple[str, int] | None:
    """'퀄리티 (원소 피해 속성 부여): +20%' / 'Quality (Elemental Damage Modifiers): +20%' → ('elemental', 20)."""
    m = QUALITY_RE.match(line.strip())
    if not m:
        return None
    desc = m.group(1).lower()
    for key, _, _, ko, en in CATALYSTS:
        if any(k in desc for k in ko) or any(k in desc for k in en):
            return key, int(m.group(2))
    return None


def catalyst_tags(key: str) -> tuple[str, ...]:
    return next((c[2] for c in CATALYSTS if c[0] == key), ())


def mod_tags(en_line: str) -> list[str]:
    """영문 옵션 문장 → RePoE 옵션 태그 (없으면 빈 목록)."""
    from itemmodel import skeleton

    return _dict().mod_tags.get(skeleton(en_line), [])


NAME_PREFIXES = ("상급 ", "결합된 ", "삿된 ", "흔적 ", "기묘한 ", "상이한 ", "몽환적인 ")


@dataclass
class Result:
    text: str
    untranslated: list[str] = field(default_factory=list)


class _Dict:
    def __init__(self):
        d = json.loads(resource_path("data/ko_en.json").read_text(encoding="utf-8"))
        self.bases: dict[str, str] = d["bases"]
        self.uniques: dict[str, str] = d.get("uniques", {})
        self.implicit_kinds: dict[str, list[str]] = d.get("implicit_kinds", {})
        self.base_implicits: dict[str, list[str]] = d.get("base_implicits", {})
        self.classes: dict[str, str] = d["classes"]
        self.mod_tags: dict[str, list[str]] = d.get("mod_tags", {})
        self.base_list = sorted(self.bases, key=len, reverse=True)
        self._stats = d["stats"]
        self._passive = d.get("passive", [])
        self._prev: dict | None = None
        self._rev: dict | None = None
        # 골격 → [템플릿, 결과, 부호수, 컴파일된 정규식(처음 쓸 때)] — 수만 개를 미리 컴파일하면 수 초 걸림
        self.index = _build_index((ko, en) for ko, en in d["stats"])


def _build_index(pairs) -> dict[str, list[list]]:
    idx: dict[str, list[list]] = {}
    for src, dst in pairs:
        idx.setdefault(_skeleton_tpl(src), []).append([src, dst, src.count("+{") + src.count("-{"), None])
    for lst in idx.values():
        lst.sort(key=lambda t: -t[2])  # 부호가 명시된(더 구체적인) 템플릿 먼저 (안정 정렬: 원래 우선순위 유지)
    return idx


def _lookup(idx: dict[str, list[list]], line: str):
    """(정규식 match, 결과 템플릿) 들 — 그 골격 묶음만 필요할 때 컴파일."""
    for e in idx.get(_skeleton_line(line), ()):
        if e[3] is None:
            e[3] = _regex(e[0])
        m = e[3].match(line)
        if m:
            yield m, e[1]


def _skeleton_tpl(tpl: str) -> str:
    # 고정 숫자(예: '1초마다')도 아이템 줄 쪽과 똑같이 '#' 로
    return NUM_RE.sub("#", PH_RE.sub("#", tpl)).strip()


def _skeleton_line(line: str) -> str:
    return NUM_RE.sub("#", line).strip()


def _regex(tpl: str) -> re.Pattern:
    out, last, seen = [], 0, set()
    for m in PH_RE.finditer(tpl):
        out.append(re.escape(tpl[last:m.start()]))
        i = m.group(2)
        # 템플릿에 부호(+#)가 있으면 아이템 줄에도 부호가 있어야 함 → '냉기 저항 +20%' 와 '냉기 저항 75%'(고정값) 구분
        num = r"[+-]\d+(?:\.\d+)?" if m.group(1) else NUM
        out.append(rf"(?P=v{i})" if i in seen else rf"(?P<v{i}>{num})")
        seen.add(i)
        last = m.end()
    out.append(re.escape(tpl[last:]))
    return re.compile("^" + "".join(out) + "$")


_D: _Dict | None = None
_LOCK = threading.Lock()


def _dict() -> _Dict:
    global _D
    if _D is None:
        with _LOCK:
            if _D is None:
                _D = _Dict()
    return _D


def reload() -> None:
    """번역 사전이 자동 갱신된 뒤 다시 읽기."""
    global _D, _NAME_REV
    with _LOCK:
        _D = None
    _NAME_REV = None
    _PASSIVE_CACHE.clear()


def preload() -> None:
    try:
        _dict()
    except Exception:  # noqa: BLE001
        pass


def _fill(en_tpl: str, vals: dict[str, str]) -> str:
    def rep(m):
        sign, i = m.group(1), m.group(2)
        v = vals.get(f"v{i}")
        if v is None:
            return m.group(0)
        if not sign:
            return v  # 영문 템플릿에 부호가 없으면 원래 표시된 부호(+82, -5)를 그대로
        num = v.lstrip("+-")
        if v.startswith("-"):
            return "-" + num
        return sign + num if sign == "+" else "-" + num

    return PH_RE.sub(rep, en_tpl)


def translate_mod(line: str) -> str | None:
    d = _dict()
    for m, en in _lookup(d.index, line):
        out = _fill(en, m.groupdict())
        if not PH_RE.search(out):  # 수치 자리가 다른 줄에 있는 반쪽 문장 → 오역 대신 실패 처리
            return out
    return None


def _en_skels() -> tuple[set[str], set[str]]:
    """영문 템플릿 골격 (전체, 여러 줄짜리) — 영문 아이템의 옵션 인식용."""
    d = _dict()
    if getattr(d, "_en_sk", None) is None:
        allsk = {_skeleton_tpl(en) for _, en in d._stats}
        d._en_sk = (allsk, {s for s in allsk if "\n" in s})
    return d._en_sk


def known(line: str, lang: str) -> bool:
    """알려진 옵션 문장인지 (설명문·플레이버 텍스트 구분용)."""
    if lang == "ko":
        return translate_mod(line) is not None
    return _skeleton_line(line) in _en_skels()[0]


def joins(a: str, b: str, lang: str) -> bool:
    """두 줄이 합쳐서 하나의 여러 줄 옵션인지."""
    s = a + "\n" + b
    if lang == "ko":
        return translate_mod(s) is not None
    return _skeleton_line(s) in _en_skels()[1]


def en_to_ko(line: str) -> str | None:
    """영문 옵션 문장 → 한글 (옵션 추가 목록 표시용). 실패하면 None."""
    d = _dict()
    if d._rev is None:
        d._rev = _build_index((en, ko) for ko, en in d._stats)
    for m, ko in _lookup(d._rev, line):
        out = _fill(ko, m.groupdict())
        if not PH_RE.search(out):
            return out
    return None


_PASSIVE_CACHE: dict[str, str] = {}


def passive_ko(line: str) -> str:
    """패시브 노드 효과 영문 → 한글 (트리 표시용). 실패하면 영문 그대로."""
    if line in _PASSIVE_CACHE:
        return _PASSIVE_CACHE[line]
    d = _dict()
    if d._prev is None:
        d._prev = _build_index((en, ko) for en, ko in d._passive)
    out = None
    for m, ko in _lookup(d._prev, line):
        t = _fill(ko, m.groupdict())
        if not PH_RE.search(t):
            out = t
            break
    if out is None:
        out = en_to_ko(line) or line
    _PASSIVE_CACHE[line] = out
    return out


_NAME_REV: dict[str, str] | None = None


def name_ko(en: str) -> str:
    """영문 유니크/베이스 이름 → 한글 (없으면 빈 문자열). 아이템 만들기 창 목록 표시용."""
    global _NAME_REV
    if _NAME_REV is None:
        d = _dict()
        rev: dict[str, str] = {}
        for ko, e in d.bases.items():
            rev.setdefault(e, ko)
        for ko, e in d.uniques.items():
            rev.setdefault(e, ko)
        _NAME_REV = rev
    return _NAME_REV.get(en, "")


_RANGE_RE = re.compile(r"\((-?[\d.]+)-(-?[\d.]+)\)")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def mod_ko(text: str) -> str:
    """영문 옵션(범위 '(24-28)' 포함, ' / ' 로 여러 줄) → 한글 '24~28'. 번역 못 하면 영문 그대로."""
    out = []
    for part in text.split(" / "):
        lo = _RANGE_RE.sub(lambda m: m.group(1), part)
        hi = _RANGE_RE.sub(lambda m: m.group(2), part)
        klo, khi = passive_ko(lo), passive_ko(hi)
        if klo == lo:
            out.append(part)
            continue
        if lo == hi:
            out.append(klo)
            continue
        a, b = _NUM_RE.findall(klo), _NUM_RE.findall(khi)
        if len(a) == len(b) and _NUM_RE.sub("#", klo) == _NUM_RE.sub("#", khi):
            it = iter(zip(a, b))

            multi = sum(1 for x, y in zip(a, b) if x != y) > 1

            def rep(_m):
                x, y = next(it)
                if x == y:
                    return x
                return f"({x}~{y})" if multi else f"{x}~{y}"  # 'Adds (6-9) to (13-15)' → (6~9)~(13~15)

            out.append(_NUM_RE.sub(rep, klo))
        else:
            out.append(khi)
    return " / ".join(out)


def label_ko(label: str) -> str:
    """'+# to maximum Life' 같은 묶음 이름 → '최대 생명력 +#'."""
    parts = []
    for part in label.split(" / "):
        if _RANGE_RE.search(part):  # 티어가 하나뿐인 옵션은 '(5-7)%' 처럼 범위가 그대로 남아 있음
            parts.append(mod_ko(part))
            continue
        t = passive_ko(part.replace("#", "7"))
        parts.append(_NUM_RE.sub("#", t) if t != part.replace("#", "7") else part)
    return " / ".join(parts)


def translate_base(name: str) -> str | None:
    d = _dict()
    n = name
    for p in NAME_PREFIXES:
        if n.startswith(p):
            n = n[len(p):]
    if n in d.bases:
        return d.bases[n]
    for kb in d.base_list:  # 마법 아이템: '접두 베이스 접미' 안에서 가장 긴 베이스 이름
        if len(kb) >= 2 and kb in n:
            return d.bases[kb]
    return None


def translate_unique(name: str) -> str:
    d = _dict()
    if name in d.uniques:
        return d.uniques[name]
    if name.startswith("삿된 ") and name[3:] in d.uniques:
        return "Foulborn " + d.uniques[name[3:]]
    return name


def translate_item(text: str) -> Result:
    d = _dict()
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    out: list[str] = []
    miss: list[str] = []
    rarity = ""
    i = 0
    # --- 머리 (종류 / 희귀도 / 이름 / 베이스)
    while i < len(lines) and lines[i] != SEP:
        ln = lines[i].strip()
        if ln.startswith("아이템 종류:"):
            cls = ln.split(":", 1)[1].strip()
            out.append(f"Item Class: {d.classes.get(cls, cls)}")
        elif ln.startswith("아이템 희귀도:"):
            rarity = RARITY.get(ln.split(":", 1)[1].strip(), ln.split(":", 1)[1].strip())
            out.append(f"Rarity: {rarity}")
        elif ln:
            block = []
            for x in lines[i:]:
                if x == SEP:
                    break
                if x.strip():
                    block.append(x.strip())
            i += len(block) - 1
            if rarity in ("Rare", "Unique") and len(block) >= 2:
                base = translate_base(block[-1])
                out.append(translate_unique(block[0]) if rarity == "Unique" else block[0])
                out.append(base or block[-1])
                if not base:
                    miss.append(block[-1])
            else:
                base = translate_base(block[0])
                out.append(base or block[0])
                if not base:
                    miss.append(block[0])
        i += 1
    # --- 본문
    for ln in lines[i:]:
        s = ln.strip()
        if not s:
            continue
        if s == SEP:
            out.append(SEP)
            continue
        if s in FLAGS:
            out.append(FLAGS[s])
            continue
        if s.endswith(":") and s[:-1] in ("요구 사항", "요구사항"):
            out.append("Requirements:")
            continue
        cat = catalyst_of(s)
        if cat:  # 촉매 특수 퀄리티 → PoB 표기
            desc = next(c[1] for c in CATALYSTS if c[0] == cat[0])
            out.append(f"Quality ({desc} Modifiers): +{cat[1]}%")
            continue
        key, sep, val = s.partition(": ")
        if sep and key in PROPS:
            out.append(f"{PROPS[key]}: {val}")
            continue
        if sep and len(key) <= 12 and not any(ch.isdigit() for ch in key):
            continue  # 요구 능력치(힘: 100) 등 PoB 계산에 필요 없는 속성 줄
        if s.startswith("{"):
            continue  # 고급 복사의 옵션 머리줄
        tag = ""
        m = TAG_RE.search(s)
        if m:
            tag = " " + m.group(1)
            s = s[:m.start()]
        s = re.sub(r"\(\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*\)", "", s)  # 고급 복사 범위
        en = translate_mod(s)
        if en is not None:
            out.append(en + tag)
        elif any(ch.isdigit() for ch in s):
            miss.append(s)  # 수치가 있는 줄을 못 옮긴 경우만 보고 (설명문 등은 무시)
    return Result("\n".join(out), miss)
