import pytest

from trade import config, viscera
from trade.query import build_query, conditions, item_info
from trade.trade_window import TradeWindow
from itemmodel import parse

SKULL = "하위 이글거리는 두개골"
TIER = {"id": "implicit.stat_2137878565", "value": {"min": 20, "max": 30}}


@pytest.fixture
def skull(fixtures):
    return (fixtures / "viscera_lesser_blazing_skull_ko.txt").read_text(encoding="utf-8")


def test_unverified_viscera_shows_identity_but_cannot_search(app, monkeypatch, skull):
    monkeypatch.setattr(viscera, "VERIFIED_TIERS", frozenset())
    config.save(server=config.KAKAO, mode="api", league="Standard")
    window = TradeWindow()
    try:
        window.load(skull)
        window._validate()
        assert window.title.text() == "이글거리는 두개골"
        assert window.copied_item.text() == "하위 · 머리"
        assert window.hint.text() == "아직 확인되지 않은 살덩이 종류입니다"
        assert not window.search_button.isEnabled()
        assert [c.kind for c in window.stats] == ["viscera_tier"]
    finally:
        window.close()


@pytest.mark.parametrize("server,base", [(config.KAKAO, "이글거리는 두개골"), (config.OFFICIAL, "Blazing Skull")])
def test_verified_lesser_skull_always_sends_tier_band_once(skull, server, base):
    info = item_info(parse(skull), server)
    assert info.supported, info.message
    assert build_query(info, [])["query"] == {
        "status": {"option": "securable"}, "type": base,
        "stats": [{"type": "and", "filters": [TIER]}], "filters": {},
    }
    stats = conditions(info)
    stats[0].checked = False
    assert build_query(info, stats)["query"]["stats"][0]["filters"] == [TIER]


def test_window_keeps_band_after_bulk_clear_and_validates_bounds(app, skull):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    window = TradeWindow()
    try:
        window.load(skull)
        check, minimum, maximum = window.inputs[0]
        assert check.isChecked() and not check.isEnabled()
        assert (minimum.text(), maximum.text()) == ("20", "30")
        assert window.ilvl.text() == "아이템 레벨 ≥ 38" and not window.ilvl.isChecked()
        assert window.corrupted.isHidden()
        window._set_all_options(False)
        assert window._query()["query"]["stats"][0]["filters"] == [TIER]
        minimum.setText("25")
        assert window._query()["query"]["stats"][0]["filters"][0]["value"] == {"min": 25, "max": 30}
        minimum.clear()
        assert window._query()["query"]["stats"][0]["filters"][0]["value"] == {"min": 20, "max": 30}
        for low, high in (("19", "30"), ("20", "31"), ("28", "22"), ("2.5", "30")):
            minimum.setText(low)
            maximum.setText(high)
            with pytest.raises(ValueError):
                window._query()
    finally:
        window.close()


def test_unknown_viscera_is_blocked(skull):
    info = item_info(parse(skull.replace(SKULL, "여왕 이글거리는 두개골")), config.KAKAO)
    assert not info.supported and info.message == "아직 지원하지 않는 살덩이입니다"


@pytest.mark.parametrize("name,line,stat_id,band", [
    ("하위 잘린 로아 머리", "카오스 피해 14% 증가", "implicit.stat_736967255", (10, 15)),
    ("하위 간수의 팔", "생명력 최대치 +45", "implicit.stat_3299347043", (30, 50)),
])
def test_other_verified_lesser_viscera_use_catalog_band(skull, name, line, stat_id, band):
    text = skull.replace(SKULL, name).replace("희귀 몬스터 명중 시 피해 30(20-30)% 증가", line)
    slot = next(row.slot for row in viscera.rows() if row.name == name.removeprefix("하위 "))
    info = item_info(parse(text.replace("\n머리\n", f"\n{slot}\n")), config.KAKAO)
    assert info.supported, info.message
    assert build_query(info, conditions(info))["query"]["stats"][0]["filters"] == [
        {"id": stat_id, "value": {"min": band[0], "max": band[1]}}]


def test_lesser_viscera_with_out_of_band_value_is_blocked(skull):
    info = item_info(parse(skull.replace("피해 30(20-30)%", "피해 45%")), config.KAKAO)
    assert not info.supported and info.message == "살덩이 단계를 확인할 수 없습니다"


def test_greater_skull_uses_ranged_number_and_ignores_price_note(fixtures):
    text = (fixtures / "viscera_greater_blazing_skull_ko.txt").read_text(encoding="utf-8")
    info = item_info(parse(text), config.KAKAO)
    assert info.supported and info.viscera.tier == "High", info.message
    stats = conditions(info)
    assert [c.kind for c in stats] == ["viscera_tier"]
    assert build_query(info, stats)["query"]["stats"][0]["filters"] == [
        {"id": "implicit.stat_2736829661", "value": {"min": 20, "max": 30}}]


@pytest.mark.parametrize("name,stat_id", [
    ("상위 간수의 팔", "implicit.stat_1214601201"),
    ("여왕의 간수의 팔", "implicit.stat_137377270"),
    ("간수의 팔", "implicit.stat_137377270"),
])
def test_queen_and_greater_share_text_but_not_trade_id(skull, name, stat_id):
    text = skull.replace(SKULL, name).replace("\n머리\n", "\n상지\n").replace(
        "희귀 몬스터 명중 시 피해 30(20-30)% 증가", "최대 생명력 6% 증폭")
    info = item_info(parse(text), config.KAKAO)
    assert info.supported, info.message
    assert build_query(info, conditions(info))["query"]["stats"][0]["filters"] == [
        {"id": stat_id, "value": {"min": 5, "max": 7}}]
    assert not item_info(parse(text.replace("최대 생명력 6% 증폭", "생명력 최대치 +45")), config.KAKAO).supported
