from dataclasses import replace

import pytest
from PySide6.QtWidgets import QPushButton

from itemmodel import parse
from trade import config, stats
from trade.query import build_query, conditions, item_info


SPELL = "explicit.stat_561307714"
ATTACK = "explicit.stat_1702195217"
SPELL_TEXT = "15%의 확률로 주문 피해를 막아냄"
ATTACK_TEXT = "공격 피해 막기 확률 +20%"
SPELL_EN = "15% Chance to Block Spell Damage"


def filters(info, rows):
    return build_query(info, rows)["query"]["stats"]


@pytest.mark.parametrize("fixture,stat_id,minimum", [
    ("block_spell_shield_audit_derived_ko.txt", SPELL, 13),
    ("block_attack_staff_audit_derived_ko.txt", ATTACK, 18),
])
def test_audit_copy_sends_exactly_one_verified_block_filter(fixtures, monkeypatch, fixture, stat_id, minimum):
    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", frozenset())
    info = item_info(parse((fixtures / fixture).read_text(encoding="utf-8")), config.KAKAO)
    grey, = conditions(info)
    assert not grey.match.id
    assert filters(info, [grey]) == [{"type": "and", "filters": []}]
    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", {stat_id})
    row, = conditions(info)
    assert row.match.id == stat_id and row.checked
    assert filters(info, [row]) == [{"type": "and", "filters": [{"id": stat_id, "value": {"min": minimum}}]}]


@pytest.mark.parametrize("kind", ["explicit", "crafted", "implicit", "fractured", "enchant"])
@pytest.mark.parametrize("text,en,explicit_eligible", [
    (SPELL_TEXT, SPELL_EN, True),
    (ATTACK_TEXT, "20% Chance to Block Attack Damage", True),
    ("15%의 확률로 공격 피해를 막아냄", "15% Chance to Block Attack Damage", False),
    ("주문 피해 막기 확률 +15%", SPELL_EN, False),
])
def test_only_the_two_confirmed_explicit_ids_can_open(monkeypatch, kind, text, en, explicit_eligible):
    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", {
        SPELL, ATTACK, "explicit.stat_2530372417", "explicit.stat_19803471", "crafted.stat_561307714",
        "implicit.stat_1702195217", "fractured.stat_561307714",
    })
    matched = stats.index().bilingual(text, en, kind, "ARMOUR")
    assert bool(matched.id) == (kind == "explicit" and explicit_eligible)
    assert not matched.ids


def test_korean_block_cannot_fall_back_on_missing_or_mismatched_paths(monkeypatch):
    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", {SPELL})
    index = stats.index()
    for en in (None, "16% Chance to Block Spell Damage", "15% Chance to Block Attack Damage",
               "15% Chance to Block Attack Damage per Endurance Charge"):
        assert not index.bilingual(SPELL_TEXT, en, "explicit", "ARMOUR").id
    assert not index.bilingual(SPELL_TEXT.replace("주문 피해", "주문  피해"), None, "explicit", "ARMOUR").id
    actual = index.resolve(SPELL_EN, "explicit", "ARMOUR")
    monkeypatch.setattr(index, "resolve", lambda *_: replace(actual, negate=not actual.negate))
    assert not index.bilingual(SPELL_TEXT, SPELL_EN, "explicit", "ARMOUR").id


def test_r2_english_and_unrelated_korean_count_are_unchanged(monkeypatch):
    index = stats.index()
    def matches():
        return (
            index.match(SPELL_EN, "explicit", "ARMOUR"),
            index.bilingual("인내 충전 하나당 공격 피해 막기 확률 +1%",
                            "+1% Chance to Block Attack Damage per Endurance Charge", "explicit", "ARMOUR"),
        )
    original = matches()
    assert all(len(m.ids) == 2 for m in original)
    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", {SPELL, ATTACK})
    assert matches() == original


def test_kind_switch_greys_row_and_shared_query_still_enforces_gate(app, fixtures, monkeypatch):
    from trade.trade_window import TradeWindow

    monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", {SPELL})
    config.save(mode="browser", server=config.KAKAO, league="Standard")
    window = TradeWindow()
    try:
        window.load((fixtures / "block_spell_shield_audit_derived_ko.txt").read_text(encoding="utf-8"))
        row, = window.stats
        check, lo, hi = window.inputs[0]
        switch, = [button for button in window.findChildren(QPushButton) if button.text() == "종류 전환"]
        assert check.isEnabled() and switch.isEnabled()
        switch.click()
        assert row.kind == "fractured" and not check.isEnabled() and not lo.isEnabled() and not hi.isEnabled()
        assert "확인되지 않았습니다" in check.toolTip()
        row.checked = True
        assert filters(window.info, [row]) == [{"type": "and", "filters": []}]
        switch.click()
        assert check.isEnabled() and filters(window.info, [row])[0]["filters"][0]["id"] == SPELL
        monkeypatch.setattr(stats, "BLOCK_BROWSER_VERIFIED", frozenset())
        assert filters(window.info, [row]) == [{"type": "and", "filters": []}]
    finally:
        window.close()
