import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from PySide6.QtWidgets import QLabel, QWidget

from itemmodel import parse
from trade import browser, config
from trade.query import build_query, conditions, item_info
from trade.stats import index


EXPECTED_IDS = {
    "Shaper": "pseudo.pseudo_has_shaper_influence",
    "Elder": "pseudo.pseudo_has_elder_influence",
    "Crusader": "pseudo.pseudo_has_crusader_influence",
    "Redeemer": "pseudo.pseudo_has_redeemer_influence",
    "Hunter": "pseudo.pseudo_has_hunter_influence",
    "Warlord": "pseudo.pseudo_has_warlord_influence",
}
KO_FLAGS = ("쉐이퍼", "엘더", "십자군", "대속자", "사냥꾼", "전쟁군주")


def filters(query):
    group, = query["query"]["stats"]
    assert group["type"] == "and"
    assert query["query"]["status"] == {"option": "securable"}
    return group["filters"]


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_all_traditional_influences_and_selection(fixtures, lang):
    text = (fixtures / f"rare_{lang}.txt").read_text(encoding="utf-8")
    names = EXPECTED_IDS if lang == "en" else KO_FLAGS
    suffix = " Item" if lang == "en" else " 아이템"
    item = item_info(parse(text + "\n" + "\n".join(name + suffix for name in names)))
    assert index().influences == EXPECTED_IDS
    selected = filters(build_query(item, []))
    assert selected == [{"id": value} for value in EXPECTED_IDS.values()]
    for name, value in EXPECTED_IDS.items():
        assert filters(build_query(item, [], influences={name})) == [{"id": value}]
    assert filters(build_query(item, [], influences=set())) == []


def eldritch_item(fixtures, lang, flags):
    header = (fixtures / f"rare_{lang}.txt").read_text(encoding="utf-8").split("--------")[0]
    if lang == "en":
        blocks = ["Item Level: 86",
                  "{ Searing Exarch Implicit Modifier }\n4% increased Movement Speed",
                  "{ Eater of Worlds Implicit Modifier }\n+5% chance to Suppress Spell Damage",
                  "{ Eater of Worlds Implicit Modifier }\n0.2% of Fire Damage Leeched as Life",
                  "+100 to maximum Life\n+30% to Fire Resistance (crafted)\n"
                  "+40% to Fire Resistance (fractured)\n10% increased Attack Speed (enchant)"]
    else:
        blocks = ["아이템 레벨: 86",
                  "{ 작열의 총주교 고정 속성 부여 }\n이동 속도 4% 증가",
                  "{ 세계 포식자 고정 속성 부여 }\n주문 피해 억제 확률 +5%",
                  "{ 세계 포식자 고정 속성 부여 }\n화염 피해의 0.2%를 생명력으로 흡수",
                  "생명력 최대치 +100\n화염 저항 +30% (crafted)\n"
                  "화염 저항 +40% (fractured)\n공격 속도 10% 증가 (enchant)"]
    return header + "--------\n" + "\n--------\n".join([*blocks, "\n".join(flags)])


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_eldritch_rows_keep_sources_badges_and_match_reasons(app, fixtures, lang):
    from trade.trade_window import TradeWindow

    flags = (["Searing Exarch Item", "Eater of Worlds Item"] if lang == "en"
             else ["작열의 총주교 아이템", "세계 포식자 아이템"])
    text = eldritch_item(fixtures, lang, flags)
    item = item_info(parse(text))
    assert item.eldritch_sources == ("작열의 총주교", "세계 포식자")
    config.save(mode="browser", server=config.OFFICIAL, league="Standard")
    window = TradeWindow()
    window.load(text)
    assert not window.influence_inputs
    assert "섬뜩한 영향력: 작열의 총주교 · 세계 포식자" in [
        label.text() for label in window.findChildren(QLabel)]
    assert window.inputs[0][0].isEnabled() and window.inputs[1][0].isEnabled()
    assert not window.inputs[2][0].isEnabled() and window.inputs[2][0].toolTip()
    window.close()
    stats = conditions(item)
    assert {line.badge for line in stats} >= {"총주교", "포식자", "제작", "분열", "인챈트"}
    assert [line.match.id for line in stats[:3]] == [
        "implicit.stat_2250533757", "implicit.stat_3680664274", ""]
    assert stats[2].match.reason
    assert all(not line.checked for line in stats[:3])
    for line in stats:
        line.checked = line is stats[0] or line is stats[1]
    query = build_query(item, stats)
    assert [line["id"] for line in filters(query)] == ["implicit.stat_2250533757", "implicit.stat_3680664274"]
    assert query["query"]["filters"] == {
        "misc_filters": {"filters": {"corrupted": {"option": "false"}}},
        "type_filters": {"filters": {"category": {"option": "armour.chest"}, "rarity": {"option": "nonunique"}}},
    }
    # 기존 파서가 출처를 특정하지 못한 줄은 거래소 stat이 있더라도 선택하지 않는다.
    item.model.mods[0].sub = "eldritch"
    ambiguous = conditions(item)[0]
    assert not ambiguous.match.id and "출처가 모호" in ambiguous.match.reason


