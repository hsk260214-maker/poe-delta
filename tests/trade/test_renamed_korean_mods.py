import json

import pytest

from itemmodel import parse
from trade import config, stats
from trade.query import build_query, conditions, item_info


TEXT = "지역에 허상 등장"
REF = "Area contains a Mirage"
MIRAGE = "explicit.stat_2436559047"
MIRROR = "explicit.stat_2398157267"


@pytest.fixture
def clipboard(fixtures):
    return (fixtures / "nightmare_mirage_ko.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("server,base", [(config.KAKAO, "악몽 지도"), (config.OFFICIAL, "Nightmare Map")])
def test_verified_mirage_adds_only_one_default_explicit_filter(clipboard, monkeypatch, server, base):
    info = item_info(parse(clipboard), server)
    rows = conditions(info)
    mirage, = [row for row in rows if row.text == TEXT]
    assert (mirage.kind, mirage.match.id, mirage.match.ref, mirage.checked) == ("explicit", MIRAGE, REF, True)
    packet = build_query(info, rows, monster_level=True)
    query = packet["query"]
    assert query["type"] == base
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "nonunique"}
    assert query["filters"]["map_filters"]["filters"] == {
        "area_level": {"min": 83, "max": 83}, "map_blighted": {"option": "false"},
    }
    filters = query["stats"][0]["filters"]
    assert {"id": MIRROR} in filters
    assert [row for row in filters if row["id"] == MIRAGE] == [{"id": MIRAGE}]
    filters.remove({"id": MIRAGE})
    monkeypatch.setattr(stats, "_korean_aliases", lambda: {})
    assert json.dumps(packet) == json.dumps(build_query(info, conditions(info), monster_level=True))


def test_unverified_enchant_and_inexact_alias_stay_grey(clipboard):
    info = item_info(parse(clipboard.replace(TEXT, f"{TEXT} (enchant)")), config.KAKAO)
    rows = conditions(info)
    mirage, = [row for row in rows if row.text == TEXT]
    assert mirage.kind == "enchant" and not mirage.match.id and not mirage.checked
    assert all("2436559047" not in row["id"] for row in build_query(info, rows)["query"]["stats"][0]["filters"])
    matcher = stats.index()
    assert not matcher.bilingual("지역에  허상 등장", None, "explicit", "Map").id
    assert not matcher.bilingual("지역에 허상 1개 등장", None, "explicit", "Map").id


@pytest.mark.parametrize("field,value", [
    ("kind", "enchant"),
    ("id", MIRROR),
    ("ref", "Area contains a different thing"),
])
def test_alias_disagrees_with_verified_record_and_stays_grey(monkeypatch, clipboard, field, value):
    record = {**stats._korean_aliases()[TEXT], field: value}
    monkeypatch.setattr(stats, "_korean_aliases", lambda: {TEXT: record})
    info = item_info(parse(clipboard), config.KAKAO)
    rows = conditions(info)
    mirage, = [row for row in rows if row.text == TEXT]
    assert not mirage.match.id and not mirage.checked
    assert "일치하지 않습니다" in mirage.match.reason
    assert all(row["id"] != MIRAGE for row in build_query(info, rows)["query"]["stats"][0]["filters"])


def test_existing_english_translation_is_not_replaced_by_the_alias():
    matcher = stats.index()
    existing = "Area contains a Mirror of Delirium"
    assert matcher.resolve(existing, "explicit", "Map").id == MIRROR
    result = matcher.bilingual(TEXT, existing, "explicit", "Map")
    assert not result.id and result.reason == "한국어·번역 연결 불일치"
    assert matcher.bilingual(TEXT, REF, "explicit", "Map").id == MIRAGE
