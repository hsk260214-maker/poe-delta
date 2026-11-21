import pytest

from itemmodel import parse
from trade import api, config, items, trade_window
from trade.query import item_info


@pytest.fixture
def copied(fixtures):
    return (fixtures / "screaming_invitation_normal_ko.txt").read_text(encoding="utf-8")


@pytest.fixture
def scenario(app, monkeypatch):
    settings = {"server": config.KAKAO, "mode": "api", "league": "Covens"}
    leagues = ["Standard", "Covens"]
    calls = []
    monkeypatch.setattr(config, "settings", lambda: settings.copy())
    monkeypatch.setattr(config, "save", lambda **values: calls.append(("save", values)))
    monkeypatch.setattr(trade_window.browser, "open_url", lambda *_: pytest.fail("브라우저가 열림"))
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, _fail: done(work()))

    class Client:
        def leagues(self, server, lang):
            calls.append(("leagues", server, lang))
            return leagues

        def search(self, league, query, server, lang):
            calls.append(("search", league, query, server, lang))
            return {"id": "query", "result": ["quest", "ok", "other-base", "other-type", "bool", "string", "clash"],
                    "total": 100}

        def fetch(self, ids, query_id, server, lang):
            calls.append(("fetch", tuple(ids), query_id, server, lang))
            name = "절규하는 초대"

            def entry(key, *, frame=0, base=name, type_line=name):
                return {"id": key, "item": {"baseType": base, "typeLine": type_line, "frameType": frame,
                                             "ilvl": 83}, "listing": {"price": {"amount": 4, "currency": "chaos"}}}

            return {"result": [
                entry("outside"), entry("quest", frame=7), entry("other-base", base="다른 초대"),
                entry("ok"), entry("other-type", type_line="다른 초대"), entry("bool", frame=False),
                entry("string", frame="0"), entry("clash"), entry("clash", frame=7),
            ]}

        def remaining(self, *_):
            return 0

    monkeypatch.setattr(api, "TradeClient", Client)
    win = trade_window.TradeWindow()
    yield win, settings, leagues, calls
    win.close()


@pytest.mark.parametrize("use_level", [False, True])
def test_explicit_search_filters_bad_results_and_keeps_optional_level(scenario, copied, use_level):
    win, _, _, calls = scenario
    win.load(copied)
    assert (win.info.category, win.info.rarity, win.info.ilvl) == ("기타 지도 아이템", "Normal", 83)
    assert win.info.map_fragment_ref == "Screaming Invitation"
    assert win.title.text() == "절규하는 초대" and win.scope_badge.text() == "기타 지도 아이템"
    assert [(mod.kind, mod.unscalable) for mod in win.model.mods if mod.kind == "implicit"] == [("implicit", True)]
    assert win.ilvl.isEnabled() and not win.ilvl.isChecked() and win.stats == []
    win.ilvl.setChecked(use_level)
    assert not calls and win.search_button.isEnabled()
    win.search_button.click()
    expected = {"status": {"option": "securable"}, "type": "절규하는 초대"}
    if use_level:
        expected["filters"] = {"misc_filters": {"filters": {"ilvl": {"min": 83}}}}
    assert calls[1] == ("search", "Covens", {"query": expected, "sort": {"price": "asc"}}, config.KAKAO, "ko")
    assert [call[0] for call in calls] == ["leagues", "search", "fetch"]
    assert win.table.rowCount() == 1 and [row["id"] for row in win._results.rows] == ["ok"]
    assert "일치한 매물 1개" in win.result_summary.text()
    assert win.open_button.isHidden() and not win._result_link


@pytest.mark.parametrize("change", [
    {"mode": "browser"}, {"server": config.OFFICIAL}, {"league": "Standard"},
])
def test_wrong_route_never_starts_request(scenario, copied, change):
    win, settings, _, calls = scenario
    settings.update(change)
    win.load(copied)
    win.search()
    assert not win.search_button.isEnabled() and not calls


def test_pressed_in_api_but_mode_changed_never_opens_browser(scenario, copied):
    win, settings, _, calls = scenario
    win.load(copied)
    settings["mode"] = "browser"
    win.search()
    assert not win.search_button.isEnabled() and not calls


def test_no_covens_never_searches_fetches_or_saves(scenario, copied):
    win, settings, leagues, calls = scenario
    leagues[:] = ["Standard"]
    win.load(copied)
    win.search_button.click()
    assert calls == [("leagues", config.KAKAO, "ko")]
    assert win.league.currentText() == settings["league"] == "Covens"
    assert "Covens를 확인할 수 없습니다" in win.result_summary.text()


@pytest.mark.parametrize("before,after", [
    ("희귀도: 일반", "희귀도: 퀘스트"),
    ("기타 지도 아이템", "지도 조각"),
    ("절규하는 초대", "다른 초대"),
    ("아이템 레벨: 83", "아이템 레벨: 83\n아이템 레벨: 84"),
])
def test_ambiguous_or_other_copy_does_not_use_new_path(copied, before, after):
    info = item_info(parse(copied.replace(before, after)), config.KAKAO, league="Covens")
    assert not info.map_fragment_ref and not info.supported


def test_same_name_catalog_collision_is_closed(copied, monkeypatch):
    row, = [row for row in items.catalog()["items"]["ko"] if row[2] == "절규하는 초대"]
    monkeypatch.setattr(items, "catalog", lambda: {"items": {"ko": [
        row, ["ITEM", "Other Invitation", "절규하는 초대", "Invitation", None, None],
    ]}})
    info = item_info(parse(copied), config.KAKAO, league="Covens")
    assert not info.map_fragment_ref and not info.supported
