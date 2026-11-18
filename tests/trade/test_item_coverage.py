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


@pytest.mark.parametrize("lang,server,kind,rarity,name,properties,requirements,description", [
    ("ko", config.KAKAO, "보조 젬", "젬", "체온저하 보조",
     "보조, 냉기\n레벨: 20 (최대)\n퀄리티: +20% (augmented)", "요구 사항:\n레벨: 70\n지능: 111",
     "적에게 명중하는 스킬에 적용됩니다."),
    ("ko", config.OFFICIAL, "보조 젬", "젬", "체온저하 보조",
     "보조, 냉기\n레벨: 20 (augmented)\n퀄리티: +20% (augmented)", "요구사항:\n레벨: 70\n지능: 111",
     "적에게 명중하는 스킬에 적용됩니다."),
    ("en", config.OFFICIAL, "Support Gems", "Gem", "Hypothermia Support",
     "Cold, Support\nLevel: 20 (Max) (augmented)\nQuality: +20% (augmented)",
     "Requirements:\nLevel: 70\nInt: 111", "Supports any skill that hits enemies."),
])
def test_gem_clipboard_uses_properties_not_requirements(lang, server, kind, rarity, name, properties, requirements,
                                                      description):
    model = parse(copy(kind, rarity, name, properties, requirements, description, lang=lang))
    info = item_info(model, server)
    query = build_query(info, conditions(info))["query"]
    assert query["type"] == ("체온저하 보조" if server == config.KAKAO else "Hypothermia Support")
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["gem_level"] == {"min": 20} and misc["quality"] == {"min": 20}


def test_korean_support_gem_clipboard_from_game(fixtures):
    model = parse((fixtures / "fix004_support_gem_ko.txt").read_text(encoding="utf-8"))
    for server, base in ((config.KAKAO, "덫 및 지뢰 피해 보조"), (config.OFFICIAL, "Trap and Mine Damage Support")):
        info = item_info(model, server)
        assert info.supported, info.message
        rows = conditions(info)
        assert [(row.text, row.badge, row.checked, row.minimum, row.maximum) for row in rows] == [
            ("젬 레벨", "젬", True, 20, None), ("퀄리티 (%)", "젬", True, 18, None),
        ]
        query = build_query(info, rows)["query"]
        assert query == build_query(info, [])["query"]
        assert query["stats"] == [{"type": "and", "filters": []}]
        assert query["type"] == base
        assert query["filters"]["misc_filters"]["filters"] == {
            "corrupted": {"option": "false"}, "gem_level": {"min": 20}, "quality": {"min": 18},
        }


@pytest.mark.parametrize("derived_plain_copy", [False, True], ids=["advanced-original", "derived-plain-copy"])
def test_originator_memories_is_optional_map_implicit(fixtures, derived_plain_copy):
    text = (fixtures / "fix004_map_ko.txt").read_text(encoding="utf-8")
    if derived_plain_copy:
        text = text.replace("{ 고정 속성 부여 }\n", "").replace(" — 변경이 불가능한 값", " (implicit)")
    model = parse(text)
    info = item_info(model, config.KAKAO)
    assert info.supported, info.message
    assert info.identity.map_ids == ()
    rows = conditions(info)
    row, = [row for row in rows if row.kind == "implicit"]
    assert row.text == "지역이 태초자의 기억의 영향을 받음" and not row.checked
    assert all(not other.match.id and not other.checked for other in rows if other is not row)
    query = build_query(info, rows)["query"]
    assert query["type"] == {"option": "지도", "discriminator": "map"}
    assert build_query(item_info(model, config.OFFICIAL), [])["query"]["type"] == {
        "option": "Map", "discriminator": "map",
    }
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "normal"}
    assert query["filters"]["map_filters"]["filters"]["map_tier"] == {"min": 16, "max": 16}
    assert query["stats"][0]["filters"] == []
    row.checked = True
    assert build_query(info, rows)["query"]["stats"][0]["filters"] == [{"id": "implicit.stat_2696470877"}]


def test_map_identity_still_blocks_unknown_influence_and_conflicting_tiers():
    text = copy("지도", "희귀", "재앙의 영역\n지도 (16등급)", "지도 등급: 16\n몬스터 레벨: 83",
                "아이템 레벨: 83", "지역이 태초자의 기억의 영향을 받음 (implicit)", lang="ko")
    unknown = item_info(parse(text + "\n지역이 알 수 없는 세력의 영향을 받음 (implicit)"), config.KAKAO)
    assert not unknown.supported and "지도 정체성" in unknown.message
    conflicting = item_info(parse(text.replace("지도 등급: 16", "지도 등급: 16\n지도 등급: 15")), config.KAKAO)
    assert not conflicting.supported and "서로 일치하지 않습니다" in conflicting.message


@pytest.mark.parametrize("kind,name,base", [
    ("특수 플라스크", "분석가의 비취 플라스크 - 영양", "비취 플라스크"),
    ("반지", "차원의 토파즈 반지 - 레인저", "토파즈 반지"),
])
def test_korean_magic_clipboard_with_suffix(kind, name, base):
    model = parse(copy(kind, "마법", name, "아이템 레벨: 83", lang="ko"))
    info = item_info(model, config.KAKAO)
    query = build_query(info, conditions(info), exact_base=True)["query"]
    assert query["type"] == base
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "magic"}


def test_korean_magic_flask_clipboard_from_game(fixtures):
    model = parse((fixtures / "fix004_flask_ko.txt").read_text(encoding="utf-8"))
    info = item_info(model, config.KAKAO)
    rows = conditions(info)
    assert [(row.text, row.kind, row.checked) for row in rows] == [
        ("충전이 가득 차면 사용", "enchant", False),
        ("사용 시 연막 생성", "implicit", False),
        ("지속시간 23% 증가", "explicit", True),
        ("효과를 받는 동안 이동 속도 10% 증가", "explicit", True),
    ]
    assert [row.badge for row in rows[:2]] == ["인챈트", "고정"]
    query = build_query(info, rows)["query"]
    assert query["type"] == "휘안석 플라스크"
    assert build_query(item_info(model, config.OFFICIAL), [])["query"]["type"] == "Stibnite Flask"
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "magic"}


def test_nightmare_map_clipboard_allows_exact_base_without_tier(fixtures):
    text = (fixtures / "fix004_nightmare_map_ko.txt").read_text(encoding="utf-8")
    model = parse(text)
    for server, base in ((config.KAKAO, "악몽 지도"), (config.OFFICIAL, "Nightmare Map")):
        info = item_info(model, server)
        assert info.supported, info.message
        assert info.identity.map_ids == ()
        rows = conditions(info)
        assert any(row.text == "플레이어의 효과 범위 27% 감폭" for row in rows)
        query = build_query(info, rows)["query"]
        assert query["type"] == base
        assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "nonunique"}
        assert "map_tier" not in query["filters"]["map_filters"]["filters"]
    generic = item_info(parse(text.replace("\n악몽 지도\n", "\n지도\n")), config.KAKAO)
    assert not generic.supported and "지도 등급을 읽을 수 없습니다" in generic.message


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
