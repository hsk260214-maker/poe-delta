from dataclasses import replace

import pytest
from PySide6.QtWidgets import QPushButton

from itemmodel import parse
from trade import combine, config
from trade.query import StatCondition, build_query, conditions, default_minimum, item_info, resistance_rows
from trade.stats import Match
from trade.trade_window import TradeWindow


LIFE = "explicit.stat_3299347043"
FRACTURED = "fractured.stat_3299347043"
TEXT = ("Item Class: Rings\nRarity: Rare\nGold Ring\n--------\nItem Level: 83\n--------\n"
        '{ Prefix Modifier "Healthy" }\n+10 to maximum Life\n'
        '{ Suffix Modifier "of the Fox" }\n+5 to Dexterity\n'
        '{ Prefix Modifier "Healthy" }\n+20 to maximum Life\n')


def merged(rows, ratio=0.9):
    return combine.apply(rows, ratio, default_minimum, lang="en", category="Ring")


@pytest.fixture(autouse=True)
def allowlist_only(monkeypatch):
    monkeypatch.setattr(combine, "OPEN_ALL", False)


def test_open_all_sums_eligible_rows_without_allowlist(monkeypatch):
    monkeypatch.setattr(combine, "OPEN_ALL", True)
    monkeypatch.setattr(combine, "VERIFIED", frozenset())
    info = item_info(parse(TEXT))
    total, other = merged(conditions(info))
    assert (total.text, total.badge, total.minimum) == ("+30 to maximum Life", "일반 · 합산", 27)
    assert other.text == "+5 to Dexterity"


def test_empty_or_unrelated_allowlist_preserves_rows(monkeypatch):
    info = item_info(parse(TEXT))
    rows = conditions(info)
    for keys in (frozenset(), {("explicit", "explicit.stat_1")}, {("fractured", FRACTURED)}):
        monkeypatch.setattr(combine, "VERIFIED", keys)
        assert merged(rows) == rows
        assert build_query(info, merged(rows)) == build_query(info, rows)


def test_total_uses_copy_values_at_first_position(monkeypatch):
    monkeypatch.setattr(combine, "VERIFIED", {("explicit", LIFE)})
    info = item_info(parse(TEXT))
    rows = conditions(info)
    assert len(rows) == 3
    rows[0].minimum = 1
    total, other = merged(rows, 0.8)
    assert other is rows[1]
    assert (total.text, total.badge, total.sources, total.minimum, total.detail) == (
        "+30 to maximum Life", "일반 · 합산", ("+10 to maximum Life", "+20 to maximum Life"), 24, "",
    )
    result = build_query(info, [total, other])["query"]["stats"][0]["filters"]
    assert [f for f in result if f["id"] == LIFE] == [{"id": LIFE, "value": {"min": 24}}]


@pytest.mark.parametrize("row_change,match_change", [
    ({"kind": "crafted"}, {}), ({}, {"ids": (LIFE, "explicit.stat_1")}),
    ({}, {"rolls": ("10", "10")}), ({}, {"rolls": ("10.0",)}), ({}, {"rolls": ("-10",)}),
    ({}, {"rolls": ("0",)}), ({}, {"negate": True}), ({}, {"invert": True}),
    ({}, {"inverted": True}), ({}, {"value": 10}),
    ({"combinable": False}, {}), ({"checked": False}, {}),
    ({}, {"ref": "+#% to Cold Resistance"}), ({}, {"ref": "+#% to All Resistances"}),
    ({"kind": "elemental_resistance_total"}, {}),
    ({"kind": "heist_area"}, {}), ({"kind": "gem_filter"}, {}), ({"kind": "viscera_tier"}, {}),
    ({"detail": "합치면 안 되는 두 줄"}, {}), ({}, {"alternate_id": ""}),
    ({}, {"verified_korean_block_id": LIFE}),
])
def test_separate_rows_for_excluded_values_and_roles(monkeypatch, row_change, match_change):
    row = StatCondition("+10 to maximum Life", "explicit", Match(LIFE, alternate_id=FRACTURED, rolls=("+10",)), True)
    other = replace(row, match=replace(row.match, **match_change), **row_change)
    monkeypatch.setattr(combine, "VERIFIED", {(row.kind, LIFE), (other.kind, LIFE)})
    assert merged([row, other]) == [row, other]


def test_gear_only_metadata_excludes_grant_reduced_and_destiny(fixtures):
    grant = conditions(item_info(parse(TEXT.replace("+10 to maximum Life", "Grants Level 20 Anger Skill"))))[0]
    reduced = conditions(item_info(parse(TEXT.replace("+10 to maximum Life", "10% reduced Attack Speed"))))[0]
    destiny = conditions(item_info(parse((fixtures / "bound_by_destiny_ko.txt").read_text(encoding="utf-8"))))
    assert not grant.combinable and not reduced.combinable
    assert destiny and all(not row.combinable for row in destiny)


def test_sum_preserves_elemental_source_and_aggregate_position(monkeypatch):
    monkeypatch.setattr(combine, "VERIFIED", {("explicit", LIFE)})
    info = item_info(parse(TEXT + "+13% to Fire Resistance\n+18% to Cold Resistance"))
    rows = conditions(info)
    before, _ = resistance_rows(info, rows)
    after, _ = resistance_rows(info, merged(rows))
    for options in (before, after):
        total = next(i for i, row in enumerate(options) if row.badge == "합산")
        assert options[total].text == "총 원소 저항 +31%"
        assert options[total + 1].text == "+13% to Fire Resistance"
    assert before[-2:] == after[-2:]


def test_merged_row_is_editable_and_only_verified_kind_can_switch(app, monkeypatch):
    monkeypatch.setattr(combine, "VERIFIED", {("explicit", LIFE)})
    config.save(mode="browser", server=config.OFFICIAL, league="Standard")
    window = TradeWindow()
    try:
        window.load(TEXT)
        combined = window.stats[0]
        check, lo, hi = window.inputs[0]
        switch = next(b for b in check.parentWidget().findChildren(QPushButton) if b.text() == "종류 전환")
        assert check.toolTip() == "+10 to maximum Life\n+20 to maximum Life"
        assert check.isEnabled() and not lo.isHidden() and not hi.isHidden()
        assert not switch.isEnabled()
        combined.switch_kind()
        assert combined.kind == "explicit"
        lo.setText("22")
        hi.setText("35")
        assert window._query()["query"]["stats"][0]["filters"][0] == {
            "id": LIFE, "value": {"min": 22, "max": 35},
        }
        check.click()
        assert all(f["id"] != LIFE for f in window._query()["query"]["stats"][0]["filters"])
        monkeypatch.setattr(combine, "VERIFIED", {("explicit", LIFE), ("fractured", FRACTURED)})
        window.load(TEXT)
        check = window.inputs[0][0]
        switch = next(b for b in check.parentWidget().findChildren(QPushButton) if b.text() == "종류 전환")
        assert switch.isEnabled()
        switch.click()
        assert window.stats[0].badge == "분열 · 합산"
        assert window._query()["query"]["stats"][0]["filters"][0] == {
            "id": FRACTURED, "value": {"min": 27},
        }
    finally:
        window.close()
