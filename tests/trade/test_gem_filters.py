import json
from urllib.parse import parse_qs, urlsplit

import pytest

from itemmodel import parse
from trade import browser, config
from trade.query import build_query, conditions, item_info


ZERO = "Item Class: Skill Gems\nRarity: Gem\nFireball\n--------\nLevel: 5\n--------\nCorrupted"
NOTICE = "조건이 바뀌었습니다. 검색을 눌러 주세요"


def test_gem_rows_override_defaults_per_key():
    info = item_info(parse(ZERO))
    level, quality = conditions(info, ratio=0.5)
    assert (level.minimum, quality.minimum) == (5, 0)
    level.minimum, level.maximum = None, 10
    quality.minimum, quality.maximum = 2, 20

    def misc(rows, *, corrupted=False):
        query = build_query(info, rows, corrupted=corrupted)["query"]
        assert query["type"] == "Fireball"
        assert query["stats"] == [{"type": "and", "filters": []}]
        return query["filters"].get("misc_filters", {}).get("filters", {})

    assert misc([]) == {"gem_level": {"min": 5}, "quality": {"min": 0}}
    assert misc([level, quality]) == {"gem_level": {"max": 10}, "quality": {"min": 2, "max": 20}}
    level.checked = False
    assert misc([level, quality]) == {"quality": {"min": 2, "max": 20}}
    assert misc([level]) == {"quality": {"min": 0}}
    level.checked = True
    level.maximum = None
    assert misc([level, quality]) == {"quality": {"min": 2, "max": 20}}
    level.checked = quality.checked = False
    assert misc([level, quality], corrupted=True) == {"corrupted": {"option": "true"}}
    assert "misc_filters" not in build_query(info, [level, quality], corrupted=False)["query"]["filters"]


@pytest.mark.parametrize("index,minimum,maximum", [
    (0, 0, None), (0, None, 0), (1, -1, None), (1, None, -1),
    (0, 1.5, None), (1, None, 2.5), (0, 5, 4), (1, 2, 0), (1, None, float("inf")),
])
def test_gem_bounds_reject_invalid_checked_values(index, minimum, maximum):
    info = item_info(parse(ZERO))
    rows = conditions(info)
    rows[index].minimum, rows[index].maximum = minimum, maximum
    with pytest.raises(ValueError, match="정수|최소값"):
        build_query(info, rows)
    rows[index].checked = False
    build_query(info, rows)


def test_gem_controls_share_queries_and_clear_stale_results(app, fixtures, monkeypatch):
    from trade import api, trade_window

    opened, sent = [], []
    monkeypatch.setattr(browser, "open_url", opened.append)
    monkeypatch.setattr(api.TradeClient, "leagues", lambda *args: ["Standard"])
    monkeypatch.setattr(api.TradeClient, "remaining", lambda *args: 0)
    monkeypatch.setattr(trade_window, "run_async", lambda work, done, fail: done(work()))

    def search(_client, _league, packet, *_args):
        sent.append(packet)
        return {"id": "fixture", "result": [], "total": 0}

    monkeypatch.setattr(api.TradeClient, "search", search)
    text = (fixtures / "fix004_support_gem_ko.txt").read_text(encoding="utf-8")
    window = trade_window.TradeWindow()
    for mode in ("browser", "api"):
        config.save(mode=mode, server=config.OFFICIAL, league="Standard")
        window.load(text)
        assert [(check.text(), check.isChecked(), lo.text(), hi.text()) for check, lo, hi in window.inputs] == [
            ("젬 레벨", True, "20", ""), ("퀄리티 (%)", True, "18", ""),
        ]
        (level, minimum, maximum), (quality, _, _) = window.inputs
        minimum.setText("1.5")
        assert not window.search_button.isEnabled()
        level.setChecked(False)
        assert window.search_button.isEnabled()
        minimum.clear()
        maximum.setText("19")
        level.setChecked(True)
        quality.setChecked(False)
        assert window.result_summary.text() == NOTICE and not sent
        window.search()
    assert len(sent) == len(opened) == 1
    assert json.loads(parse_qs(urlsplit(opened[0]).query)["q"][0]) == sent[0]
    assert sent[0]["query"]["filters"]["misc_filters"]["filters"] == {
        "corrupted": {"option": "false"}, "gem_level": {"max": 19},
    }
    assert window.open_button.isEnabled() and window._result_link
    quality.setChecked(True)
    assert not window.open_button.isEnabled() and not window._result_link
    assert window.result_summary.text() == NOTICE and len(sent) == 1
    window.load(ZERO)
    assert [(c.isChecked(), lo.text(), hi.text()) for c, lo, hi in window.inputs] == [
        (True, "5", ""), (True, "0", ""),
    ]
    window.load((fixtures / "rare_en.txt").read_text(encoding="utf-8"))
    assert all(row.kind != "gem_filter" for row in window.stats)
    window.close()
