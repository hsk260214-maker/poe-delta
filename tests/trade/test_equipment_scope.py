import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from PySide6.QtWidgets import QPushButton

from itemmodel import parse
from trade import browser, config, items
from trade.query import StatCondition, build_query, conditions, item_info
from trade.stats import StatIndex, index


def equipment(label, base, *, lang="en", rarity="Rare", mods=""):
    headers = ("Item Class", "Rarity", "Item Level") if lang == "en" else ("아이템 종류", "아이템 희귀도", "아이템 레벨")
    return parse(f"{headers[0]}: {label}\n{headers[1]}: {rarity}\n{base}\n--------\n{headers[2]}: 80\n--------\n{mods}")


@pytest.mark.parametrize("en,ko,base_en,base_ko,category", [
    ("Helmets", "투구", "Leather Cap", "가죽 모자", "armour.helmet"),
    ("Rings", "반지", "Gold Ring", "황금 반지", "accessory.ring"),
    ("Thrusting One Hand Swords", "날카로운 한손 검", "Jewelled Foil", "보석이 박힌 펜싱 검", "weapon.onesword"),
    ("Jewels", "주얼", "Crimson Jewel", "진홍색 주얼", "jewel"),
    ("Abyss Jewels", "심연 주얼", "Searching Eye Jewel", "탐색하는 눈 주얼", "jewel.abyss"),
    ("Jewels", "주얼", "Large Cluster Jewel", "대형 스킬 군 주얼", "jewel.cluster"),
])
def test_equipment_category_and_exact_localized_base(en, ko, base_en, base_ko, category):
    for model, server, base in (
        (equipment(en, base_en), config.OFFICIAL, base_en),
        (equipment(ko, base_ko, lang="ko", rarity="희귀"), config.OFFICIAL, base_en),
        (equipment(ko, base_ko, lang="ko", rarity="희귀"), config.KAKAO, base_ko),
    ):
        info = item_info(model, server)
        query = build_query(info, [])["query"]
        assert "type" not in query and "name" not in query
        assert query["filters"]["type_filters"]["filters"] == {
            "category": {"option": category}, "rarity": {"option": "nonunique"},
        }
        exact = build_query(info, [], exact_base=True)["query"]
        assert exact["type"] == base and "type_filters" not in exact["filters"]


@pytest.mark.parametrize("rarity,base", [("Normal", "Topaz Ring"), ("Magic", "Healthy Topaz Ring")])
def test_equipment_rarity_is_unchanged_in_both_scopes(rarity, base, monkeypatch):
    model = equipment("Rings", base, rarity=rarity)
    if rarity == "Normal":
        monkeypatch.setattr(items, "BROWSER_VERIFIED", frozenset())
        assert not item_info(model).supported
        monkeypatch.setattr(items, "BROWSER_VERIFIED", {"normal"})
    info = item_info(model)
    for exact in (False, True):
        query = build_query(info, [], exact_base=exact)["query"]
        filters = query["filters"]["type_filters"]["filters"]
        assert filters["rarity"] == {"option": rarity.lower()}
        assert ("category" in filters) != exact
        assert query.get("type") == ("Topaz Ring" if exact else None)


def test_unmapped_category_only_allows_exact(monkeypatch):
    monkeypatch.delitem(items.EQUIPMENT_TRADE_IDS, "Ring")
    info = item_info(equipment("Rings", "Topaz Ring"))
    assert build_query(info, [])["query"]["type"] == "Topaz Ring"


@pytest.mark.parametrize("rarity,base", [
    ("Rare", "Two-Stone Ring"),
    ("Magic", "Healthy Two-Stone Ring"),
    ("Magic", "Imaginary Future Band"),
    ("Normal", "Imaginary Future Band"),
])
def test_equipment_search_blocks_ambiguous_or_unconfirmed_base(rarity, base):
    info = item_info(equipment("Rings", base, rarity=rarity))
    assert not info.supported
    for exact in (False, True):
        with pytest.raises(ValueError, match="식별할 수 없습니다"):
            build_query(info, [], exact_base=exact)


