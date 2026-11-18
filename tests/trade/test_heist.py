import json
from urllib.parse import parse_qs, urlsplit

import pytest
from PySide6.QtWidgets import QLabel

from itemmodel import parse
from trade import browser, config, heist
from trade.query import build_query, conditions, item_info


CONTRACT = """Item Class: Contracts
Rarity: Rare
Gale Pledge
Contract: Repository
--------
Client: Castor Pollinius III
Heist Target: Golden Xoplotli Idol (Priceless)
Area Level: 75
Requires Demolition (Level 1 (unmet))
--------
Item Level: 75
--------
Patrolling Monsters deal 25% increased Damage
"""
BLUEPRINT = """Item Class: Blueprints
Rarity: Magic
Deployed Blueprint: Mansion
--------
Area Level: 83
Wings Revealed: 1/4
Escape Routes Revealed: 1/8
Requires Brute Force (Level 2 (unmet))
--------
Item Level: 84
"""


@pytest.mark.parametrize("en,ko,key", heist.JOBS)
def test_contract_jobs(en, ko, key):
    # APT의 한국어 개별 속성 문자열만 검사한다. 전체 복사 자료는 원문을 기다린다.
    data = heist.read([f"{ko} 필요(2레벨)", "강탈 대상: 대상 (환산 불가능한 가치)"], "ko", heist.CONTRACT)
    assert (data.job, data.job_level, data.priceless) == (key, 2, True)
    text = CONTRACT.replace("Demolition", en)
    if en != "Demolition":
        text = text.replace("(Priceless)", "(Valuable)")
    info = item_info(parse(text))
    query = build_query(info, conditions(info))["query"]
    assert "type" not in query
    assert query["filters"]["type_filters"]["filters"] == {
        "category": {"option": "heistmission.contract"}, "rarity": {"option": "nonunique"},
    }
    expected = {f"heist_{key}": {"min": 1}}
    if en == "Demolition":
        expected["heist_objective_value"] = {"option": "priceless"}
    assert query["filters"]["heist_filters"]["filters"] == expected
    exact = build_query(info, conditions(info), exact_base=True)["query"]
    assert exact["type"] == "Contract: Repository"
    assert exact["filters"]["type_filters"]["filters"] == {"rarity": {"option": "nonunique"}}


def test_blueprint_ranges_and_no_enchant():
    assert heist.read(["지역 레벨: 83", "부속 건물 드러남: 1/4"], "ko", heist.BLUEPRINT).wings == (1, 4)
    info = item_info(parse(BLUEPRINT))
    rows = conditions(info)
    query = build_query(info, rows)["query"]
    assert query["type"] == "Blueprint: Mansion"
    assert query["filters"]["heist_filters"]["filters"] == {
        "heist_wings": {"min": 1, "max": 1}, "heist_max_wings": {"min": 4, "max": 4},
    }
    assert query["stats"][1:] == [{"type": "not", "filters": [
        {"id": "pseudo.pseudo_number_of_enchant_mods", "value": {}, "disabled": False},
    ]}]
    rows[0].maximum = None
    rows[2].checked = False
    broader = build_query(info, rows, exact_base=False)["query"]
    assert "type" not in broader and len(broader["stats"]) == 1
    assert broader["filters"]["heist_filters"]["filters"]["heist_wings"] == {"min": 1}
    assert broader["filters"]["type_filters"]["filters"] == {
        "category": {"option": "heistmission.blueprint"}, "rarity": {"option": "nonunique"},
    }


def test_kakao_contract_advanced_clipboard(fixtures):
    model = parse((fixtures / "heist_contract_ko.txt").read_text(encoding="utf-8"))
    info = item_info(model, config.KAKAO)
    rows = conditions(info)
    query = build_query(info, rows)["query"]
    assert query["filters"]["heist_filters"]["filters"] == {"heist_engineering": {"min": 5}}
    assert heist.read(model.head, "ko", heist.CONTRACT).area == 83
    assert not any(row.kind == "heist_area" for row in rows)
    assert build_query(info, rows, exact_base=True)["query"]["type"] == "계약: 벙커"
    explicit = [row for row in rows if row.kind == "explicit"]
    assert [row.text for row in explicit] == [
        "몬스터가 명중 시 20%의 확률로 점화, 동결, 감전 유발",
        "순찰 무리 대신 정예 순찰 무리가 등장할 확률 29% 증가",
        "플레이어가 쇠약화 저주에 걸림",
        "경보 레벨 25%당 플레이어의 플라스크 충전량 12% 감소",
    ]
    assert all(row.match.id.startswith("explicit.") or row.match.reason for row in explicit)


def test_kakao_blueprint_without_enchant_clipboard(fixtures):
    model = parse((fixtures / "heist_blueprint_no_enchant_ko.txt").read_text(encoding="utf-8"))
    info = item_info(model, config.KAKAO)
    rows = conditions(info)
    query = build_query(info, rows)["query"]
    assert query["type"] == "도면: 기록 보관소"
    assert query["filters"]["heist_filters"]["filters"] == {
        "heist_wings": {"min": 1, "max": 1}, "heist_max_wings": {"min": 3, "max": 3},
    }
    assert query["stats"][1:] == [{"type": "not", "filters": [
        {"id": "pseudo.pseudo_number_of_enchant_mods", "value": {}, "disabled": False},
    ]}]
    assert not any(row.kind == "heist_job" for row in rows)
    area, = [row for row in rows if row.kind == "heist_area"]
    assert (area.checked, area.minimum, area.maximum) == (False, 83, None)
    assert "map_filters" not in query["filters"]
    area.checked = True
    assert build_query(info, rows)["query"]["filters"]["map_filters"]["filters"] == {"area_level": {"min": 83}}


