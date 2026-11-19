import json
from datetime import datetime, timezone

import pytest

from itemmodel import Mod, parse
from trade import browser, config
from trade.query import (StatCondition, build_query, conditions, default_minimum,
                         item_info, league_for, result_rows, summary)
from trade.stats import index


@pytest.mark.parametrize("language", ["en", "ko"])
@pytest.mark.parametrize("rarity", ["rare", "unique"])
def test_golden_queries_and_links(fixtures, language, rarity):
    model = parse((fixtures / f"{rarity}_{language}.txt").read_text(encoding="utf-8"))
    expected = json.loads((fixtures / f"{rarity}_expected.json").read_text(encoding="utf-8"))
    info = item_info(model)
    assert info.supported
    assert build_query(info, conditions(info), exact_base=True) == expected
    for server in (config.OFFICIAL, config.KAKAO) if language == "ko" else (config.OFFICIAL,):
        info = item_info(model, server)
        correct = json.loads(json.dumps(expected))
        if server == config.KAKAO:
            correct["query"]["type"] = model.base
            if rarity == "unique":
                correct["query"]["name"] = model.name
        actual = build_query(info, conditions(info), exact_base=True)
        assert actual == correct
        links = json.loads((fixtures / "browser_links.json").read_text(encoding="utf-8"))
        expected_url = links[f"{rarity}_{language}_{'kakao' if server == config.KAKAO else 'official'}"]
        assert browser.build_url("Standard", actual, server, language) == expected_url


@pytest.mark.parametrize("text,category,stat_id", [
    ("+100 to Armour", "ARMOUR", "explicit.stat_3484657501"),
    ("+100 to Armour", "Ring", "explicit.stat_809229260"),
    ("10% increased Attack Speed", "WEAPON", "explicit.stat_210067635"),
    ("10% increased Attack Speed", "Ring", "explicit.stat_681332047"),
])
def test_select(text, category, stat_id):
    assert index().match(text, "explicit", category).id == stat_id


@pytest.mark.parametrize("text,reason", [
    ("Intimidate Enemies for 4 seconds on Hit", "거래소 옵션과 맞추지 못함"),
    ("2 Added Passive Skill is a Jewel Socket", "거래소 옵션과 맞추지 못함"),
    ("10% chance to Avoid being Chilled during Effect", "이번 버전은 미지원 옵션"),
    ("10% chance to Curse Enemies with Elemental Weakness on Hit", "이번 버전은 미지원 옵션"),
    ("10% to Maximum Effect of Shock", "이번 버전은 미지원 옵션"),
    ("not a known modifier", "거래소 옵션과 맞추지 못함"),
])
def test_unsupported_matchers(text, reason):
    result = index().match(text, "explicit", "WEAPON")
    assert not result.id
    assert result.reason == reason


@pytest.mark.parametrize("text,stat_id", [
    ("Projectiles Pierce an additional Target", "explicit.stat_2067062068"),
    ("Ignites you inflict deal Damage 12% [DamageFaster|Faster]", None),
])
def test_fixed_value_and_markup_lines_match(text, stat_id):
    result = index().match(text, "explicit", "Quiver")
    assert result.id.startswith("explicit.")
    if stat_id:
        assert (result.id, result.value) == (stat_id, 1)


def test_cross_place_ambiguity():
    stat_index = index()
    ambiguous = []
    for text, matchers in stat_index.by_skeleton.items():
        places = {("g", stat_index.entries[m["entry"]]["group"]) if stat_index.entries[m["entry"]]["group"] is not None
                  else ("e", m["entry"]) for m in matchers}
        if len(places) > 1:
            ambiguous.append(text)
            assert stat_index.match(text, "explicit", "ARMOUR").reason == "후보가 여러 개"
    assert len(ambiguous) == 26


@pytest.mark.parametrize("text,invert", [
    ("10% reduced Movement Speed", True),
    ("10% reduced Action Speed", True),
    ("10% increased Action Speed", False),
])
@pytest.mark.parametrize("minimum,maximum", [(10, None), (None, 20), (10, 20), (None, None)])
def test_inverted_xor_negate(fixtures, text, invert, minimum, maximum):
    info = item_info(parse((fixtures / "rare_en.txt").read_text()))
    matched = index().match(text, "explicit", "ARMOUR")
    assert matched.id
    assert matched.invert == invert
    stat = StatCondition(text, "explicit", matched, True, minimum, maximum)
    actual = build_query(info, [stat])["query"]["stats"][0]["filters"][0]
    expected = {}
    if minimum is not None:
        expected["max" if invert else "min"] = -minimum if invert else minimum
    if maximum is not None:
        expected["min" if invert else "max"] = -maximum if invert else maximum
    assert actual.get("value", {}) == expected


@pytest.mark.parametrize("text,expected", [
    ("+100 to maximum Life", 90), ("Adds 10 to 20 Fire Damage", 13),
    ("1.9% increased Attack Speed", 1.7), ("-10 to maximum Life", None),
    ("0% increased Attack Speed", None), ("10% less Damage", None),
    ("10% reduced Movement Speed", None), ("Cannot be Frozen", None),
])
def test_default_minimum(text, expected):
    assert default_minimum(text) == expected


def test_unsupported_items(fixtures):
    info = item_info(parse((fixtures / "currency_ko.txt").read_text(encoding="utf-8")))
    assert not info.supported
    with pytest.raises(ValueError, match="지원하지 않습니다"):
        build_query(info, [])


def test_gem_unidentified_and_mod_kinds(fixtures):
    text = (fixtures / "rare_en.txt").read_text()
    assert not item_info(parse(text + "\n--------\nUnidentified")).supported
    assert not item_info(parse(text.replace("Body Armours", "Skill Gems"))).supported
    for kind in ("scourge", "crucible"):
        assert index().match("+100 to maximum Life", kind, "ARMOUR").reason == "이번 버전은 미지원 종류"
    info = item_info(parse(text))
    assert build_query(info, [], ilvl=True)["query"]["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 86}


def test_league_priority():
    assert league_for({"type": "account", "character": {"league": "Hardcore"}}, "Standard") == "Hardcore"
    assert league_for({"type": "code", "character": {"league": "Hardcore"}}, "Standard") == "Standard"
    assert league_for(None, "") == ""


def test_rows_and_summary(fixtures):
    rows = result_rows(json.loads((fixtures / "fetch.json").read_text()), datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc))
    assert rows[0] == {"amount": 2, "currency": "chaos", "seller": "seller1", "age": "10분 전", "ilvl": 86, "id": "first"}
    assert summary(50, rows) == "전체 50개 · 최저가 2 chaos · 상위 10개 중간값 2.5 chaos (가장 많은 화폐 기준)"
    assert "검색 결과가 없습니다" in summary(0, [])


def test_browser_missing_league_and_length(fixtures, monkeypatch):
    expected = json.loads((fixtures / "rare_expected.json").read_text())
    with pytest.raises(ValueError, match="리그 이름"):
        browser.build_url("", expected)
    url = browser.build_url("Standard", expected)
    monkeypatch.setattr(browser, "MAX_URL_LEN", len(url))
    assert browser.build_url("Standard", expected) == url
    monkeypatch.setattr(browser, "MAX_URL_LEN", len(url) - 1)
    with pytest.raises(ValueError, match="검색 조건이 너무 깁니다"):
        browser.build_url("Standard", expected)
    with pytest.raises(ValueError, match="한글 클라이언트"):
        browser.build_url("Standard", expected, config.KAKAO, "en")
