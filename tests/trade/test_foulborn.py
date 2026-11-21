import json
from urllib.parse import parse_qs, urlsplit

import pytest

from itemmodel import parse
from trade import api, browser, config, items
from trade.query import build_query, item_info
from trade.trade_window import TradeWindow


COPY = """아이템 종류: 투구
아이템 희귀도: 고유
삿된 아세나스의 징표
철제 관
--------
에너지 보호막: 44 (augmented)
--------
요구사항:
레벨: 8
지능: 23
--------
홈: W
--------
아이템 레벨: 83
--------
{ 고유 속성 부여 — 마나 }
마나 재생 속도 30% 증가
{ 고유 속성 부여 — 방어력, 에너지 보호막 }
에너지 보호막 최대치 +30(30-50)
{ 고유 속성 부여 — 피해, 시전 }
주문 피해 52(30-60)% 증가
{ 고유 속성 부여 — 공격, 시전, 젬 }
활 공격 시 장착된 주문 발동, 재사용 대기시간 0.3초 — 변경이 불가능한 값
{ 삿된 고유 속성 }
재사용 대기시간 회복 속도 14(10-15)% 증가
--------
아세나스의 정신은
활시위를 당기는 가락만큼이나 기민했다."""


@pytest.mark.parametrize("server,name,base", [
    (config.KAKAO, "아세나스의 징표", "철제 관"),
    (config.OFFICIAL, "Asenath's Mark", "Iron Circlet"),
])
def test_exact_foulborn_pair_and_corruption_are_independent(server, name, base):
    model = parse(COPY + "\n--------\n타락")
    info = item_info(model, server)
    assert info.supported and info.foulborn and info.ilvl == 83
    assert model.name == "삿된 아세나스의 징표" and model.base == "철제 관"
    assert any(mod.text == "재사용 대기시간 회복 속도 14% 증가" for mod in model.mods)
    query = build_query(info, [])["query"]
    assert (query["name"], query["type"]) == (name, base)
    assert query["stats"] == [{"type": "and", "filters": []}]
    assert query["filters"]["misc_filters"]["filters"] == {
        "foulborn_item": {"option": "true"}, "corrupted": {"option": "true"},
    }
    assert build_query(info, [], corrupted=False)["query"]["filters"]["misc_filters"]["filters"] == {
        "foulborn_item": {"option": "true"},
    }


@pytest.mark.parametrize("name", ["아세나스의 징표", "삿된아세나스의 징표"])
def test_prefix_must_be_in_name_with_exact_space(name):
    info = item_info(parse(COPY.replace("삿된 아세나스의 징표", name)), config.KAKAO)
    assert info.supported and not info.foulborn
    assert "foulborn_item" not in build_query(info, [])["query"]["filters"]["misc_filters"]["filters"]


@pytest.mark.parametrize("mode", ["api", "browser"])
def test_unresolved_pairs_never_fall_back(app, monkeypatch, mode):
    config.save(server=config.KAKAO, mode=mode, league="Covens")
    monkeypatch.setattr(api, "TradeClient", lambda: pytest.fail("API 검색이 시작됨"))
    monkeypatch.setattr(browser, "open_url", lambda _: pytest.fail("웹 검색이 열림"))
    window = TradeWindow()
    try:
        for text in (COPY.replace("철제 관", "가죽 모자"), COPY.replace("아세나스의 징표", "다른 고유"),
                     COPY.replace("삿된 아세나스", "삿된 삿된 아세나스")):
            window.load(text)
            window.search()
            assert not window.info.supported and not window.search_button.isEnabled()
        original = items.catalog()
        rows = [row for row in original["items"]["ko"] if row[:2] != ["ITEM", "Iron Circlet"]]
        monkeypatch.setattr(items, "catalog", lambda: {"items": {**original["items"], "ko": rows}})
        window.load(COPY)
        window.search()
        assert not window.search_button.isEnabled()
    finally:
        window.close()


def test_browser_search_retains_required_foulborn_filter(app, monkeypatch):
    config.save(server=config.KAKAO, mode="browser", league="Covens")
    urls = []
    monkeypatch.setattr(browser, "open_url", urls.append)
    window = TradeWindow()
    try:
        window.load(COPY)
        assert window.scope_badge.text() == "삿된: 예" and not urls
        window.search_button.click()
        url, = urls
        query = json.loads(parse_qs(urlsplit(url).query)["q"][0])["query"]
        assert (query["name"], query["type"]) == ("아세나스의 징표", "철제 관")
        assert query["filters"]["misc_filters"]["filters"]["foulborn_item"] == {"option": "true"}
    finally:
        window.close()