def test_blueprint_lockdown_enchant_select():
    info = item_info(parse(BLUEPRINT + "--------\n{ Enchant Modifier }\n10% increased time before Lockdown\n"))
    query = build_query(info, conditions(info))["query"]
    assert query["stats"] == [{"type": "and", "filters": [{"id": "enchant.stat_429193272"}]}]


def test_kakao_blueprint_advanced_clipboard(fixtures):
    from trade.stats import index

    model = parse((fixtures / "heist_blueprint_ko.txt").read_text(encoding="utf-8"))
    assert item_info(model, config.OFFICIAL).base == "Blueprint: Underbelly"
    info = item_info(model, config.KAKAO)
    rows = conditions(info)
    query = build_query(info, rows)["query"]
    assert query["type"] == "도면: 취약 지점"
    assert query["filters"]["type_filters"]["filters"] == {"rarity": {"option": "nonunique"}}
    assert query["filters"]["heist_filters"]["filters"] == {
        "heist_wings": {"min": 1, "max": 1}, "heist_max_wings": {"min": 3, "max": 3},
    }
    expected = index().match("Heist Targets are always Enchanted Armaments", "enchant", heist.BLUEPRINT)
    assert expected.id.startswith("enchant.")
    assert [group["type"] for group in query["stats"]] == ["and"]
    assert {"id": expected.id} in query["stats"][0]["filters"]
    explicit = [row for row in rows if row.kind == "explicit"]
    assert [row.text for row in explicit] == [
        "지원군의 공격 속도 19% 증가", "지원군의 시전 속도 18% 증가",
        "지원군의 이동 속도 15% 증가", "몬스터의 주문 명중 시 이동 방해 유발",
    ]
    assert all(row.checked if row.match.id else row.match.reason for row in explicit)


@pytest.mark.parametrize("text, reason", [
    (CONTRACT.replace("Demolition", "Invented"), "필요 직업"),
    (BLUEPRINT + "--------\nUnknown effect (enchant)\n", "인챈트"),
    (BLUEPRINT.replace("1/4", "5/4"), "구역 수"),
    (BLUEPRINT + "--------\nUnidentified\n", "미확인"),
    (BLUEPRINT.replace("Deployed Blueprint: Mansion", "Unknown"), "식별"),
])
def test_blocked_items_do_not_broaden_search(app, text, reason):
    from trade.trade_window import TradeWindow

    config.save(mode="browser", server=config.OFFICIAL, league="Standard")
    window = TradeWindow()
    window.load(text)
    assert not window.search_button.isEnabled()
    assert reason in window.hint.text()
    if reason in ("필요 직업", "인챈트"):
        assert any(not check.isEnabled() and check.toolTip() for check, _, _ in window.inputs)
    with pytest.raises(ValueError, match=reason):
        build_query(window.info, conditions(window.info))
    window.close()


def test_unique_contract_uses_name_and_type_only():
    text = "Item Class: Contracts\nRarity: Unique\nContract: The Twins\nVengeful Contract\n--------\nItem Level: 83"
    info = item_info(parse(text))
    query = build_query(info, conditions(info))["query"]
    assert query["name"] == "Contract: The Twins" and query["type"] == "Vengeful Contract"
    assert "type_filters" not in query["filters"] and "heist_filters" not in query["filters"]


def test_area_gate_and_both_search_modes(app, monkeypatch):
    from trade import api, trade_window

    opened, sent = [], []
    monkeypatch.setattr(browser, "open_url", opened.append)
    monkeypatch.setattr(api.TradeClient, "leagues", lambda *args: ["Standard"])

    def search(_self, _league, query, *_args):
        sent.append(query)
        return {"id": "fixture", "result": [], "total": 0}

    monkeypatch.setattr(api.TradeClient, "search", search)
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: done(work()))
    monkeypatch.setattr(heist, "AREA_API_VERIFIED", frozenset())
    monkeypatch.setattr(heist, "AREA_BROWSER_VERIFIED", {heist.BLUEPRINT})
    config.save(mode="browser", server=config.OFFICIAL, league="Standard")
    window = trade_window.TradeWindow()
    window.load(BLUEPRINT)
    assert any("지역 레벨 조건은 아직 지원하지 않습니다" in label.text() for label in window.findChildren(QLabel))
    assert not any(row.kind == "heist_area" for row in window.stats)
    monkeypatch.setattr(heist, "AREA_API_VERIFIED", {heist.BLUEPRINT})
    for mode in ("browser", "api"):
        config.save(mode=mode, server=config.OFFICIAL, league="Standard")
        window.load(BLUEPRINT)
        assert window.base_button.isChecked()
        assert window.base_button.text() == "정확한 베이스: Blueprint: Mansion"
        window.base_button.click()
        assert window.base_button.text() == "도면 전체 검색"
        check, minimum, _ = next(inputs for row, inputs in zip(window.stats, window.inputs) if row.kind == "heist_area")
        assert not check.isChecked() and minimum.text() == "83"
        check.setChecked(True)
        assert not sent
        window.search()
    assert len(opened) == len(sent) == 1
    assert json.loads(parse_qs(urlsplit(opened[0]).query)["q"][0]) == sent[0]
    assert sent[0]["query"]["status"] == {"option": "securable"}
    assert sent[0]["query"]["filters"]["map_filters"]["filters"] == {"area_level": {"min": 83}}
    assert window.result_summary.text() == "전체 0개 · 검색 결과가 없습니다"
    window.close()
