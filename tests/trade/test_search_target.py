import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QScrollArea

from itemmodel import parse
from trade import browser, config, heist, items
from trade.query import CATEGORY_LABELS, TradeItem, build_query, item_info, search_target
from trade.trade_window import TradeWindow


RING = """아이템 종류: 반지
아이템 희귀도: 희귀
검사 반지
토파즈 반지
--------
아이템 레벨: 83
--------
생명력 최대치 +30
--------
번개 저항 +20% (implicit)
--------
지원하지 않는 옵션 17% 증가
--------
쉐이퍼 아이템
"""


def test_nightmare_map_title_matches_exact_payload(app, fixtures):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    text = (fixtures / "fix004_nightmare_map_ko.txt").read_text(encoding="utf-8")
    window = TradeWindow()
    window.load(text.replace("고대의 연결부", "경악의 선택"))
    assert window.target_caption.text() == "검색 대상"
    assert window.title.text() == "악몽 지도"
    assert window.scope_badge.text() == "정확한 베이스"
    assert window.copied_item.text() == "복사한 이름: 경악의 선택 · 검색에 사용하지 않음"
    assert window.base_button.isHidden()
    assert build_query(window.info, []) == {
        "query": {
            "status": {"option": "securable"},
            "type": "악몽 지도",
            "stats": [{"type": "and", "filters": []}],
            "filters": {
                "misc_filters": {"filters": {"corrupted": {"option": "false"}}},
                "type_filters": {"filters": {"rarity": {"option": "nonunique"}}},
                "map_filters": {"filters": {"map_blighted": {"option": "false"}}},
            },
        },
        "sort": {"price": "asc"},
    }
    window.close()


@pytest.mark.parametrize("mode", ["api", "browser"])
def test_conqueror_map_with_ellipses_retains_exact_identity_and_monster_level(app, fixtures, mode):
    config.save(server=config.KAKAO, mode=mode, league="Standard")
    text = (fixtures / "conqueror_map_ko.txt").read_text(encoding="utf-8")
    window = TradeWindow()
    try:
        window.load(text)
        assert window.info.supported, window.info.message
        assert all("시타델" not in condition.text and "몬스터 레벨:" not in condition.text for condition in window.stats)
        assert not window.monster_level.isHidden() and not window.monster_level.isChecked()
        assert window.monster_level.text() == "몬스터 레벨 = 83"
        assert "area_level" not in window._query()["query"]["filters"]["map_filters"]["filters"]
        window.monster_level.click()
        query = window._query()["query"]
        assert query["type"] == {"option": "지도", "discriminator": "map"}
        assert query["filters"]["map_filters"]["filters"]["area_level"] == {"min": 83, "max": 83}
        assert query["filters"]["map_filters"]["filters"]["map_tier"] == {"min": 16, "max": 16}
        assert "ilvl" not in query["filters"]["misc_filters"]["filters"]
        assert [s for s in query["stats"][0]["filters"] if s["id"].startswith("implicit.")] == [
            {"id": "implicit.stat_2563183002|2"},
        ]
        window.load(text.replace("베리타니아", "미확인 정복자"))
        assert not window.info.supported
    finally:
        window.close()


@pytest.mark.parametrize("server,base", [(config.KAKAO, "쉐이퍼 수호자 지도"), (config.OFFICIAL, "Shaper Guardian Map")])
def test_shaper_guardian_map_matches_verified_kakao_query(app, fixtures, server, base):
    config.save(server=server, mode="browser", league="Standard")
    window = TradeWindow()
    try:
        window.load((fixtures / "shaper_guardian_map_ko.txt").read_text(encoding="utf-8"))
        assert window.info.supported, window.info.message
        assert window.title.text() == base
        assert all("쉐이퍼의 영향" not in condition.text for condition in window.stats)
        query = window._query()["query"]
        assert query["type"] == base
        assert query["filters"]["type_filters"]["filters"] == {"rarity": {"option": "nonunique"}}
        assert query["filters"]["map_filters"]["filters"] == {"map_blighted": {"option": "false"}}
        identity = [s for s in query["stats"][0]["filters"] if s["id"].startswith("implicit.")]
        assert identity == [{"id": "implicit.stat_1792283443|1"}]
        window.monster_level.click()
        assert window._query()["query"]["filters"]["map_filters"]["filters"]["area_level"] == {"min": 83, "max": 83}
    finally:
        window.close()


