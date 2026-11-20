import hashlib
import json
from copy import deepcopy
from pathlib import Path
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

import map_avoid_panel
import map_presets
import map_regex
import map_warn
import mapcheck


REGEN = "players cannot regenerate life, mana or energy shield"
CURSE = "players are cursed with enfeeble"
FIXTURES = Path(__file__).parent / "trade" / "fixtures"


def test_site_numeric_port_matches_reference_for_every_input():
    # 승인 HTML에 옮긴 사이트 함수에서 10~999 출력을 LF로 이은 SHA-256.
    output = "\n".join(map_regex.regex_calc(value) for value in range(10, 1000))
    assert hashlib.sha256(output.encode()).hexdigest() == "0795dfd9a85f3518ed81fc83d16072e36da7fc7a04c2d0ce4a002f915265d90c"


def test_site_identical_golden_unchanged_pack_threshold():
    assert map_regex.build([], mapcheck.catalog(), map_regex.load_patterns(mapcheck.catalog()),
                           limits={"pack": "35"}).text == '"규모:.*(3[5-9]|[4-9].|[1-9]..)%"'


def test_app_golden_any_keeps_option_order_and_operator():
    catalog = [{"key": "a", "ko": "가"}, {"key": "b", "ko": "나"}, {"key": "c", "ko": "다"}]
    patterns = {"a": [("가", "a"), ("갸", "aa")], "b": [("나", "b")], "c": [("다", "c")]}
    assert map_regex.build(["c"], catalog, patterns, wanted=["a", "b"], limits={"pack": "35"}).text == (
        '"가|갸|나" "!다" "규모:.*(3[5-9]|[4-9].|[1-9]..)%"'
    )


@pytest.mark.parametrize("mode,extras", [
    ("or", '"화폐 더 많음: .([4-9].|[1-9]..)%|지도 더 많음: .([3-9].|[1-9]..)%"'),
    ("and", '"화폐 더 많음: .([4-9].|[1-9]..)%" "지도 더 많음: .([3-9].|[1-9]..)%"'),
])
def test_app_golden_all_atlas_rarity_and_narrowed_prefixes(mode, extras):
    catalog = [{"key": "a", "ko": "가"}, {"key": "b", "ko": "나"}]
    patterns = {"a": [("가", "a"), ("갸", "aa")], "b": [("나", "b")]}
    assert map_regex.build([], catalog, patterns, wanted=["a", "b"], mode="all",
                           limits={"drops": "80", "rarity": "105", "currency": "40", "map": "30"},
                           limit_mode=mode).text == (
        '"가|갸" "나" "획득물:.*([8-9].|[1-9]..)%" "희귀도:.*(10[5-9]|1[1-9].|[2-9]..)%" ' + extras
    )


@pytest.mark.parametrize("threshold", [10, 15, 19, 20, 35, 89, 90, 99, 100, 105, 120, 123, 191, 200, 998, 999])
def test_korean_numeric_threshold_boundaries(threshold):
    for key, name in map_regex.LIMIT_NAMES.items():
        pattern = re.compile(map_regex.PREFIXES[key] + map_regex.regex_calc(threshold))
        for value in range(threshold - 1, min(999, threshold + 1) + 1):
            assert bool(pattern.search(f"{name}: +{value}% (augmented)")) == (value >= threshold)


def test_repoe_upper_bounds_and_full_korean_map_line_corpus(monkeypatch):
    import sys

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    from audit_map_regex import bounds

    audit = json.loads((FIXTURES / "map_regex_repoe_audit.json").read_text(encoding="utf-8"))
    assert bounds(audit) == {"drops": 258, "rarity": 878, "pack": 246, "currency": 516, "map": 428}
    over = deepcopy(audit)
    over["maxima"]["currency"]["prefix"][0] = 1000
    with pytest.raises(ValueError, match="지원 범위 초과"):
        bounds(over)

    lines = set(audit["lines"]) | {"아이템 희귀도: 희귀", "지도 (16등급)", "지도 등급: 16"}
    for path in FIXTURES.glob("*_ko.txt"):
        text = path.read_text(encoding="utf-8")
        if text.startswith("아이템 종류: 지도\n"):
            lines.update(text.splitlines())
    for key, prefix in map_regex.PREFIXES.items():
        pattern = re.compile(prefix + map_regex.regex_calc(10))
        assert all(line.startswith(map_regex.LIMIT_NAMES[key] + ":") for line in lines if pattern.search(line))
        for line in lines:
            if value := re.fullmatch(re.escape(map_regex.LIMIT_NAMES[key]) + r": \+(\d+)%(?: \(augmented\))?", line):
                assert int(value[1]) <= 999


