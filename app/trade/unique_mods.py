"""이름으로 확정한 두 고유 아이템의 변동 옵션 처리."""
from functools import lru_cache
import re

import ko2en
from itemmodel import mod_en
from trade.stats import Match, index

DESTINY = "Bound By Destiny"
MONARCH = "The Dark Monarch"
MONARCH_PREFIX = "explicit.stat_56473917|"
LIVING_ID = MONARCH_PREFIX + "15"
LIVING_REF = "Maximum number of Living Lightning is Doubled\nCannot have Minions other than Living Lightning"
# 2026-11-19 머성: 어둠의 국왕 |15 카카오 링크(다른 옵션 해제)에서 살아 있는 번개 매물만 나오는 것을 확인.
# 다른 소환수 변형(|1~|14, |16)은 확인하지 않아 계속 닫는다.
LIVING_BROWSER_VERIFIED = True
DESTINY_REF = re.compile(r"\bif [246] (?:Shaper|Elder|Crusader|Redeemer|Hunter|Warlord) Items are Equipped\b")


def unique_ref(model, rarity):
    if model is None or rarity != "Unique":
        return ""
    return ko2en.translate_unique(model.name) if model.lang == "ko" else model.name


@lru_cache(maxsize=1)
def destiny_pool():
    return frozenset((ref, ids[0]) for entry in index().entries
                     if (ref := entry["ref"]) and DESTINY_REF.search(ref)
                     and len(ids := entry["ids"].get("explicit", ())) == 1)


@lru_cache(maxsize=2)
def _living_copy_forms(lang):
    stat_index = index().ko if lang == "ko" else index()
    for i, entry in enumerate(stat_index.entries):
        if entry["ref"] == LIVING_REF and entry["ids"].get("explicit") == [LIVING_ID]:
            return {(form, advanced) for matcher in stat_index.by_entry[i]
                    for form, advanced in ((matcher["string"], False), (matcher["advanced"], True))
                    if isinstance(form, str)}
    return set()


def living_pair(model, first, second):
    if (first.kind != "explicit" or second.kind != first.kind
            or first.copy_block is None or second.copy_block != first.copy_block
            or first.copy_section is None or second.copy_section != first.copy_section
            or first.copy_line is None or second.copy_line != first.copy_line + 1):
        return None
    joined = first.text + "\n" + second.text
    advanced = first.copy_block > 0
    forms = _living_copy_forms(model.lang)
    if (joined, advanced) not in forms and not (model.lang == "en" and advanced and (joined, False) in forms):
        return None
    if not LIVING_BROWSER_VERIFIED:
        return Match(reason="브라우저 확인 대기: 살아 있는 번개")
    if model.lang == "ko":
        a, b = mod_en(model, first), mod_en(model, second)
        english = "\n".join((a, b)) if a and b else None
        matched = index().bilingual(joined, english, first.kind, "ARMOUR")
    else:
        matched = index().match(joined, first.kind, "ARMOUR")
    if not matched.ids and (matched.id, matched.ref) == (LIVING_ID, LIVING_REF):
        return matched
    return Match(reason=matched.reason or "고정 소환수 ID·ref 불일치",
                 candidate_refs=matched.candidate_refs)