def test_trade_window_keeps_copied_option_order_including_unmatched_rows(app):
    config.save(server=config.KAKAO, mode="api", league="Standard")
    window = TradeWindow()
    try:
        window.load(RING)
        window.show()
        app.processEvents()
        checks = sorted((check for check, _, _ in window.inputs),
                        key=lambda check: check.mapTo(window, QPoint()).y())
        assert [check.text() for check in checks] == [
            "생명력 최대치 +30", "번개 저항 +20%", "지원하지 않는 옵션 17% 증가",
        ]
        assert not checks[-1].isEnabled()
    finally:
        window.close()


def test_scope_toggle_updates_title_even_when_bounds_are_invalid(app):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    window = TradeWindow()
    window.load(RING)
    assert window.title.text() == "반지"
    assert window.scope_badge.text() == "반지 전체"
    assert "검색에 사용하지 않음" in window.copied_item.text()
    assert window._query()["query"]["filters"]["type_filters"]["filters"]["category"] == {"option": "accessory.ring"}
    _, lo, hi = window.inputs[0]
    lo.setText("10")
    hi.setText("1")
    assert not window.search_button.isEnabled()
    window.base_button.click()
    assert window.title.text() == "토파즈 반지"
    assert window.scope_badge.text() == "정확한 베이스"
    assert window.base_button.text() == "반지 전체로 전환"
    assert not window.search_button.isEnabled()
    hi.clear()
    assert window._query()["query"]["type"] == "토파즈 반지"
    window.close()


@pytest.mark.parametrize("category,label", [
    ("weapon.onesword", "한손 검"), ("jewel", "주얼"), ("jewel.abyss", "어비스 주얼"),
    ("jewel.cluster", "성단 주얼"), ("heistmission.contract", "계약"),
    ("heistmission.blueprint", "도면"), ("unknown.category", "unknown.category"),
])
def test_search_target_uses_confirmed_korean_category_labels(category, label):
    assert search_target(TradeItem(None, supported=True, equipment_category=category)).label == label


def test_category_labels_cover_exactly_the_supported_trade_ids():
    assert CATEGORY_LABELS.keys() == set(items.EQUIPMENT_TRADE_IDS.values()) | set(heist.CATEGORIES.values())


@pytest.mark.parametrize("fixture,label,toggle_label,checked", [
    ("heist_contract_ko.txt", "계약", "계약 전체로 전환", False),
    ("heist_blueprint_ko.txt", "도면: 취약 지점", "정확한 베이스로 전환: 도면: 취약 지점", True),
])
def test_heist_title_respects_scope_defaults(app, fixtures, fixture, label, toggle_label, checked):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    window = TradeWindow()
    window.load((fixtures / fixture).read_text(encoding="utf-8"))
    assert window.title.text() == label
    assert window.base_button.isChecked() == checked
    if checked:
        assert "검색에 사용하지 않음" not in window.copied_item.text()
    assert ("type" in window._query()["query"]) == checked
    window.base_button.click()
    assert window.base_button.text() == toggle_label
    assert ("type" in window._query()["query"]) != checked
    window.close()


