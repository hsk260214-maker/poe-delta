from dataclasses import replace

import pytest

from itemmodel import parse
from trade import browser, config, resistance
from trade.query import StatCondition, build_query, conditions, item_info, resistance_rows
from trade.stats import Match, index
from trade.trade_window import TradeWindow


AMULET = ("아이템 종류: 목걸이\n아이템 희귀도: 희귀\n시신의 부적\n호박 목걸이\n--------\n"
          "아이템 레벨: 83\n--------\n번개 저항 +34%\n냉기 저항 +32%")
ALL = AMULET.replace("번개 저항 +34%\n냉기 저항 +32%", "모든 원소 저항 +12%\n화염 저항 +30%\n카오스 저항 +20%")
HYBRID = ALL + "\n화염 및 카오스 저항 +10%"


@pytest.mark.parametrize("example,total,minimum", [("amulet", 66, 59), ("ring", 71, 63), ("all", 66, 59)])
def test_three_copied_totals(fixtures, monkeypatch, example, total, minimum):
    monkeypatch.setattr(resistance, "BROWSER_VERIFIED", False)
    text = {"amulet": AMULET, "all": ALL,
            "ring": (fixtures / "two_stone_ring_ko.txt").read_text(encoding="utf-8")}[example]
    info = item_info(parse(text), config.KAKAO)
    original = conditions(info)
    assert resistance_rows(info, original) == (original, "")
    per_row = build_query(info, original)
    monkeypatch.setattr(resistance, "BROWSER_VERIFIED", True)
    for row in original:
        if resistance.role(row) == "elemental":
            row.maximum = 999
    rows, note = resistance_rows(info, original)
    assert not note
    combined, = [row for row in rows if row.kind == resistance.ROW_KIND]
    assert combined.text == f"총 원소 저항 +{total}%"
    assert combined.minimum == minimum and combined.checked and combined.badge == "합산"
    assert rows.index(combined) == next(i for i, row in enumerate(original) if resistance.role(row) == "elemental")
    combined_id = index().total_resistance_id
    payload = build_query(info, rows, total_resistance=True)["query"]["stats"][0]["filters"]
    assert {"id": combined_id, "value": {"min": minimum}} in payload
    assert all(entry["id"] not in {row.match.id for row in original if resistance.role(row) == "elemental"}
               for entry in payload)
    for row in original:
        if resistance.role(row) == "elemental":
            row.maximum = None
    assert build_query(info, rows) == per_row


def test_signed_copy_and_conservative_classification(monkeypatch):
    monkeypatch.setattr(resistance, "BROWSER_VERIFIED", True)
    info = item_info(parse(AMULET.replace("냉기 저항 +32%", "화염 저항 -9%")), config.KAKAO)
    rows = conditions(info)
    assert resistance.copied_total(rows)[1] == 25
    ref = "+#% to Fire Resistance"
    unresolved = StatCondition("알 수 없는 문구", "explicit", Match(candidate_refs=frozenset({ref})))
    no_candidates = replace(unresolved, text="확인할 수 없는 저항", match=Match())
    unrelated = replace(unresolved, text="저항 효과", match=Match(candidate_refs=frozenset({"Maximum Resistances"})))
    chaos = next(row for row in conditions(item_info(parse(ALL), config.KAKAO)) if "카오스" in row.text)
    for blocked in (unresolved, no_candidates):
        assert resistance_rows(info, [*rows, blocked])[1]
    assert any(row.kind == resistance.ROW_KIND for row in resistance_rows(info, [*rows, unrelated, chaos])[0])
    assert index().bilingual("화염 저항 +46%", "+45% to Fire Resistance", "explicit", "Ring").candidate_refs >= {ref}


def test_total_mode_restores_values_and_bulk_clear_includes_checked_hybrid(app, monkeypatch):
    monkeypatch.setattr(resistance, "BROWSER_VERIFIED", False)
    config.save(server=config.KAKAO, mode="browser", league="Standard")
    opened = []
    monkeypatch.setattr(browser, "open_url", opened.append)
    window = TradeWindow()
    window.load(HYBRID)
    assert window.resistance_button.isHidden()
    monkeypatch.setattr(resistance, "BROWSER_VERIFIED", True)
    window.load(HYBRID)
    total, = [w for r, w in zip(window.stats, window.inputs) if resistance.role(r) == "total"]
    hybrid_row, = [r for r in window.stats if resistance.role(r) == "hybrid"]
    hybrid = window.inputs[window.stats.index(hybrid_row)]
    normal, = [w for r, w in zip(window.stats, window.inputs) if "화염 저항 +30%" == r.text]
    chaos, = [w for r, w in zip(window.stats, window.inputs) if "카오스 저항 +20" in r.text]
    assert window.total_resistance and not window.resistance_button.isHidden()
    assert total[0].isChecked() and not normal[0].isEnabled() and not hybrid[0].isChecked()
    assert resistance.HYBRID_HINT in hybrid[0].toolTip()
    total[0].click()
    assert not normal[0].isEnabled()
    window.select_all.click()
    assert total[0].isChecked() and not hybrid[0].isChecked()
    hybrid[0].click()
    assert any(p["id"] == hybrid_row.match.id for p in window._query()["query"]["stats"][0]["filters"])
    window.clear_all.click()
    assert not hybrid[0].isChecked() and not total[0].isChecked()
    total[0].click()
    total[1].setText("65")
    chaos[1].setText("17")
    generation = window._generation
    window.resistance_button.click()
    assert window._generation == generation + 1 and normal[0].isEnabled() and normal[0].isChecked()
    assert total[0].parentWidget().isHidden() and chaos[1].text() == "17"
    normal[1].setText("24")
    normal[2].setText("44")
    hybrid[0].setChecked(False)
    window.resistance_button.click()
    assert not normal[0].isEnabled() and total[1].text() == "65"
    assert chaos[1].text() == "17" and not opened
    window.resistance_button.click()
    assert (normal[1].text(), normal[2].text(), hybrid[0].isChecked()) == ("24", "44", False)
    window.close()