@pytest.mark.parametrize("lang,server,copied,expected_base", [
    ("en", config.OFFICIAL, "Imaginary Future Ring", "Imaginary Future Ring"),
    ("en", config.OFFICIAL, "Synthesised Gold Ring", "Synthesised Gold Ring"),
    ("ko", config.KAKAO, "결합된 황금 반지", "결합된 황금 반지"),
    ("ko", config.OFFICIAL, "결합된 황금 반지", "Gold Ring"),
])
def test_unlisted_rare_base_keeps_legacy_exact_search(app, lang, server, copied, expected_base):
    from trade.trade_window import TradeWindow

    model = (equipment("Rings", copied) if lang == "en" else
             equipment("반지", copied, lang="ko", rarity="희귀"))
    config.save(mode="browser", server=server, league="Standard")
    window = TradeWindow()
    # 카테고리를 제공했던 아이템에서 바꿔도 이전 버튼이 남지 않는다.
    window.load(equipment("반지", "황금 반지", lang="ko", rarity="희귀"))
    assert not window.base_button.isHidden()
    window.base_button.click()
    window.load(model)
    assert window.search_button.isEnabled()
    assert window.base_button.isHidden() and not window.base_button.isChecked()
    expected = {
        "query": {
            "status": {"option": "securable"},
            "type": expected_base,
            "stats": [{"type": "and", "filters": []}],
            "filters": {"misc_filters": {"filters": {"corrupted": {"option": "false"}}}},
        },
        "sort": {"price": "asc"},
    }
    assert window._query() == expected
    assert build_query(window.info, [], exact_base=True) == expected
    window.close()


def test_select_does_not_borrow_from_other_record():
    stat = index().match("Adds 10 to 20 Chaos Damage", "explicit", "Ring")
    assert stat.id == "explicit.stat_3531280422" and not stat.alternate_id
    # 선별된 Local 행에 상대 ID가 없으면 같은 묶음의 전역 ID도 쓸 수 없다.
    fixture = StatIndex({
        "influences": {},
        "entries": [
            {"group": 0, "test": None, "inverted": False, "ids": {"explicit": ["explicit.global"], "fractured": ["fractured.global"]}},
            {"group": 0, "test": "WEAPON", "inverted": True, "ids": {"explicit": ["explicit.local"]}},
        ],
        "groups": [{"strat": "select"}],
        "matchers": [{"entry": n, "skeleton": "# damage", "negate": False, "has_value": False} for n in (0, 1)],
    })
    local = fixture.match("10 damage", "explicit", "WEAPON")
    assert local.id == "explicit.local" and local.invert and not local.alternate_id


def test_switch_keeps_bounds_and_checked_state():
    match = index().match("10% reduced Movement Speed", "explicit", "ARMOUR")
    row = StatCondition("10% reduced Movement Speed", "explicit", match, True, 5, 15)
    assert match.invert and match.alternate_id
    row.switch_kind()
    info = item_info(equipment("Helmets", "Leather Cap"))
    assert build_query(info, [row])["query"]["stats"][0]["filters"] == [
        {"id": match.alternate_id, "value": {"max": -5, "min": -15}},
    ]
    row.switch_kind()
    assert (row.kind, row.match, row.checked, row.minimum, row.maximum) == ("explicit", match, True, 5, 15)


