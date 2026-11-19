from types import SimpleNamespace

import pytest

from itemmodel import Mod, parse
from trade import config, resistance, stats
from trade.query import build_query, conditions, default_minimum, item_info, resistance_rows
from trade.stats import Match
from trade.trade_window import TradeWindow


RING = "Item Class: Rings\nRarity: Rare\nGold Ring\n--------\nItem Level: 83\n--------\n"


def stat_filters(info, rows):
    return build_query(info, rows)["query"]["stats"][0]["filters"]


@pytest.mark.parametrize("text,minimum", [
    ("+1 to maximum Life", 1),
    ("+2 to maximum Life", 1),
    ("+3 to maximum Life", 2),
    ("+1.0 to maximum Life", 0.9),
    ("+0 to maximum Life", None),
    ("-1 to maximum Life", None),
    ("Adds 1 to 1 Fire Damage", 0),
    ("1% reduced Movement Speed", None),
    ("Projectiles Pierce an additional Target", 1),
])
def test_default_minimum_on_matched_row(text, minimum):
    info = item_info(parse(RING + text))
    row, = conditions(info)
    assert row.match.id and row.minimum == minimum
    expected = {"id": row.match.id}
    if minimum is not None:
        expected["value"] = {"min": minimum}
    assert stat_filters(info, [row]) == [expected]
    assert default_minimum("+1") == 0


@pytest.mark.parametrize("sign_flags,payload_bound", [
    ({"invert": True, "inverted": True}, "max"),
    ({"invert": True, "negate": True}, "max"),
    ({"inverted": True, "negate": True}, "min"),
])
def test_one_roll_sign_flags_keep_previous_default(monkeypatch, sign_flags, payload_bound):
    from trade import query

    match = Match("explicit.stat_3299347043", rolls=("1",), **sign_flags)
    monkeypatch.setattr(query, "index", lambda: SimpleNamespace(match=lambda *_: match))
    info = item_info(parse(RING + "+1 to maximum Life"))
    row, = conditions(info)
    assert row.minimum == 0
    assert stat_filters(info, [row]) == [{"id": match.id, "value": {payload_bound: 0}}]


def test_grant_gem_heist_and_aggregate_paths_keep_their_minimum(fixtures, monkeypatch):
    gem = item_info(parse("Item Class: Skill Gems\nRarity: Gem\nFireball\n--------\nLevel: 1"))
    rows = conditions(gem)
    assert [row.minimum for row in rows] == [1, 0]
    assert build_query(gem, rows)["query"]["filters"]["misc_filters"]["filters"]["quality"] == {"min": 0}

    contract = "Item Class: Heist Contracts\nRarity: Rare\nContract: Bunker\n--------\nRequires Lockpicking (Level 1)\n--------\nItem Level: 83"
    info = item_info(parse(contract))
    rows = conditions(info)
    assert build_query(info, rows)["query"]["filters"]["heist_filters"]["filters"]["heist_lockpicking"] == {"min": 1}

    grant = item_info(parse(RING + "Grants Level 1 \u200bAnger"))
    row, = conditions(grant)
    assert row.minimum == 1
    assert stat_filters(grant, [row]) == [{"id": "explicit.effect_2014162730", "value": {"min": 1}}]

    monkeypatch.setattr(resistance, "BROWSER_VERIFIED", True)
    gear = item_info(parse(RING + "+1% to Fire Resistance"))
    rows, _ = resistance_rows(gear, conditions(gear))
    assert rows[0].minimum == 0
    assert build_query(gear, rows, total_resistance=True)["query"]["stats"][0]["filters"] == [
        {"id": "pseudo.pseudo_total_elemental_resistance", "value": {"min": 0}},
    ]


def test_viscera_auxiliary_and_tier_defaults_are_unchanged(fixtures):
    model = parse((fixtures / "viscera_lesser_blazing_skull_ko.txt").read_text(encoding="utf-8"))
    model.mods.append(Mod("1% increased Attack Speed"))
    info = item_info(model, config.KAKAO)
    tier, auxiliary = conditions(info)
    assert (tier.minimum, tier.maximum) == (20, 30)
    assert auxiliary.minimum == 0 and auxiliary.match.id
    auxiliary.checked = True
    assert stat_filters(info, [tier, auxiliary]) == [
        {"id": auxiliary.match.id, "value": {"min": 0}},
        {"id": tier.match.id, "value": {"min": 20, "max": 30}},
    ]


def test_count_and_explicit_user_zero_keep_zero(monkeypatch, app):
    monkeypatch.setattr(stats, "BROWSER_VERIFIED", {"R2"})
    info = item_info(parse(RING + "+1% Chance to Block Attack Damage per Endurance Charge"))
    row, = conditions(info)
    assert row.match.ids and row.minimum == 0
    group = build_query(info, [row])["query"]["stats"][1]
    assert group["type"] == "count"
    assert [member["value"] for member in group["filters"]] == [{"min": 0}, {"min": 0}]

    config.save(mode="browser", server=config.OFFICIAL, league="Standard")
    window = TradeWindow()
    try:
        window.load(RING + "+1 to maximum Life")
        assert window.inputs[0][1].text() == "1"
        window.inputs[0][1].setText("0")
        assert window._query()["query"]["stats"][0]["filters"] == [
            {"id": "explicit.stat_3299347043", "value": {"min": 0}},
        ]
    finally:
        window.close()
