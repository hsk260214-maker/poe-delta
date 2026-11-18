import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from itemmodel import parse
from trade import browser, config, items
from trade.query import build_query, conditions, item_info


def copy(kind, rarity, name, *blocks, lang="en"):
    labels = ("Item Class", "Rarity") if lang == "en" else ("아이템 종류", "아이템 희귀도")
    return f"{labels[0]}: {kind}\n{labels[1]}: {rarity}\n{name}\n--------\n" + "\n--------\n".join(blocks)


@pytest.mark.parametrize("kind,rarity,name,detail,lang,expected,extras", [
    ("Rings", "Magic", "Healthy Gold Ring", "Item Level: 50", "en", "Gold Ring", {"rarity": "magic"}),
    ("반지", "마법", "건강한 황금 반지", "아이템 레벨: 50", "ko", "Gold Ring", {"rarity": "magic"}),
    ("Utility Flasks", "Magic", "Experimenter's Quicksilver Flask", "Item Level: 50", "en", "Quicksilver Flask", {"rarity": "magic"}),
    ("특수 플라스크", "마법", "실험자의 수은 플라스크", "아이템 레벨: 50", "ko", "Quicksilver Flask", {"rarity": "magic"}),
    ("Maps", "Magic", "Chilled Map (Tier 8)", "Item Level: 70", "en", {"option": "Map", "discriminator": "map"}, {"tier": 8, "rarity": "magic"}),
    ("지도", "마법", "냉각된 지도 (8등급)", "아이템 레벨: 70", "ko", {"option": "Map", "discriminator": "map"}, {"tier": 8, "rarity": "magic"}),
    ("Utility Flasks", "Unique", "Taste of Hate\nSapphire Flask", "Item Level: 80", "en", "Sapphire Flask", {"name": "Taste of Hate"}),
    ("지도", "고유", "겁쟁이의 시험\n지도 (8등급)", "아이템 레벨: 75", "ko", {"option": "Map", "discriminator": "map"}, {"tier": 8, "name": {"option": "The Coward's Trial", "discriminator": "map"}}),
    ("Skill Gems", "Gem", "Fireball", "Level: 18\nQuality: +20%", "en", "Fireball", {"gem_level": 18, "quality": 20}),
    ("보조 젬", "젬", "강화 보조", "레벨: 3 (최대)\n퀄리티: +20%", "ko", "Empower Support", {"gem_level": 3, "quality": 20}),
])
def test_item_and_browser_queries(kind, rarity, name, detail, lang, expected, extras):
    info = item_info(parse(copy(kind, rarity, name, detail, lang=lang)))
    assert info.supported, info.message
    packet = build_query(info, conditions(info), exact_base=True)
    query = packet["query"]
    assert query["type"] == expected and query["status"] == {"option": "securable"}
    assert query.get("name") == extras.get("name")
    filters = query["filters"]
    if "tier" in extras:
        assert filters["map_filters"]["filters"]["map_tier"] == {"min": extras["tier"], "max": extras["tier"]}
    if "rarity" in extras:
        assert filters["type_filters"]["filters"]["rarity"] == {"option": extras["rarity"]}
    for key in ("gem_level", "quality"):
        if key in extras:
            assert filters["misc_filters"]["filters"][key] == {"min": extras[key]}
    url = browser.build_url("Standard", packet, lang=lang)
    assert json.loads(parse_qs(urlsplit(url).query)["q"][0]) == packet