def test_window_base_and_switch_send_one_shared_query(app, monkeypatch):
    from ratelimit import RateLimiter
    from trade import api, trade_window

    sent, opened = [], []
    monkeypatch.setattr(browser, "open_url", opened.append)
    monkeypatch.setattr(api, "_LEAGUES", ["Standard"])
    monkeypatch.setattr(api, "_POLICIES", {})
    monkeypatch.setattr(api, "_LIMITS", RateLimiter())
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: done(work()))

    def post(method, url, **kwargs):
        sent.append(kwargs["json"])
        return SimpleNamespace(status_code=200, headers={}, json=lambda: {"id": "x", "result": [], "total": 0})

    monkeypatch.setattr(requests, "request", post)
    model = equipment("Rings", "Topaz Ring", mods="+30 to maximum Life\n+12% to Lightning Resistance (implicit)\nAdds 10 to 20 Chaos Damage")
    window = trade_window.TradeWindow()
    for mode in ("browser", "api"):
        config.save(mode=mode, server=config.OFFICIAL, league="Standard")
        window.load(model)
        assert "type" not in window._query()["query"]
        assert not window.base_button.isChecked() and window.base_button.text() == "장비 종류 전체 검색"
        window.base_button.click()
        assert window.base_button.isChecked() and window.base_button.text() == "정확한 베이스: Topaz Ring"
        assert window.result_summary.text() == "조건이 바뀌었습니다. 검색을 눌러 주세요"
        check, minimum, maximum = window.inputs[0]
        check.setChecked(True)
        minimum.setText("20")
        maximum.setText("35")
        switches = [b for b in window.findChildren(QPushButton) if b.text() == "종류 전환"]
        assert len(switches) == 2
        assert switches[0].isEnabled() and not switches[1].isEnabled() and switches[1].toolTip()
        switches[0].click()
        assert check.isChecked() and (minimum.text(), maximum.text()) == ("20", "35")
        assert not sent
        window.search()
    assert len(opened) == len(sent) == 1
    assert json.loads(parse_qs(urlsplit(opened[0]).query)["q"][0]) == sent[0]
    assert sent[0]["query"]["type"] == "Topaz Ring"
    assert sent[0]["query"]["status"] == {"option": "securable"}
    window.close()


def test_condition_change_discards_previous_and_in_flight_results(app, monkeypatch):
    from trade import api, trade_window

    pending, sent = [], []
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: pending.append((work, done)))
    monkeypatch.setattr(api.TradeClient, "leagues", lambda *args: ["Standard"])
    monkeypatch.setattr(api.TradeClient, "remaining", lambda *args: 0)
    monkeypatch.setattr(api.TradeClient, "fetch", lambda *args: {"result": []})
    monkeypatch.setattr(trade_window, "result_rows", lambda _data: [
        {"amount": 10, "currency": "chaos", "seller": "tester", "age": "1분 전", "ilvl": 80},
    ])

    def search(_client, _league, query, *_args):
        sent.append(query)
        return {"id": "test", "result": ["item"], "total": 1}

    monkeypatch.setattr(api.TradeClient, "search", search)
    config.save(mode="api", server=config.KAKAO, league="Standard")
    window = trade_window.TradeWindow()
    window.load(equipment("반지", "토파즈 반지", lang="ko", rarity="희귀", mods="최대 생명력 +30"))

    def finish_search():
        work, done = pending.pop()
        done(work())

    window.search()
    finish_search()
    assert "type" not in sent[0]["query"]
    assert window.table.rowCount() == 1 and window.open_button.isEnabled() and window._result_link
    window.base_button.click()
    assert window.base_button.text() == "정확한 베이스: 토파즈 반지"
    assert window.table.rowCount() == 0 and not window.open_button.isEnabled() and not window._result_link
    assert window.result_summary.text() == "조건이 바뀌었습니다. 검색을 눌러 주세요"
    assert not pending and len(sent) == 1

    window.search()
    finish_search()
    assert sent[1]["query"]["type"] == "토파즈 반지"
    assert window.table.rowCount() == 1

    window.search()
    window.corrupted.click()
    assert len(pending) == 1 and len(sent) == 2
    finish_search()
    assert window.table.rowCount() == 0 and not window.open_button.isEnabled() and not window._result_link
    assert window.result_summary.text() == "조건이 바뀌었습니다. 검색을 눌러 주세요"
    window.close()
