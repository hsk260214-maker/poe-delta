import pytest
from PySide6.QtCore import Qt
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
    assert window.title.text() == "검색 대상: 악몽 지도"
    assert window.copied_item.text() == "복사한 아이템: 경악의 선택"
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


def test_scope_toggle_updates_title_even_when_bounds_are_invalid(app):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    window = TradeWindow()
    window.load(RING)
    assert window.title.text() == "검색 대상: 반지"
    assert window._query()["query"]["filters"]["type_filters"]["filters"]["category"] == {"option": "accessory.ring"}
    _, lo, hi = window.inputs[0]
    lo.setText("10")
    hi.setText("1")
    assert not window.search_button.isEnabled()
    window.base_button.click()
    assert window.title.text() == "검색 대상: 토파즈 반지"
    assert window.base_button.text() == "정확한 베이스: 토파즈 반지"
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
    ("heist_contract_ko.txt", "계약", "정확한 베이스: 계약: 벙커", False),
    ("heist_blueprint_ko.txt", "도면: 취약 지점", "도면 전체 검색", True),
])
def test_heist_title_respects_scope_defaults(app, fixtures, fixture, label, toggle_label, checked):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    window = TradeWindow()
    window.load((fixtures / fixture).read_text(encoding="utf-8"))
    assert window.title.text() == f"검색 대상: {label}"
    assert window.base_button.isChecked() == checked
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
    assert window.title.text() == "검색 대상: The Coward's Trial · Map"
    query = window._query()["query"]
    assert query["name"] == {"option": "The Coward's Trial", "discriminator": "map"}
    assert query["type"] == {"option": "Map", "discriminator": "map"}
    gem = (fixtures / "fix004_support_gem_ko.txt").read_text(encoding="utf-8")
    window.load(gem)
    assert window.title.text() == "검색 대상: Trap and Mine Damage Support"
    assert window._query()["query"]["type"] == "Trap and Mine Damage Support"
    assert not window.clear_all.isHidden() and window.clear_all.isEnabled()
    window.load(gem.replace("덫 및 지뢰 피해 보조", "미지원 젬"))
    assert window.title.text() == "검색 대상: 검색할 수 없음"
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


def test_narrow_trade_window_has_scrollable_rows_and_keyboard_access(app):
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    text = RING.replace("검사 반지", "길게 복사한 아이템 이름 " * 10).replace(
        "지원하지 않는 옵션", "매우 긴 한글 옵션 이름 " * 10)
    window = TradeWindow()
    window.load(text)
    window.resize(390, 580)
    window.show()
    app.processEvents()
    assert window.width() == 390
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
    assert window.title.text() == "검색 대상: 토파즈 반지"
    assert not window.grab().isNull()
    window.close()