def test_unique_gem_and_unsupported_targets(app, fixtures):
    config.save(server=config.OFFICIAL, mode="browser", league="Standard")
    window = TradeWindow()
    text = "아이템 종류: 지도\n아이템 희귀도: 고유\n겁쟁이의 시험\n지도 (8등급)\n--------\n아이템 레벨: 75"
    window.load(text)
    assert window.title.text() == "The Coward's Trial · Map"
    assert window.scope_badge.text() == "고유"
    assert window.copied_item.text() == "복사한 이름: 겁쟁이의 시험"
    query = window._query()["query"]
    assert query["name"] == {"option": "The Coward's Trial", "discriminator": "map"}
    assert query["type"] == {"option": "Map", "discriminator": "map"}
    gem = (fixtures / "fix004_support_gem_ko.txt").read_text(encoding="utf-8")
    window.load(gem)
    assert window.title.text() == "Trap and Mine Damage Support"
    assert window.scope_badge.text() == "젬"
    assert window.copied_item.text() == "복사한 이름: 덫 및 지뢰 피해 보조"
    assert window._query()["query"]["type"] == "Trap and Mine Damage Support"
    assert not window.clear_all.isHidden() and window.clear_all.isEnabled()
    window.load(gem.replace("덫 및 지뢰 피해 보조", "미지원 젬"))
    assert window.title.text() == "검색할 수 없음"
    assert window.scope_badge.isHidden()
    assert window.select_all.isHidden() and window.clear_all.isHidden()
    window.close()


@pytest.mark.parametrize("fixture", [None, "fix004_support_gem_ko.txt", "heist_blueprint_ko.txt"])
def test_bulk_actions_only_change_enabled_option_checks(app, fixtures, monkeypatch, fixture):
    opened = []
    monkeypatch.setattr(browser, "open_url", opened.append)
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    text = RING if fixture is None else (fixtures / fixture).read_text(encoding="utf-8")
    window = TradeWindow()
    window.load(text)
    enabled = [check for check, _, _ in window.inputs if check.isEnabled()]
    disabled = [(check, check.isChecked()) for check, _, _ in window.inputs if not check.isEnabled()]
    controls = [window.corrupted, window.base_button, window.ilvl, window.links, *window.influence_inputs.values()]
    assert len(enabled) >= 2
    if fixture is None:
        assert disabled and window.influence_inputs
    state = [check.isChecked() for check in controls]
    bounds = [(lo.text(), hi.text()) for _, lo, hi in window.inputs]
    for button, checked in ((window.clear_all, False), (window.select_all, True)):
        generation = window._generation
        assert button.isEnabled()
        button.click()
        assert window._generation == generation + 1 and not button.isEnabled()
        assert all(check.isChecked() == checked for check in enabled)
        assert all(check.isChecked() == original for check, original in disabled)
        assert [(lo.text(), hi.text()) for _, lo, hi in window.inputs] == bounds
        assert [check.isChecked() for check in controls] == state
        assert not opened
    enabled[0].click()
    assert window.select_all.isEnabled()
    window.close()


@pytest.mark.parametrize("mode", ["api", "browser"])
def test_narrow_trade_window_has_scrollable_rows_and_keyboard_access(app, mode):
    config.save(server=config.KAKAO, mode=mode, league="Standard")
    text = RING.replace("검사 반지", "길게 복사한 아이템 이름 " * 10).replace(
        "지원하지 않는 옵션", "매우 긴 한글 옵션 이름 " * 10)
    window = TradeWindow()
    window.load(text)
    window.resize(390, 580)
    window.show()
    app.processEvents()
    assert window.width() == 390
    assert window.search_button.geometry().bottom() < window.height()
    assert window.title.fontMetrics().height() > window.target_caption.fontMetrics().height()
    scroll = window.findChild(QScrollArea)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert window.copied_item.height() > window.copied_item.fontMetrics().height()
    assert all(label.width() <= window.width() for label in window.findChildren(QLabel) if label.isVisible())
    for check, lo, hi in window.inputs:
        assert check.width() > 0 and lo.accessibleName() and hi.accessibleName()
        assert hi.geometry().right() < hi.parentWidget().width()
    window.base_button.setFocus()
    assert window.base_button.hasFocus()
    QTest.keyClick(window.base_button, Qt.Key.Key_Space)
    assert window.title.text() == "토파즈 반지"
    assert not window.grab().isNull()
    window.close()


