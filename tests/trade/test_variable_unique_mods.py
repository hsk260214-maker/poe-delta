import pytest

from itemmodel import parse
from trade import config, unique_mods
from trade.query import build_query, conditions, item_info
from trade.stats import index
from trade.trade_window import TradeWindow


ADVANCED = ("살아 있는 번개(기동된 무기-신성한 병기) 최대 수 2배\n"
            "살아 있는 번개(기동된 무기-신성한 병기) 외의 다른 소환수 보유 불가")
NORMAL = "살아 있는 번개의 최대 수 2배\n살아 있는 번개 외의 다른 소환수 보유 불가"


@pytest.fixture
def monarch_text(fixtures):
    return (fixtures / "dark_monarch_ko.txt").read_text(encoding="utf-8")


def query_stats(info, rows):
    return build_query(info, rows)["query"]["stats"][0]["filters"]


def test_destiny_defaults_choose_only_the_verified_pool(fixtures):
    model = parse((fixtures / "bound_by_destiny_ko.txt").read_text(encoding="utf-8"))
    for server in (config.OFFICIAL, config.KAKAO):
        info = item_info(model, server)
        rows = conditions(info)
        assert len(rows) == 3 and all(row.checked and row.match.id for row in rows)
        assert [row.minimum for row in rows] == [None, 2, 1]
        assert query_stats(info, rows) == [
            {"id": row.match.id, **({"value": {"min": row.minimum}} if row.minimum is not None else {})}
            for row in rows
        ]
    other = item_info(parse((fixtures / "unique_ko.txt").read_text(encoding="utf-8")), config.KAKAO)
    assert not any(row.checked for row in conditions(other))


def test_all_52_destiny_refs_match_the_pinned_korean_id():
    matcher = index()
    pool = unique_mods.destiny_pool()
    assert len(pool) == 52
    verified = set()
    for entry_no, entry in enumerate(matcher.ko.entries):
        ids = entry["ids"].get("explicit", ())
        if len(ids) == 1 and (entry["ref"], ids[0]) in pool:
            for form in matcher.ko.by_entry[entry_no]:
                result = matcher.bilingual(form["string"].replace("#", "7"), None, "explicit", "Jewel")
                assert (result.ref, result.id) == (entry["ref"], ids[0])
            verified.add((entry["ref"], ids[0]))
    assert verified == pool


def test_real_advanced_monarch_pair_keeps_parser_boundaries_and_is_closed(monkeypatch, monarch_text):
    monkeypatch.setattr(unique_mods, "LIVING_BROWSER_VERIFIED", False)
    model = parse(monarch_text)
    pair = model.mods[-2:]
    assert [m.text for m in pair] == ADVANCED.splitlines()
    assert pair[0].copy_section == pair[1].copy_section and pair[0].copy_section is not None
    assert pair[0].copy_block == pair[1].copy_block and pair[0].copy_block > 0
    assert pair[0].copy_line + 1 == pair[1].copy_line
    assert pair[1].unscalable
    info = item_info(model, config.KAKAO)
    rows = conditions(info)
    assert [row.text for row in rows[-2:]] == ADVANCED.splitlines()
    assert all("브라우저 확인 대기" in row.match.reason for row in rows[-2:])
    assert not query_stats(info, rows)


@pytest.mark.parametrize("file,joined", [("dark_monarch_ko.txt", ADVANCED),
    ("dark_monarch_normal_apt_derived_ko.txt", NORMAL)])
def test_monarch_advanced_and_apt_derived_normal_send_one_id(app, fixtures, monkeypatch, file, joined):
    monkeypatch.setattr(unique_mods, "LIVING_BROWSER_VERIFIED", True)
    config.save(mode="browser", server=config.KAKAO, league="Covens")
    window = TradeWindow()
    window.load((fixtures / file).read_text(encoding="utf-8"))
    row, = [row for row in window.stats if row.checked]
    assert (row.match.id, row.text, row.detail) == (unique_mods.LIVING_ID, joined.splitlines()[0], joined)
    check, lo, hi = window.inputs[window.stats.index(row)]
    assert check.toolTip() == joined and lo.isHidden() and hi.isHidden()
    assert window._query()["query"]["stats"][0]["filters"] == [{"id": unique_mods.LIVING_ID}]
    window.close()


@pytest.mark.parametrize("case,expected", [
    ("extra_header", "\n{ 고유 속성 부여 }\n"),
    ("section", "\n--------\n"),
    ("kind", " (enchant)\n"),
])
def test_monarch_does_not_pair_across_boundaries(monkeypatch, monarch_text, case, expected):
    monkeypatch.setattr(unique_mods, "LIVING_BROWSER_VERIFIED", True)
    info = item_info(parse(monarch_text.replace(ADVANCED, expected.join(ADVANCED.splitlines()))), config.KAKAO)
    assert not query_stats(info, conditions(info)), case


@pytest.mark.parametrize("replacement", [
    "\n".join(reversed(ADVANCED.splitlines())), ADVANCED.splitlines()[0],
    ADVANCED.replace("기동된 무기-신성한 병기", "다른 주석"),
    ADVANCED.replace("살아 있는 번개", "신성한 병기", 1),
    "신성한 병기 최대 수 2배\n신성한 병기 외의 다른 소환수 보유 불가",
])
def test_monarch_rejects_nonmatching_copy_pairs(monkeypatch, monarch_text, replacement):
    monkeypatch.setattr(unique_mods, "LIVING_BROWSER_VERIFIED", True)
    info = item_info(parse(monarch_text.replace(ADVANCED, replacement)), config.KAKAO)
    assert not query_stats(info, conditions(info))


def test_other_14_monarch_variants_stay_closed(monkeypatch, monarch_text):
    monkeypatch.setattr(unique_mods, "LIVING_BROWSER_VERIFIED", True)
    matcher = index().ko
    variants = {}
    for entry_no, entry in enumerate(matcher.entries):
        for stat_id in entry["ids"].get("explicit", ()):
            if stat_id.startswith(unique_mods.MONARCH_PREFIX):
                variants[int(stat_id.rsplit("|", 1)[1])] = matcher.by_entry[entry_no][0]["string"]
    for variant in range(1, 15):
        info = item_info(parse(monarch_text.replace(ADVANCED, variants[variant])), config.KAKAO)
        assert not query_stats(info, conditions(info)), variant
