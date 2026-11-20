import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from itemmodel import parse
from trade import api, config, items, trade_window
from trade.query import build_query, item_info, owns_search_category


BASE = "어둠의 꼭두각시"
PERFECT = "완전한 어둠의 꼭두각시"


def clip(base=BASE, *, kind="시신", rarity="일반", tail=""):
    return f"아이템 종류: {kind}\n아이템 희귀도: {rarity}\n{base}\n--------\n{tail}"


def test_exact_variants_only_without_local_configuration(monkeypatch):
    monkeypatch.delenv("POE_DELTA_LOCAL_KAKAO_SPECTRE", raising=False)
    for base in (BASE, PERFECT):
        model = parse(clip(base))
        assert owns_search_category(model, server=config.KAKAO, league="Covens")
        info = item_info(model, config.KAKAO, league="Covens")
        assert info.category == items.SPECTRE_CATEGORY
        assert build_query(info, [])["query"] == {"status": {"option": "securable"}, "type": base}
        assert item_info(model, config.KAKAO, league="Standard").category != items.SPECTRE_CATEGORY
        assert item_info(model, config.OFFICIAL, league="Covens").category != items.SPECTRE_CATEGORY
    for text in (clip("꼭두각시"), clip("전쟁군주"), clip(kind="지도 조각"), clip(rarity="희귀"),
                 clip(tail="미확인"), clip("다른 이름\n" + BASE)):
        assert not item_info(parse(text), config.KAKAO, league="Covens").supported


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    state = {"server": config.KAKAO, "league": "Covens", "mode": "api"}
    calls = []
    scenario = {"league_list": ["Standard", "Covens"], "result": "row"}
    monkeypatch.setattr(config, "settings", lambda: state.copy())
    monkeypatch.setattr(config, "save", lambda **kwargs: (calls.append(("save", kwargs)), state.update(kwargs)))
    monkeypatch.setattr(trade_window.browser, "open_url", lambda url: calls.append(("browser", url)))
    monkeypatch.setattr(api, "_LEAGUES", None)

    def request(_client, method, endpoint, path, server, *, lang, **kwargs):
        calls.append((endpoint, server, lang, path, kwargs))
        if endpoint == "leagues":
            return {"result": [{"id": league} for league in scenario["league_list"]]}
        if endpoint == "search":
            if scenario["result"] == "error":
                raise api.TradeError("network")
            ids = ["one"] if scenario["result"] == "row" else []
            return {"id": "query", "result": ids, "total": len(ids)}
        assert endpoint == "fetch"
        return {"result": [{"id": "one", "listing": {"price": {"amount": 4, "currency": "chaos"}}}]}

    monkeypatch.setattr(api.TradeClient, "_request", request)
    monkeypatch.setattr(api, "LOCAL", tmp_path)
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, _fail: done(work()))
    win = trade_window.TradeWindow()
    yield win, state, calls, scenario
    win.close()


@pytest.mark.parametrize("result,expected", [("row", "4 chaos"), ("empty", "검색 결과가 없습니다"),
                                            ("error", "네트워크 오류입니다")])
def test_click_only_native_request_and_result(window, result, expected):
    win, state, calls, scenario = window
    scenario["result"] = result
    win.load(clip(PERFECT))
    assert win.scope_badge.text() == "시신" and win.search_button.isEnabled()
    assert win.open_button.isHidden() and not calls
    win.search_button.click()
    assert [c[0] for c in calls] == ["leagues", "search"] + (["fetch"] if result == "row" else [])
    assert calls[1][1:] == (config.KAKAO, "ko", "/api/trade/search/Covens", {
        "json": {"query": {"status": {"option": "securable"}, "type": PERFECT}, "sort": {"price": "asc"}},
    })
    if result == "row":
        assert win.table.item(0, 0).text() == expected
    else:
        assert win.table.rowCount() == 0 and expected in win.result_summary.text()
    assert state["league"] == win.league.currentText() == "Covens"


@pytest.mark.parametrize("initial", ["api", "browser"])
def test_browser_mode_or_mode_change_never_requests_or_opens(window, initial):
    win, state, calls, _ = window
    state["mode"] = initial
    win.load(clip())
    state["mode"] = "browser"
    win.search()
    assert not calls and not win.search_button.isEnabled()
    assert "게임 위 시세 모드" in win.hint.text()


