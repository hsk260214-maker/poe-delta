from dataclasses import replace

import pytest

from itemmodel import ItemModel, Mod, mod_en, parse
from trade import config, items, stats
from trade.query import StatCondition, build_query, conditions, item_info
from trade.stats import Match, choose_match, index


@pytest.fixture
def vaal_temple(fixtures):
    return parse((fixtures / "vaal_temple_map_ko.txt").read_text(encoding="utf-8"))


def test_vaal_temple_has_its_own_gate_and_no_tier(monkeypatch, vaal_temple):
    monkeypatch.setattr(items, "VAAL_TEMPLE_BROWSER_VERIFIED", False)
    info = item_info(vaal_temple, config.KAKAO)
    assert not info.supported and "브라우저 확인 대기" in info.message


@pytest.mark.parametrize("server,base", [(config.KAKAO, "바알 사원 지도"), (config.OFFICIAL, "Vaal Temple Map")])
def test_vaal_temple_open_gate_payload(monkeypatch, vaal_temple, server, base):
    monkeypatch.setattr(items, "VAAL_TEMPLE_BROWSER_VERIFIED", True)
    info = item_info(vaal_temple, server)
    row, = [row for row in conditions(info) if row.kind == "implicit"]
    assert (row.kind, row.checked, row.match.id) == ("implicit", False, "implicit.stat_44159086")
    query = build_query(info, [row], monster_level=True)["query"]
    assert query["type"] == base
    assert query["filters"]["misc_filters"]["filters"]["corrupted"] == {"option": "true"}
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "nonunique"}
    assert "map_tier" not in query["filters"]["map_filters"]["filters"]
    assert query["filters"]["map_filters"]["filters"]["map_blighted"] == {"option": "false"}
    assert info.ilvl == 84 and info.monster_level == 83
    assert query["filters"]["map_filters"]["filters"]["area_level"] == {"min": 83, "max": 83}
    assert query["stats"] == [{"type": "and", "filters": []}]


def test_fixed_number_is_not_a_roll_and_korean_can_match_alone():
    entry = index().bilingual("힘 15당 피해 10% 증가", "10% increased Damage per 15 Strength", "explicit", "ARMOUR")
    assert (entry.id, entry.rolls) == ("explicit.stat_3948776386", ("10",))
    model = parse("아이템 종류: 반지\n아이템 희귀도: 희귀\n토파즈 반지\n--------\n"
                  "아이템 레벨: 83\n--------\n힘 15당 피해 10% 증가")
    row, = conditions(item_info(model, config.KAKAO))
    assert row.minimum == 9


def test_implicit_one_second_in_translation_does_not_change_roll():
    match = index().bilingual("1초마다 생명력 96.1 재생", "Regenerate 96.1 Life per second",
                              "explicit", "ARMOUR")
    assert (match.id, match.rolls) == ("explicit.stat_3325883026", ("96.1",))


def test_bilingual_different_fixed_seconds_still_conflict():
    match = index().bilingual("처치 시 10%의 확률로 4초 동안 맹공 획득",
                              "10% chance to gain Onslaught for 10 seconds on Kill", "explicit", "ARMOUR")
    assert not match.id and match.reason == "한국어·번역 연결 불일치"


@pytest.mark.parametrize("ko,en,stat_id", [
    ("화염", "Fire", "3372524247"), ("냉기", "Cold", "4220027924"), ("번개", "Lightning", "1671376347"),
])
@pytest.mark.parametrize("kind", ["explicit", "implicit"])
def test_known_korean_resistance_collision_keeps_only_established_single(ko, en, stat_id, kind):
    matched = index().bilingual(f"{ko} 저항 +46%", f"+46% to {en} Resistance", kind, "ARMOUR")
    assert matched.id == f"{kind}.stat_{stat_id}" and not matched.ids
    assert index().bilingual(f"{ko} 저항 +46%", f"+45% to {en} Resistance", kind, "ARMOUR").ambiguous


def test_gear_grants_aura_stat_not_unique_effect():
    model = parse("아이템 종류: 투구\n아이템 희귀도: 희귀\n가죽 모자\n--------\n"
                  "아이템 레벨: 83\n--------\n20레벨 분노 스킬 사용 가능")
    info = item_info(model, config.KAKAO)
    row, = conditions(info)
    assert (row.match.id, row.minimum) == ("explicit.stat_449494711", 20)
    assert build_query(info, [row])["query"]["stats"][0]["filters"] == [
        {"id": "explicit.stat_449494711", "value": {"min": 20}},
    ]
    assert index().match("Grants Level 20 \u200bAnger", "explicit", "ARMOUR").id == "explicit.effect_2014162730"