@pytest.mark.parametrize("lang,kind,rarity,name,detail", [
    ("en", "Rings", "Normal", "Superior Topaz Ring", "Item Level: 75"),
    ("ko", "반지", "일반", "상급 토파즈 반지", "아이템 레벨: 75"),
    ("en", "Utility Flasks", "Normal", "Quicksilver Flask", "Item Level: 75"),
    ("en", "Maps", "Normal", "Map (Tier 8)", "Item Level: 75"),
])
def test_normal_requires_both_gates(monkeypatch, lang, kind, rarity, name, detail):
    model = parse(copy(kind, rarity, name, detail, lang=lang))
    monkeypatch.setattr(items, "API_VERIFIED", set())
    monkeypatch.setattr(items, "BROWSER_VERIFIED", {"normal"})
    assert not item_info(model).supported
    with pytest.raises(ValueError, match="거래소 검증"):
        build_query(item_info(model), [])
    monkeypatch.setattr(items, "API_VERIFIED", {"normal"})
    monkeypatch.setattr(items, "BROWSER_VERIFIED", set())
    with pytest.raises(ValueError, match="브라우저 확인 대기"):
        build_query(item_info(model), [])
    monkeypatch.setattr(items, "BROWSER_VERIFIED", {"normal"})
    server = config.OFFICIAL if lang == "en" else config.KAKAO
    info = item_info(model, server)
    query = build_query(info, conditions(info), exact_base=True)["query"]
    assert query["filters"]["type_filters"]["filters"]["rarity"]["option"] == "normal"
    if kind in ("Rings", "반지"):
        assert query["type"] == ("Topaz Ring" if lang == "en" else "토파즈 반지")


@pytest.mark.parametrize("family,text,stat_id", [
    ("elder", "Map is occupied by The Enslaver", "implicit.stat_3624393862|1"),
    ("conqueror", "Map contains Drox's Citadel", "implicit.stat_2563183002|4"),
    ("area", "Area is influenced by The Elder", "implicit.stat_1792283443|2"),
])
def test_map_gate_is_exact_and_identity_cannot_be_removed(monkeypatch, family, text, stat_id):
    model = parse(copy("Maps", "Magic", "Chilled Map (Tier 16)", "Item Level: 80", text + " (implicit)"))
    monkeypatch.setattr(items, "API_VERIFIED", set())
    monkeypatch.setattr(items, "BROWSER_VERIFIED", {stat_id})
    with pytest.raises(ValueError, match="거래소 검증"):
        build_query(item_info(model), [])
    monkeypatch.setattr(items, "API_VERIFIED", {stat_id})
    monkeypatch.setattr(items, "BROWSER_VERIFIED", {stat_id[:-1] + ("2" if stat_id.endswith("1") else "1")})
    with pytest.raises(ValueError, match="브라우저 확인 대기"):
        build_query(item_info(model), [])
    monkeypatch.setattr(items, "BROWSER_VERIFIED", {stat_id})
    info = item_info(model)
    assert info.supported
    assert build_query(info, [])["query"]["stats"] == [{"type": "and", "filters": [{"id": stat_id}]}]


@pytest.mark.parametrize("kind,rarity,name", [
    ("Maps", "Magic", "Chilled Shaper Guardian Map (Tier 16)"),
    ("Maps", "Magic", "Chilled Lair of the Hydra Map (Tier 16)"),
    ("Maps", "Rare", "Foo\nBlight-ravaged Map (Tier 16)"),
    ("Skill Gems", "Gem", "Vaal Fireball"),
    ("Skill Gems", "Gem", "Fire Trap of Blasting"),
    ("Rings", "Magic", "Synthesised Topaz Ring"),
    ("Rings", "Magic", "Foulborn Topaz Ring"),
    ("Rings", "Magic", "Vestigial Topaz Ring"),
    ("Rings", "Magic", "Healthy Two-Stone Ring"),
    ("Rings", "Magic", "Healthy Quicksilver Flask"),
])
def test_unverified_variants_never_widen(kind, rarity, name):
    info = item_info(parse(copy(kind, rarity, name, "Item Level: 75\nLevel: 1")))
    assert not info.supported
    with pytest.raises(ValueError):
        build_query(info, [])