@pytest.mark.parametrize("cached", [False, True])
def test_covens_missing_never_falls_back_or_saves(window, monkeypatch, cached):
    win, state, calls, scenario = window
    scenario["league_list"] = ["Standard"]
    if cached:
        monkeypatch.setattr(api, "_LEAGUES", ["Standard"])
    win.load(clip())
    assert not calls
    win.search_button.click()
    assert [c[0] for c in calls] == ([] if cached else ["leagues"])
    assert trade_window.SPECTRE_LEAGUE_ERROR == win.result_summary.text()
    assert state["league"] == win.league.currentText() == "Covens" and not win.table.rowCount()


def test_non_spectre_browser_and_league_fallback_are_unchanged(window):
    win, state, calls, scenario = window
    scenario["league_list"] = ["Standard"]
    state.update(server=config.OFFICIAL, mode="browser")
    text = "Item Class: Rings\nRarity: Rare\nGold Ring\n--------\nItem Level: 83"
    win.load(text)
    win.search_button.click()
    assert [c[0] for c in calls] == ["browser"]
    calls.clear()
    state["mode"] = "api"
    win.load(text)
    win.search_button.click()
    assert [c[0] for c in calls] == ["leagues", "search", "save", "fetch"]
    assert calls[1][3] == "/api/trade/search/Standard"
    assert state["league"] == win.league.currentText() == "Standard"


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_keyboard_shortcut_requires_spectre_search_button_focus(window, key):
    win, state, calls, _ = window
    win.load(clip())
    win.show()
    win.activateWindow()
    editor = win.league.lineEdit()
    editor.setFocus()
    QApplication.processEvents()
    assert editor.hasFocus()
    QTest.keyClick(editor, key)
    assert not calls
    win.search_button.setFocus()
    QTest.keyClick(win.search_button, key)
    assert [c[0] for c in calls] == ["leagues", "search", "fetch"]

    calls.clear()
    state.update(server=config.OFFICIAL, mode="browser", league="Standard")
    win.load("Item Class: Rings\nRarity: Rare\nGold Ring\n--------\nItem Level: 83")
    editor.setFocus()
    QTest.keyClick(editor, key)
    assert [c[0] for c in calls] == ["browser"]


@pytest.mark.parametrize("pending_endpoint", ["search", "fetch"])
@pytest.mark.parametrize("revoke", ["delete", "mutate"])
def test_queued_spectre_requests_require_bundled_data(window, tmp_path, monkeypatch, pending_endpoint, revoke):
    bundled = items.resource_path
    local = tmp_path / "spectre_types.json"
    local.write_bytes(bundled(items.SPECTRE_TYPES).read_bytes())
    monkeypatch.setattr(items, "resource_path", lambda rel: local if rel == items.SPECTRE_TYPES else bundled(rel))
    win, _, calls, _ = window
    pending = []
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, _fail: pending.append((work, done)))
    win.load(clip())
    win.search_button.click()
    assert len(pending) == 1 and not calls

    if pending_endpoint == "fetch":
        work, done = pending.pop(0)
        done(work())
        assert len(pending) == 1 and [c[0] for c in calls] == ["leagues", "search"]

    if revoke == "delete":
        local.unlink()
    else:
        local.write_text("{}", encoding="utf-8")

    work, done = pending.pop(0)
    done(work())
    assert not pending
    assert [c[0] for c in calls] == ([] if pending_endpoint == "search" else ["leagues", "search"])
    assert trade_window.SPECTRE_DATA_ERROR in win.result_summary.text()
    assert win.table.rowCount() == 0


def test_copied_currency_corpse_searches_by_class_without_opt_in(window, monkeypatch):
    monkeypatch.delenv("POE_DELTA_LOCAL_KAKAO_SPECTRE", raising=False)
    win, _, calls, _ = window
    win.load("""아이템 종류: 시신
아이템 희귀도: 화폐
불완전한 신성모독자
--------
시신 레벨: 71
몬스터 유형: 언데드
--------
아이템 레벨: 71
--------
이동하는 저주받은 지대 생성
--------
이 아이템에 우클릭하여 이 시신을 생성할 수 있습니다.""")
    assert win.scope_badge.text() == "시신" and win.search_button.isEnabled() and not calls
    win.search_button.click()
    assert calls[1][-1]["json"]["query"] == {
        "status": {"option": "securable"}, "type": "불완전한 신성모독자",
    }