@pytest.mark.parametrize("server,base", [(config.KAKAO, "금지된 책"), (config.OFFICIAL, "Forbidden Tome")])
def test_forbidden_tome_item_level_search(app, fixtures, server, base):
    config.save(server=server, mode="api", league="Standard")
    text = (fixtures / "forbidden_tome_ko.txt").read_text(encoding="utf-8")
    window = TradeWindow()
    try:
        window.load(text)
        assert window.title.text() == base and not window.ilvl.isHidden()
        assert window.ilvl.isChecked() and window.ilvl.text() == "아이템 레벨 ≥ 85"
        query = window._query()["query"]
        assert query["type"] == base and "name" not in query
        assert query["filters"] == {"misc_filters": {"filters": {"ilvl": {"min": 85}}}}
        assert query["stats"] == [{"type": "and", "filters": []}]
        window.ilvl.click()
        assert window._query()["query"]["filters"] == {}
        window.load(text.replace("아이템 레벨: 85\n--------\n", ""))
        assert window.ilvl.isHidden() and window._query()["query"]["filters"] == {}
        window.load(text.replace("금지된 책", "다른 성역 연구 아이템"))
        assert not window.info.supported
    finally:
        window.close()


@pytest.mark.parametrize("fixture,level", [
    ("rare_en.txt", 86),
    ("magic_en.txt", 50),
    ("unique_en.txt", 75),
    ("fix004_map_ko.txt", 83),
    ("fix004_flask_ko.txt", 80),
    ("heist_contract_ko.txt", 83),
    ("heist_blueprint_ko.txt", 83),
    ("fix004_support_gem_ko.txt", None),
])
def test_supported_items_offer_their_copied_item_level(app, fixtures, fixture, level):
    config.save(server=config.OFFICIAL, mode="browser", league="Standard")
    window = TradeWindow()
    try:
        window.load((fixtures / fixture).read_text(encoding="utf-8"))
        assert window.info.supported, window.info.message
        assert window.ilvl.isHidden() == (level is None)
        assert not window.ilvl.isChecked()
        misc = lambda: window._query()["query"]["filters"]["misc_filters"]["filters"]
        assert "ilvl" not in misc()
        if level is not None:
            assert window.ilvl.text() == f"아이템 레벨 ≥ {level}"
            window.ilvl.click()
            assert misc()["ilvl"] == {"min": level}
    finally:
        window.close()


def test_default_trade_window_fits_six_results(app, fixtures):
    config.save(server=config.KAKAO, mode="api", league="Standard")
    window = TradeWindow()
    window.load((fixtures / "fix004_support_gem_ko.txt").read_text(encoding="utf-8"))
    window.result_summary.setText("전체 20개 · 최저가 9 chaos")
    window.table.setRowCount(20)
    window.show()
    app.processEvents()
    assert window.table.visualRect(window.table.model().index(5, 0)).bottom() < window.table.viewport().height()
    assert window.search_button.geometry().bottom() < window.height()
    window.close()


@pytest.mark.parametrize("server", [config.OFFICIAL, config.KAKAO])
@pytest.mark.parametrize("mode", ["api", "browser"])
def test_serverless_header_preserves_mode_and_canonical_target(app, server, mode):
    config.save(server=server, mode=mode, league="Standard")
    window = TradeWindow()
    ring = "아이템 종류: 반지\n아이템 희귀도: 마법\n차원의 토파즈 반지 - 레인저\n--------\n아이템 레벨: 83"
    window.load(ring)
    assert window.server == server and window.current_mode == mode
    assert window.league.currentText() == "Standard"
    assert window.mode_label.text() == (
        "POE Delta · 게임 위 시세 모드 (공식 문서 밖 API 사용)" if mode == "api" else "POE Delta · 브라우저 모드"
    )
    assert window.scope_badge.text() == "반지 전체"
    assert window.copied_item.text() == "복사한 이름: 차원의 토파즈 반지 - 레인저"
    window.base_button.click()
    base = "Topaz Ring" if server == config.OFFICIAL else "토파즈 반지"
    assert window.title.text() == base == window._query()["query"]["type"]
    assert window.copied_item.text() == "복사한 이름: 차원의 토파즈 반지 - 레인저"
    window.load(ring.replace("마법", "일반").replace("차원의 토파즈 반지 - 레인저", "상급 토파즈 반지"))
    window.base_button.click()
    assert window.title.text() == base
    assert window.copied_item.text() == "복사한 이름: 상급 토파즈 반지"
    window.close()
