"""게임 Ctrl+C / Ctrl+Alt+C(고급) 아이템 텍스트 → 구조화 (머리 부분 + 옵션 줄 목록).

- 옵션 줄의 종류(kind): explicit / implicit / crafted / fractured / enchant
  · 일반 복사: 줄 끝 꼬리표 '(implicit)' '(crafted)' ...
  · 고급 복사: '{ 고정 속성 부여 … }' / '{ Implicit Modifier … }' 같은 머리줄
- 고급 복사의 범위 '6(4-6)', 꼬리 '— 변경이 불가능한 값' / '— Unscalable Value' 는 제거
- 영문 PoB 용 텍스트 조합(compose_en): 한글이면 ko2en 으로 줄마다 변환
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

SEP = "--------"
RANGE_RE = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*\)")
TAG_RE = re.compile(r"\s*\((implicit|crafted|fractured|enchant|scourge|crucible)\)\s*$", re.IGNORECASE)
UNSCALABLE_RE = re.compile(r"\s*[—-]+\s*(변경이 불가능한 값|Unscalable Value)\s*$")
REMINDER_NOT_RE = re.compile(r"\(\s*-?\d|\((implicit|crafted|fractured|enchant)\)", re.IGNORECASE)
ITEM_LEVEL_KEYS = ("Item Level:", "아이템 레벨:")
FLAG_LINES = {
    "Corrupted", "Mirrored", "Split", "Unidentified", "Synthesised Item", "Fractured Item",
    "Shaper Item", "Elder Item", "Crusader Item", "Hunter Item", "Redeemer Item", "Warlord Item",
    "Searing Exarch Item", "Eater of Worlds Item",
    "타락", "복제", "분할됨", "미확인", "결합된 아이템", "분열된 아이템",
    "쉐이퍼 아이템", "엘더 아이템", "십자군 아이템", "사냥꾼 아이템", "대속자 아이템", "전쟁군주 아이템",
    "세계 포식자 아이템", "작열의 총주교 아이템",
}
KIND_KO = {"implicit": "고정", "explicit": "", "crafted": "제작", "fractured": "분열", "enchant": "인챈트"}
SUB_KO = {"exarch": "총주교", "eater": "포식자", "eldritch": "총주교/포식자", "corrupted": "바알(타락)"}
PRESENCE_RE = re.compile(r"^(While a (Unique Enemy|Pinnacle Atlas Boss) is in your Presence, |"
                         r"(고유 적|최종 아틀라스 보스)(이|가) 접근해 있는 동안, )", re.IGNORECASE)
EXARCH_FLAGS = ("Searing Exarch Item", "작열의 총주교 아이템")
EATER_FLAGS = ("Eater of Worlds Item", "세계 포식자 아이템")
CORRUPT_FLAGS = ("Corrupted", "타락")


def badge(m: "Mod") -> str:
    if m.kind == "implicit" and m.sub:
        return SUB_KO.get(m.sub, "고정")
    return KIND_KO.get(m.kind, "")


def _header_sub(h: str) -> str:
    h = h.lower()
    if "총주교" in h or "exarch" in h:
        return "exarch"
    if "포식자" in h or "eater" in h:
        return "eater"
    if "타락" in h or "corrupted" in h:
        return "corrupted"
    return ""


def _header_kind(h: str) -> str:
    """고급 복사 머리줄 '{ ... }' → 이어지는 옵션 줄의 종류."""
    h = h.lower()
    if "고정 속성" in h or "implicit" in h:
        return "implicit"
    if "제작" in h or "crafted" in h:
        return "crafted"
    if "분열" in h or "fractured" in h:
        return "fractured"
    if "인챈트" in h or "enchant" in h:
        return "enchant"
    return "explicit"


@dataclass
class Mod:
    text: str      # 표시용 원문 (정리된 한 줄)
    kind: str = "explicit"
    enabled: bool = True  # 옵션변경 창에서 켜고 끄기
    added: bool = False   # 옵션변경 창에서 새로 추가한 줄
    orig: str = ""        # 원래 문장 (수정 여부 표시용)
    sub: str = ""         # implicit 세부: exarch / eater / eldritch / corrupted
    en: str = ""          # PoB 데이터에서 추가한 줄의 원래 영문 (text 를 고치지 않았으면 그대로 사용)
    base_vals: bool = False  # 수치가 퀄리티 적용 전 값 (고급 복사 원문 · 새로 추가한 줄) → 촉매 퀄리티를 곱해서 계산
    unscalable: bool = False  # '— 변경이 불가능한 값' (퀄리티 영향 없음)
    affix: str = ""       # prefix / suffix (고급 복사 머리줄; 좌·우 촉매용)


@dataclass
class ItemModel:
    lang: str                       # "en" | "ko"
    head: list[str]                 # 첫 옵션 구역 전까지의 원문 줄 (종류/희귀도/이름/속성/요구/홈/아이템 레벨)
    mods: list[Mod] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    name: str = ""
    base: str = ""
    catalyst: str = ""              # 촉매 특수 퀄리티 종류 (ko2en.CATALYSTS 키)
    cat_q: int = 0                  # 그 퀄리티 %


def parse(text: str) -> ItemModel | None:
    if not text or SEP not in text:
        return None
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    first = lines[0].partition(":")[0].strip() if lines else ""
    if first not in ("Item Class", "아이템 종류"):
        return None
    lang = "ko" if first == "아이템 종류" else "en"
    # 섹션 분리
    sections, cur = [], []
    for ln in lines:
        if ln == SEP:
            sections.append(cur)
            cur = []
        elif ln:
            cur.append(ln)
    if cur:
        sections.append(cur)
    # 아이템 레벨이 있는 섹션까지가 머리, 이후가 옵션 (아이템 레벨이 없으면 첫 섹션 + 'key: value' 섹션들이 머리)
    lvl_idx = next((i for i, s in enumerate(sections) if any(x.startswith(ITEM_LEVEL_KEYS) for x in s)), None)
    if lvl_idx is None:
        lvl_idx = 0
        for i, s in enumerate(sections[1:], start=1):
            if all(": " in x or x.endswith(":") for x in s):
                lvl_idx = i
            else:
                break
    head = []
    for s in sections[:lvl_idx + 1]:
        if head:
            head.append(SEP)
        head.extend(s)
    names = []
    for x in sections[0][2:] if sections else []:
        names.append(x)
    model = ItemModel(lang, head, name=names[0] if names else "", base=names[-1] if names else "")
    rarity = next((x.split(":", 1)[1].strip() for x in (sections[0] if sections else [])
                   if x.startswith(("Rarity:", "아이템 희귀도:"))), "")
    unique = rarity in ("Unique", "고유")
    blueprint = bool(sections and sections[0] and sections[0][0].partition(":")[2].strip()
                     in {"Blueprints", "Heist Blueprints", "도면"})
    map_item = bool(sections and sections[0] and sections[0][0].partition(":")[2].strip() in {"Maps", "지도"})
    try:
        import ko2en

        cat = next((c for c in map(ko2en.catalyst_of, head) if c), None)
        if cat:
            model.catalyst, model.cat_q = cat
    except Exception:  # noqa: BLE001
        pass
    advanced = any(x.startswith("{") for s in sections[lvl_idx + 1:] for x in s)
    for s in sections[lvl_idx + 1:]:
        kind, sub, affix = "explicit", "", ""
        sec: list[Mod] = []
        reminder = False
        for raw in s:
            # 설명문 '("동결"은 ... )' — 여러 줄에 걸칠 수 있음
            if reminder:
                reminder = not raw.endswith(")")
                continue
            if raw.startswith("(") and not REMINDER_NOT_RE.match(raw):
                reminder = not raw.endswith(")")
                continue
            if raw.startswith("{"):
                kind = _header_kind(raw)
                sub = _header_sub(raw) if kind == "implicit" else ""
                hl = raw.lower()
                affix = "prefix" if ("접두" in hl or "prefix" in hl) else "suffix" if ("접미" in hl or "suffix" in hl) else ""
                continue
            if raw in FLAG_LINES:
                model.flags.append(raw)
                continue
            unscalable = bool(UNSCALABLE_RE.search(raw))
            ln = UNSCALABLE_RE.sub("", raw)
            ln = RANGE_RE.sub("", ln)
            k = kind
            m = TAG_RE.search(ln)
            if m:
                k = m.group(1).lower()
                ln = ln[:m.start()]
            # 보이지 않는 제어/서식 문자 제거, 글자·숫자가 하나도 없는 줄(빈 칸처럼 보이는 줄)은 건너뜀
            ln = "".join(ch for ch in ln if unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cn"))
            ln = re.sub(r"\s+", " ", ln).strip()
            if ln and any(ch.isalnum() for ch in ln):
                # 고급 복사의 수치는 퀄리티 적용 전 값 (PoB 주석: values won't have catalyst applied)
                sec.append(Mod(ln, k, sub=sub if k == "implicit" else "", base_vals=advanced,
                               unscalable=unscalable, affix=affix))
        sec = _merge_multiline(sec, lang)
        keep_identity = ((blueprint and any(m.kind == "enchant" for m in sec))
                         or (map_item and any(m.kind == "implicit" for m in sec)))
        if sec and not keep_identity and _is_flavour(sec, lang, unique):
            continue
        model.mods.extend(sec)
    classify_implicits(model)
    return model


def _merge_multiline(sec: list[Mod], lang: str) -> list[Mod]:
    """게임 텍스트에서 두 줄로 나뉘어 나오는 옵션(예: '...상태 이상으로' + '주는 원소 피해 37% 증가')을 한 줄로."""
    try:
        import ko2en

        out, i = [], 0
        while i < len(sec):
            a = sec[i]
            if i + 1 < len(sec) and sec[i + 1].kind == a.kind and ko2en.joins(a.text, sec[i + 1].text, lang):
                a = Mod(a.text + "\n" + sec[i + 1].text, a.kind, sub=a.sub, base_vals=a.base_vals,
                        unscalable=a.unscalable or sec[i + 1].unscalable, affix=a.affix)
                i += 2
            else:
                i += 1
            out.append(a)
        return out
    except Exception:  # noqa: BLE001
        return sec


def _is_flavour(sec: list[Mod], lang: str, unique: bool) -> bool:
    """고유 아이템 플레이버 텍스트 / 사용 설명 구역: 알려진 옵션이 하나도 없는 구역."""
    try:
        import ko2en

        if any(ko2en.known(m.text, lang) for m in sec):
            return False
    except Exception:  # noqa: BLE001
        return False
    return unique or not any(ch.isdigit() for m in sec for ch in m.text)


def classify_implicits(model: ItemModel) -> None:
    """implicit 줄이 총주교/포식자/바알(타락) 중 무엇인지 표시 (고급 복사 머리줄이 없을 때 추정)."""
    flags = set(model.flags)
    exarch = any(f in flags for f in EXARCH_FLAGS)
    eater = any(f in flags for f in EATER_FLAGS)
    corrupt = any(f in flags for f in CORRUPT_FLAGS)
    try:
        import ko2en

        kd = ko2en._dict()
        kinds = kd.implicit_kinds
        base_en = model.base if model.lang == "en" else (ko2en.translate_base(model.base) or model.base)
        base_imp = set(kd.base_implicits.get(base_en, []))
    except Exception:  # noqa: BLE001
        kinds, base_imp = {}, set()
    for m in model.mods:
        if m.kind != "implicit" or m.sub:
            continue
        presence = bool(PRESENCE_RE.match(m.text))
        en = m.text
        if model.lang == "ko":
            import ko2en

            en = ko2en.translate_mod(m.text) or m.text
        sk = skeleton(PRESENCE_RE.sub("", en))
        if not presence and sk in base_imp:
            continue  # 베이스 아이템 고유 implicit → 그냥 '고정'
        cand = kinds.get(sk, [])
        if exarch and ("exarch" in cand or (presence and not eater)):
            m.sub = "exarch"
        elif eater and ("eater" in cand or (presence and not exarch)):
            m.sub = "eater"
        elif presence or (exarch or eater) and ("exarch" in cand or "eater" in cand):
            m.sub = "eldritch"
        elif corrupt and "corrupted" in cand:
            m.sub = "corrupted"


_SK_RANGE = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?\s*\)")
_SK_NUM = re.compile(r"[+-]?\d+(?:\.\d+)?")


def skeleton(s: str) -> str:
    """tools/build_names._skel 과 같은 규칙."""
    s = re.sub(r"\{\d+\}", "#", s)
    s = _SK_RANGE.sub("#", s)
    s = _SK_NUM.sub("#", s)
    return re.sub(r"[+-]#", "#", s).strip().lower()


def mod_en(model: ItemModel, m: Mod) -> str | None:
    """옵션 줄의 영문 (PoB 용). 한글을 못 옮기면 None."""
    if model.lang != "ko":
        return m.text
    import ko2en

    en = m.en if (m.en and m.text == m.orig) else ko2en.translate_mod(m.text)
    if en is None and re.fullmatch(r"[\x00-\x7f]+", m.text):
        en = m.text  # 영문으로 직접 입력한 줄
    return en


def cat_scalar(model: ItemModel, m: Mod, en: str | None = None) -> float:
    """촉매 특수 퀄리티 배율 (PoB getCatalystScalar 와 같은 규칙: 옵션 태그가 촉매 태그와 겹치면 (100+q)/100)."""
    if not model.catalyst or not model.cat_q or m.unscalable:
        return 1.0
    import ko2en

    en = en if en is not None else mod_en(model, m)
    if not en:
        return 1.0
    tags = set(ko2en.mod_tags(en))
    if m.affix:
        tags.add(m.affix)
    return (100 + model.cat_q) / 100 if tags & set(ko2en.catalyst_tags(model.catalyst)) else 1.0


_VAL_RE = re.compile(r"\d+(?:\.\d+)?")


def scale_numbers(text: str, s: float) -> str:
    """수치에 배율 적용 (PoB 처럼 내림)."""
    if s == 1.0:
        return text

    def rep(mt):
        v = mt.group(0)
        if "." in v:
            return f"{math.floor(float(v) * s * 100 + 1e-6) / 100:g}"
        return str(math.floor(int(v) * s + 1e-6))

    return _VAL_RE.sub(rep, text)


QUALITY_LINE_RE = re.compile(r"^(Quality|퀄리티): \+?(\d+)%")
# 일반 퀄리티가 적용되는 장비(무기·방어구)에만 있는 속성 줄
QUALITY_PROP_KEYS = ("Physical Damage:", "Attacks per Second:", "Armour:", "Evasion Rating:", "Energy Shield:",
                     "Ward:", "Chance to Block:", "물리 피해:", "초당 공격 횟수:", "방어도:", "회피:",
                     "에너지 보호막:", "수호:", "막기 확률:")


def get_quality(model: ItemModel) -> int | None:
    """일반 퀄리티 %. 퀄리티를 받을 수 없는 아이템(장신구·주얼 등)이면 None, 줄이 없으면 0."""
    for ln in model.head:
        m = QUALITY_LINE_RE.match(ln)
        if m:
            return int(m.group(2))
    if any(ln.startswith(QUALITY_PROP_KEYS) for ln in model.head):
        return 0
    return None


def set_quality(model: ItemModel, q: int) -> None:
    """머리의 퀄리티 줄을 q% 로 바꾼다 (없으면 첫 구분선 뒤에 넣음)."""
    word = "퀄리티" if model.lang == "ko" else "Quality"
    line = f"{word}: +{int(q)}%"
    for i, ln in enumerate(model.head):
        if QUALITY_LINE_RE.match(ln):
            model.head[i] = line
            return
    if SEP in model.head:
        model.head.insert(model.head.index(SEP) + 1, line)
    else:
        model.head.extend([SEP, line])


def compose_en(model: ItemModel, mods: list[Mod] | None = None) -> tuple[str, list[str]]:
    """PoB 에 넘길 영문 텍스트와, 변환하지 못한 옵션 줄 목록."""
    mods = model.mods if mods is None else mods
    miss: list[str] = []
    if model.lang == "ko":
        import ko2en

        head = ko2en.translate_item("\n".join(model.head)).text
        flags = [ko2en.FLAGS.get(f, f) for f in model.flags]
    else:
        head = "\n".join(model.head)
        flags = list(model.flags)
    out = []
    for m in mods:
        en = mod_en(model, m)
        if en is None:
            miss.append(m.text)
            continue
        if m.base_vals:  # 퀄리티 적용 전 수치 → 직접 곱해서 넘김 (PoB 는 태그 없는 줄엔 퀄리티를 안 곱함)
            en = scale_numbers(en, cat_scalar(model, m, en))
        out.append((en, m.kind))
    parts = [head]

    def tag(t: str, k: str) -> str:  # 여러 줄 옵션은 줄마다 꼬리표
        return "\n".join(x + f" ({k})" for x in t.split("\n"))

    imp = [tag(t, "implicit") for t, k in out if k == "implicit"]
    ench = [tag(t, "enchant") for t, k in out if k == "enchant"]
    exp = [tag(t, k) if k in ("crafted", "fractured") else t for t, k in out
           if k not in ("implicit", "enchant")]
    for block in (ench, imp, exp, flags):
        if block:
            parts.append(SEP)
            parts.append("\n".join(block))
    return "\n".join(parts), miss