@pytest.mark.parametrize("missing", ["catalog", "fragments"])
def test_unavailable_data_preserves_presets_and_warning_keys(app, monkeypatch, missing):
    active, spare = map_presets.blank("파밍"), map_presets.blank("보조")
    active["order"] = [[REGEN, "avoid"]]
    spare["order"] = [[CURSE, "want"]]
    settings = map_presets.records([active, spare], active["id"])
    saves = []
    monkeypatch.setattr(map_avoid_panel, "load_settings", lambda: deepcopy(settings))
    monkeypatch.setattr(map_avoid_panel, "save_settings", saves.append)
    monkeypatch.setattr(map_warn, "load_settings", lambda: deepcopy(settings))
    if missing == "catalog":
        monkeypatch.setattr(mapcheck, "catalog", lambda: [])
    else:
        monkeypatch.setattr(map_regex, "load_patterns", lambda _: {})
    host = QWidget()
    card = map_avoid_panel.MapAvoidCard(host, QVBoxLayout(host))
    buttons = {button.text(): button for button in host.findChildren(QPushButton)}
    clipboard = QApplication.clipboard()
    clipboard.setText("보존")
    for name in ("새 프리셋", "복제", "정규식 복사"):
        assert not buttons[name].isEnabled()
        buttons[name].click()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == "보존"
    assert not card.regex_text.text() and "그대로" in card.regex_status.text()
    assert not saves and map_warn.avoid_keys() == {REGEN}
    host.close()


@pytest.fixture
def panel(app, monkeypatch):
    settings = {"map_avoid": [REGEN], "unrelated": {"ok": True}}
    saves = []

    def save(value):
        settings.update(deepcopy(value))
        saves.append(deepcopy(value))

    monkeypatch.setattr(map_avoid_panel, "load_settings", lambda: deepcopy(settings))
    monkeypatch.setattr(map_avoid_panel, "save_settings", save)
    monkeypatch.setattr(map_warn, "load_settings", lambda: deepcopy(settings))
    host = QWidget()
    card = map_avoid_panel.MapAvoidCard(host, QVBoxLayout(host))
    yield card, settings, saves
    host.close()


def test_presets_crud_and_toggle_writes_one_ordered_warning_mirror(panel):
    card, settings, saves = panel
    assert len(saves) == 1 and map_warn.avoid_keys() == {REGEN}
    base = card.active
    for action in (card._new, card._duplicate):
        n = len(saves)
        action()
        assert len(saves) == n + 1 and settings["map_preset_active"] == card.active
    duplicate = card.active
    assert card.preset["name"] == "새 프리셋 복사본"
    for bad in (" ", "기본", "x" * 21):
        n = len(saves)
        card.preset_name.setText(bad)
        card._rename()
        assert len(saves) == n and card.preset_status.text()
    n = len(saves)
    card.preset_name.setText(" 파밍 ")
    card._rename()
    assert len(saves) == n + 1 and card.active == duplicate and card.preset["name"] == "파밍"
    (want, avoid), = [(want, avoid) for row, _, want, avoid in card.boxes if row["key"] == CURSE]
    for button, expected in ((want, []), (avoid, [CURSE]), (avoid, [])):
        n = len(saves)
        button.click()
        assert len(saves) == n + 1
        assert settings["map_avoid"] == expected and map_warn.avoid_keys() == set(expected)
    card.limit_inputs["pack"].setText("35")
    assert not map_warn.avoid_keys()
    n = len(saves)
    card._delete()
    assert len(saves) == n + 1 and card.preset["name"] == "새 프리셋"
    card._delete()
    assert card.active == base and settings["map_avoid"] == [REGEN] and not card.delete_button.isEnabled()
    n = len(saves)
    card._delete()
    assert len(saves) == n and settings["unrelated"] == {"ok": True}


