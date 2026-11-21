import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from itemmodel import parse
from ratelimit import RateLimiter
from trade import api, config, items, trade_window
from trade.query import build_unidentified_unique_query, item_info


def copy_text(lang="ko", level="85", base=None):
    if lang == "ko":
        head = f"아이템 종류: 주얼\n아이템 희귀도: 고유\n{base or '분광 주얼'}"
        level_key, flag = "아이템 레벨", "미확인"
    else:
        head = f"Item Class: Jewels\nRarity: Unique\n{base or 'Prismatic Jewel'}"
        level_key, flag = "Item Level", "Unidentified"
    level_section = f"{level_key}: {level}\n--------\n" if level is not None else ""
    return f"{head}\n--------\n{level_section}{flag}"


@pytest.fixture
def scenario(app, monkeypatch):
    settings = {"mode": "api", "server": config.KAKAO, "league": "Covens"}
    network, opened = [], []
    monkeypatch.setattr(config, "settings", lambda: settings.copy())
    monkeypatch.setattr(config, "save", lambda **changes: settings.update(changes))
    monkeypatch.setattr(api, "_LEAGUES", ["Standard", "Covens"])
    monkeypatch.setattr(api, "_LIMITS", RateLimiter(clock=lambda: 100))
    monkeypatch.setattr(api, "_POLICIES", {})
    monkeypatch.setattr(api.secret, "load_session", lambda: "")

    def request(method, url, **kwargs):
        network.append({"method": method, "url": url, "body": kwargs.get("json")})
        return SimpleNamespace(status_code=200, headers={}, json=lambda: {"id": "", "result": [], "total": 0})

    monkeypatch.setattr(api.requests, "request", request)
    monkeypatch.setattr(trade_window.browser, "open_url", opened.append)
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, _fail: done(work()))
    win = trade_window.TradeWindow()
    yield win, settings, network, opened
    win.close()


@pytest.mark.parametrize("market,lang,league,key", [
    (config.KAKAO, "ko", "Covens", "kakao_ko"),
    (config.OFFICIAL, "en", "Standard", "official_en"),
])
def test_post_matches_fixed_apt_contract(scenario, fixtures, market, lang, league, key):
    win, settings, network, opened = scenario
    settings.update(server=market, league=league)
    expected = json.loads((fixtures / "unidentified_unique_post.json").read_bytes())[key]
    win.load(copy_text(lang))
    original = (win.model.name, win.model.base, tuple(win.model.head), tuple(win.model.flags))
    assert not win.unique_selection.isHidden() and win.unique_level.text() == "85"
    assert win.unique_name.currentData() is None and not win.search_button.isEnabled()
    name = expected["body"]["query"]["name"]
    win.unique_name.setCurrentIndex(win.unique_name.findData(name))
    assert win.unique_name.currentData() == name
    assert not network and not opened
    assert win.title.text() == f'{expected["body"]["query"]["name"]} · {expected["body"]["query"]["type"]}'
    assert win.scope_badge.text() == "미확인 · 아이템 레벨 85 정확히 일치"
    win.search_button.click()
    assert network == [expected] and not opened
    assert (win.model.name, win.model.base, tuple(win.model.head), tuple(win.model.flags)) == original


@pytest.mark.parametrize("copied,value", [("85", "86"), (None, "86")])
def test_manual_level_exact_without_mutating_copy_and_resets(scenario, copied, value):
    win, _, network, opened = scenario
    win.load(copy_text(level=copied))
    assert win.unique_level.text() == (copied or "")
    win.unique_name.setCurrentIndex(1)
    original = tuple(win.model.head)
    win.unique_level.setText(value)
    assert win.scope_badge.text() == "미확인 · 아이템 레벨 86 정확히 일치"
    assert not network and not opened and win.search_button.isEnabled()
    win.search()
    filters = network[0]["body"]["query"]["filters"]["misc_filters"]["filters"]
    assert filters["ilvl"] == {"min": 86, "max": 86}
    assert tuple(win.model.head) == original
    win.load(copy_text(level="84"))
    assert win.unique_name.currentData() is None and win.unique_level.text() == "84"
    assert not win.search_button.isEnabled() and len(network) == 1


@pytest.mark.parametrize("value", ["", "0", "-1", "85.5", "abc"])
def test_invalid_level_never_submits(scenario, value):
    win, _, network, opened = scenario
    win.load(copy_text())
    win.unique_name.setCurrentIndex(1)
    win.unique_level.setText(value)
    win.search()
    assert not win.search_button.isEnabled() and "양의 정수" in win.hint.text()
    assert not network and not opened