@pytest.mark.parametrize("text,server", [
    (copy("Rings", "Magic", "Healthy Topaz Ring", "Item Level: 75",
          "+30 to maximum Life", "+12% to Lightning Resistance (implicit)"), config.OFFICIAL),
    (copy("특수 플라스크", "마법", "실험자의 수은 플라스크", "아이템 레벨: 50", lang="ko"), config.KAKAO),
    (copy("지도", "마법", "냉각된 지도 (8등급)", "아이템 레벨: 70", lang="ko"), config.KAKAO),
    (copy("Support Gems", "Gem", "Empower Support", "Level: 3 (Max)\nQuality: +20%"), config.OFFICIAL),
])
def test_shared_window_query_in_both_modes(app, monkeypatch, text, server):
    from ratelimit import RateLimiter
    from trade import api, trade_window

    opened, sent = [], []
    monkeypatch.setattr(browser, "open_url", opened.append)
    monkeypatch.setattr(api, "_LEAGUES", ["Standard"])
    monkeypatch.setattr(api, "_POLICIES", {})
    monkeypatch.setattr(api, "_LIMITS", RateLimiter())
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: done(work()))

    def post(method, url, **kwargs):
        sent.append((method, url, kwargs["json"]))
        return SimpleNamespace(status_code=200, headers={}, json=lambda: {"id": "x", "result": [], "total": 0})

    monkeypatch.setattr(requests, "request", post)
    window = trade_window.TradeWindow()
    for mode in ("browser", "api"):
        config.save(mode=mode, server=server, league="Standard")
        window.load(text)
        assert window.search_button.isEnabled(), window.hint.text()
        if "Topaz Ring" in text:
            assert [(row.kind, row.checked) for row in window.stats] == [("explicit", True), ("implicit", False)]
            for row, (check, _, _) in zip(window.stats, window.inputs):
                check.setChecked(row.kind == "implicit")
        assert not sent
        window.search()
    assert len(opened) == len(sent) == 1
    assert sent[0][:2] == ("POST", server + "/api/trade/search/Standard")
    assert sent[0][2] == json.loads(parse_qs(urlsplit(opened[0]).query)["q"][0])
    if "Topaz Ring" in text:
        assert [row["id"].split(".")[0] for row in sent[0][2]["query"]["stats"][0]["filters"]] == ["implicit"]
    assert "검색 결과가 없습니다" in window.result_summary.text()
    window.close()


def test_anointed_amulet_keeps_pipe_id():
    info = item_info(parse(copy("Amulets", "Rare", "Test\nAmber Amulet",
                                "Item Level: 80", "Allocates Charisma (enchant)")))
    stats = conditions(info)
    stats[0].checked = True
    packet = build_query(info, stats)
    assert packet["query"]["stats"][0]["filters"] == [{"id": "enchant.stat_2954116742|6799"}]
    link = browser.build_url("Standard", packet)
    assert "%7C6799" in link


@pytest.mark.parametrize("lang,kind,rarity,name,detail,server,base", [
    ("en", "Maps", "Rare", "Woe Reach\nMap (Tier 8)", "Item Level: 75", config.OFFICIAL, "Map"),
    ("ko", "지도", "희귀", "재앙의 영역\n지도 (8등급)", "아이템 레벨: 75", config.KAKAO, "지도"),
])
def test_rare_map_uses_apt_nonunique_query(lang, kind, rarity, name, detail, server, base):
    info = item_info(parse(copy(kind, rarity, name, detail, lang=lang)), server)
    expected = {
        "query": {
            "status": {"option": "securable"},
            "type": {"option": base, "discriminator": "map"},
            "stats": [{"type": "and", "filters": []}],
            "filters": {
                "misc_filters": {"filters": {"corrupted": {"option": "false"}}},
                "type_filters": {"filters": {"rarity": {"option": "nonunique"}}},
                "map_filters": {"filters": {
                    "map_tier": {"min": 8, "max": 8}, "map_blighted": {"option": "false"},
                }},
            },
        },
        "sort": {"price": "asc"},
    }
    packet = build_query(info, [])
    assert packet == expected
    link = browser.build_url("Standard", packet, server, lang)
    assert json.loads(parse_qs(urlsplit(link).query)["q"][0]) == expected