def test_recovery_keeps_valid_rows_and_legacy_avoid_wins():
    base, spare = map_presets.blank("  FARM "), map_presets.blank("farm")
    base["order"] = [[REGEN, "want"], [CURSE, "avoid"]]
    base["limits"]["map"] = "40"
    settings = {"map_presets": [False, base, spare], "map_preset_active": base["id"], "map_avoid": [REGEN]}
    rows, active = map_presets.recover(settings, {REGEN, CURSE})
    assert active == base["id"] and [row["name"] for row in rows] == ["FARM", "farm 2"]
    assert rows[0]["order"] == [[REGEN, "avoid"]] and rows[0]["limits"]["map"] == "40"
    assert rows[1]["order"] == []
    rows, active = map_presets.recover({"map_presets": "bad", "map_avoid": [CURSE, "unknown"]}, {CURSE})
    assert rows[0]["id"] == active and rows[0]["order"] == [[CURSE, "avoid"]]


@pytest.mark.parametrize("invalid", ["1", "9", "1000", "1.5", "abc"])
def test_invalid_numbers_block_button_and_keyboard_without_touching_clipboard(panel, invalid):
    card, _, _ = panel
    card.limit_inputs["pack"].setText(invalid)
    assert not card.regex_text.text() and not card.regex_copy.isEnabled() and "정수" in card.regex_status.text()
    clipboard = QApplication.clipboard()
    clipboard.setText("변경 금지")
    card.regex_copy.click()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == "변경 금지"


def test_english_threshold_is_blocked_and_language_survives_preset_switch(panel):
    card, settings, _ = panel
    base = card.active
    card.limit_inputs["pack"].setText("35")
    card.regex_language.setCurrentIndex(1)
    assert settings["map_regex_language"] == "en"
    assert not card.regex_text.text() and "영문 수치" in card.regex_status.text()
    card._new()
    card.preset_picker.setCurrentIndex(card.preset_picker.findData(base))
    assert card.regex_language.currentData() == "en" and not card.regex_text.text()
    card.limit_inputs["pack"].clear()
    card.regex_copy.click()
    clipboard = QApplication.clipboard()
    assert clipboard.text() == '"!Mana or"' and clipboard.mimeData().hasFormat(map_regex.CLIPBOARD_MIME)


@pytest.mark.parametrize("case", ["empty", "long", "english"])
def test_blocked_output_leaves_clipboard_intact(panel, case):
    card, _, _ = panel
    if case == "empty":
        card._clear()
    elif case == "long":
        card.regex_patterns[REGEN] = [("가" * 248, "a")]
        card._update_regex()
    else:
        card.limit_inputs["currency"].setText("35")
        card.regex_language.setCurrentIndex(1)
    clipboard = QApplication.clipboard()
    clipboard.setText("원래 내용")
    assert not card.regex_text.text() and not card.regex_copy.isEnabled() and card.regex_status.text()
    card.regex_copy.click()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == "원래 내용"


@pytest.mark.parametrize("mode", ["want", "avoid"])
def test_unresolved_fragment_blocks_copy_but_preserves_selection_and_warning(panel, mode):
    card, settings, _ = panel
    key = "#% increased number of rare monsters"
    card.regex_patterns[key] = [(None, "Rare Monsters")]
    card._pick(key, mode)
    clipboard = QApplication.clipboard()
    clipboard.setText("원래 내용")
    assert not card.regex_text.text() and not card.regex_copy.isEnabled()
    assert "모든 등급" in card.regex_status.text() and "희귀 몬스터 수" in card.regex_status.text()
    card.regex_copy.click()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == "원래 내용"
    assert [key, mode] in settings["map_presets"][0]["order"]
    assert map_warn.avoid_keys() == ({REGEN, key} if mode == "avoid" else {REGEN})
    card.regex_language.setCurrentIndex(1)
    assert card.regex_copy.isEnabled() and "Rare Monsters" in card.regex_text.text()