@pytest.mark.parametrize("market,lang,mode", [
    (config.KAKAO, "ko", "browser"), (config.OFFICIAL, "en", "browser"),
    (config.OFFICIAL, "ko", "browser"), (config.OFFICIAL, "ko", "api"),
    (config.KAKAO, "en", "api"), (config.KAKAO, "en", "browser"),
])
def test_unsupported_modes_and_localizations_stay_closed(scenario, market, lang, mode):
    win, settings, network, opened = scenario
    settings.update(server=market, mode=mode)
    win.load(copy_text(lang))
    win.unique_name.setCurrentIndex(1)
    win.search()
    assert not win.search_button.isEnabled() and "지원" in win.hint.text()
    assert not network and not opened


def test_exact_base_join_does_not_substitute_public_identity(scenario, monkeypatch):
    model = parse(copy_text(base="진홍색 주얼"))
    info = item_info(model, config.KAKAO)
    assert "감시자의 눈" not in info.unique_options
    with pytest.raises(ValueError):
        build_unidentified_unique_query(info, "감시자의 눈", "85", config.KAKAO, "api")
    malformed = parse(copy_text().replace("아이템 레벨: 85", "아이템 레벨: 85\n아이템 레벨: 86"))
    assert item_info(malformed, config.KAKAO).blocked_reason
    # 공개 이름도 번들의 정확한 ITEM 카테고리가 없으면 선택할 수 없다.
    catalog = items.catalog()
    records = catalog["items"]["ko"]
    rows = [row for row in records if row[:2] != ["ITEM", "Prismatic Jewel"]]
    monkeypatch.setattr(items, "catalog", lambda: {"items": {**catalog["items"], "ko": rows}})
    missing = item_info(parse(copy_text()), config.KAKAO)
    assert not missing.unique_options and missing.blocked_reason


def test_keyboard_selection_and_enter_in_level_do_not_submit(scenario):
    win, _, network, opened = scenario
    win.load(copy_text())
    win.show()
    win.activateWindow()
    win.unique_name.setFocus()
    QApplication.processEvents()
    assert win.unique_name.hasFocus()
    QTest.keyClick(win.unique_name, Qt.Key.Key_Down)
    assert win.unique_name.currentData() == "감시자의 눈"
    win.unique_level.setFocus()
    QTest.keyClick(win.unique_level, Qt.Key.Key_Return)
    assert not network and not opened


def test_identified_unique_retains_existing_path(scenario):
    win, settings, _, _ = scenario
    settings.update(server=config.OFFICIAL, league="Standard")
    win.load("Item Class: Rings\nRarity: Unique\nVentor's Gamble\nGold Ring\n--------\nItem Level: 85")
    assert win.unique_selection.isHidden() and win.search_button.isEnabled()
    assert win._query()["query"]["name"] == "Ventor's Gamble"


def test_simple_robe_candidate_preserves_copy_and_manual_level(scenario):
    win, _, network, opened = scenario
    win.load("아이템 종류: 갑옷\n아이템 희귀도: 고유\n단순한 로브\n--------\n"
             "홈: W-W-W-W-W-W\n--------\n아이템 레벨: 85\n--------\n미확인")
    copied = (win.model.base, tuple(win.model.head), tuple(win.model.flags))
    assert win.info.unique_options == ("천 개의 리본", "타뷸라 라사")
    assert win.unique_name.currentData() is None and not win.search_button.isEnabled()
    win.unique_name.setCurrentIndex(win.unique_name.findData("타뷸라 라사"))
    assert not network
    win.search_button.click()
    win.unique_level.setText("86")
    assert len(network) == 1
    win.search_button.click()
    for sent, level in zip(network, (85, 86), strict=True):
        query = sent["body"]["query"]
        assert (query["name"], query["type"]) == ("타뷸라 라사", "단순한 로브")
        assert query["filters"]["misc_filters"]["filters"] == {
            "identified": {"option": "false"}, "ilvl": {"min": level, "max": level},
        }
    assert (win.model.base, tuple(win.model.head), tuple(win.model.flags)) == copied
    assert not opened


def test_bundled_index_adds_referenced_and_literal_names_only_to_their_exact_base():
    for cls, base, expected in (
        ("장화", "염소가죽 장화", "아버라스의 발굽"),
        ("장갑", "매복 미트", "건축가의 손길"),
        ("한손 도끼", "도살자 도끼", "액툼"),
        ("반지", "뼈 반지", "내키지 않는 포옹"),
    ):
        text = copy_text(base=base).replace("주얼", cls)
        info = item_info(parse(text), config.KAKAO)
        assert expected in info.unique_options
        assert "타뷸라 라사" not in info.unique_options
    en = copy_text("en", base="Bone Ring").replace("Jewels", "Rings")
    assert "Unwilling Embrace" in item_info(parse(en), config.OFFICIAL).unique_options