@pytest.mark.parametrize("lang,server", [("en", config.OFFICIAL), ("ko", config.KAKAO)])
def test_window_both_modes_send_same_selected_query(app, fixtures, monkeypatch, lang, server):
    from trade import api, trade_window
    from ratelimit import RateLimiter

    flags = ["Shaper Item", "Elder Item"] if lang == "en" else ["쉐이퍼 아이템", "엘더 아이템"]
    text = eldritch_item(fixtures, lang, flags)
    opened, calls = [], []
    monkeypatch.setattr(browser, "open_url", opened.append)
    monkeypatch.setattr(api, "_LEAGUES", None)
    monkeypatch.setattr(api, "_POLICIES", {})
    monkeypatch.setattr(api, "_LIMITS", RateLimiter())
    monkeypatch.setattr(api.secret, "load_session", lambda: "")

    def transport(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        payload = ({"result": [{"id": "Standard"}]} if method == "GET"
                   else {"id": "test-id", "result": [], "total": 0})
        return SimpleNamespace(status_code=200, headers={}, json=lambda: payload)

    monkeypatch.setattr(requests, "request", transport)
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: done(work()))
    window = trade_window.TradeWindow()
    for mode in ("browser", "api"):
        config.save(mode=mode, api_ack_at=1, server=server, league="Standard")
        window.load(text)
        assert [check.text() for check in window.influence_inputs.values()] == ["쉐이퍼", "엘더"]
        assert all(check.isChecked() for check in window.influence_inputs.values())
        window.influence_inputs["Shaper"].setChecked(False)
        implicit = window.findChild(QWidget, "implicitOptions")
        explicit = window.findChild(QWidget, "explicitOptions")
        for condition, (check, minimum, maximum) in zip(window.stats, window.inputs):
            assert (implicit if condition.kind == "implicit" else explicit).isAncestorOf(check)
            check.setChecked(condition.match.id == "implicit.stat_2250533757")
            if check.isChecked():
                minimum.setText("2")
                maximum.setText("5")
        assert {label.text() for label in explicit.findChildren(QLabel)} >= {"제작", "분열", "인챈트"}
        assert not calls
        window.search()
    assert len(opened) == 1
    assert opened[0].startswith(server + "/")
    browser_query = json.loads(parse_qs(urlsplit(opened[0]).query)["q"][0])
    assert [method for method, _, _ in calls] == ["GET", "POST"]
    assert all(url.startswith(server + "/") for _, url, _ in calls)
    assert calls[-1][2] == browser_query
    assert filters(browser_query) == [{"id": "implicit.stat_2250533757", "value": {"min": 2, "max": 5}},
                                      {"id": EXPECTED_IDS["Elder"]}]
    window.close()