@pytest.mark.parametrize("k,e,status", [
    ("match", "match", "match"), ("match", "other", "mismatch"),
    ("match", "miss", "match"), ("miss", "match", "match"),
    ("ambiguous", "match", "ambiguous"), ("ambiguous", "miss", "ambiguous"),
    ("match", "ambiguous", "ambiguous"), ("miss", "ambiguous", "ambiguous"),
    ("ambiguous", "ambiguous", "ambiguous"), ("miss", "miss", "miss"),
])
def test_k_e_decision_table(k, e, status):
    cases = {"match": Match("explicit.stat_1", reason=""), "other": Match("explicit.stat_2", reason=""),
             "miss": Match(), "ambiguous": Match(reason="후보가 여러 개", ambiguous=True)}
    result = choose_match(cases[k], cases[e])
    if status == "mismatch":
        assert result.reason == "한국어·번역 연결 불일치" and not result.id
    else:
        assert result == cases[status]


@pytest.mark.parametrize("minimum,maximum,expected", [
    (100, None, {"min": 100}), (70, 85, {"min": 70, "max": 85}),
    (None, 90, {"max": 90}), (None, None, {}),
])
def test_r4_count_empty_uses_roll_not_edited_bounds(monkeypatch, minimum, maximum, expected):
    text = "Curse Enemies with Flammability on Hit"
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", frozenset())
    assert not index().match(text, "explicit", "Ring").id
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", {"R4"})
    match = index().match(text, "explicit", "Ring")
    assert match.value == 100
    info = item_info(parse("Item Class: Rings\nRarity: Rare\nGold Ring\n--------\nItem Level: 83"))
    a = StatCondition(text, "explicit", match, True, minimum, maximum)
    b = replace(a, match=replace(match, invert=True))
    groups = build_query(info, [a, b])["query"]["stats"]
    assert groups[0] == {"type": "and", "filters": []}
    assert len(groups) == 3
    for group, bounds in zip(groups[1:], (expected, {("max" if key == "min" else "min"): -v
                                                   for key, v in expected.items()})):
        assert (group["type"], group["value"]) == ("count", {"min": 1})
        assert group["filters"] == [
            {"id": "explicit.stat_654274615", "value": bounds, "disabled": False},
            {"id": "explicit.stat_338121249", "value": {}, "disabled": False},
        ]


def test_r2_is_gated_and_korean_representative_has_unresolved_mismatch(monkeypatch):
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", frozenset())
    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", frozenset())
    en = "20% Chance to Block Attack Damage"
    ko = "공격 피해 막기 확률 +20%"
    assert not index().match(en, "explicit", "ARMOUR").id
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", {"R2", "R4"})
    match = index().match(en, "explicit", "ARMOUR")
    assert set(match.ids) == {"explicit.stat_2530372417", "explicit.stat_1702195217"}
    assert index().bilingual(ko, en, "explicit", "ARMOUR").reason == "한국어·번역 연결 불일치"
    assert not index().match("+1 to Level of all Raise Spectre Gems", "explicit", "ARMOUR").id
    assert not index().match("Gain a Flask Charge when you deal a Critical Strike", "explicit", "ARMOUR").id


def test_r2_first_agreeing_candidate_requires_both_paths(monkeypatch):
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", frozenset())
    idx = index()
    candidates = [
        "주문 피해 막기 확률 +20%", "인내 충전 하나당 공격 피해 막기 확률 +1%",
        "처치 시 마나의 6% 회복", "경험치 획득 3% 증가",
    ]
    translations = [mod_en(ItemModel("ko", []), Mod(text)) for text in candidates]
    assert "불일치" in idx.bilingual(candidates[0], translations[0], "explicit", "ARMOUR").reason
    assert idx.bilingual(candidates[1], translations[1], "explicit", "ARMOUR").reason == "브라우저 확인 대기: R2"
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", {"R2"})
    agreeing = [text for text, en in zip(candidates, translations) if idx.bilingual(text, en, "explicit", "ARMOUR").ids]
    assert agreeing == candidates[1:]
    assert not idx.bilingual(candidates[1], None, "explicit", "ARMOUR").id
    assert not idx.bilingual("", translations[1], "explicit", "ARMOUR").id
