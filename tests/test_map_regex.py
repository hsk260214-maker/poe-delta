import re
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

import map_avoid_panel
import mapcheck
import map_regex
from map_presets import avoids


REGEN = "players cannot regenerate life, mana or energy shield"
RESIST = "players have #% to all maximum resistances"
PATTERNS = {REGEN: [("재생", "gen")], RESIST: [("대치.-20", "o al")]}


def test_build_excludes_selected_groups_in_one_quoted_term():
    result = map_regex.build([RESIST, REGEN], mapcheck.catalog(), PATTERNS)
    assert result.text == '"!대치.-20|재생"'
    assert result.length == len(result.text)
    assert map_regex.build([RESIST, REGEN], mapcheck.catalog(), PATTERNS, "en").text == '"!o al|gen"'


def test_unknown_selection_blocks_an_otherwise_valid_result():
    result = map_regex.build([REGEN, "missing key"], mapcheck.catalog(), PATTERNS)
    assert not result.text
    assert "missing key" in result.issue


def test_map_panel_copies_bundled_patterns_without_local_files(app, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("paths.LOCAL", tmp_path)
    monkeypatch.setattr(map_avoid_panel, "load_settings", lambda: {"map_avoid": [REGEN]})
    monkeypatch.setattr(map_avoid_panel, "save_settings", lambda _: None)
    host = QWidget()
    card = map_avoid_panel.MapAvoidCard(host, QVBoxLayout(host))
    clipboard = QApplication.clipboard()
    card.search.setText("목록에 없음")
    assert card.regex_copy.isEnabled()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == '"!마나 또는"'
    assert clipboard.mimeData().hasFormat(map_regex.CLIPBOARD_MIME)
    card.regex_language.setCurrentIndex(1)
    card.regex_copy.click()
    assert clipboard.text() == '"!Mana or"'
    assert avoids(card.preset) == [REGEN]
    card._pick(RESIST, "avoid")
    card._pick(REGEN, "avoid")
    card._pick(REGEN, "avoid")
    assert card.regex_text.text() == '"!to all|Mana or"'

    card._pick("missing key", "avoid")
    assert not card.regex_copy.isEnabled() and not card.regex_text.text()
    clipboard.setText("유지")
    card.regex_copy.click()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == "유지"
    card._clear()
    assert card.regex_count.text() == "0 / 250자"
    host.close()


@pytest.mark.parametrize("length", [249, 250, 251])
def test_length_includes_quote_negation_and_separator(length):
    text = '"!가|' + "나" * (length - 5) + '"'
    result = map_regex.fit(text)
    assert result.length == length
    assert result.text == (text if length <= 250 else "")


@pytest.mark.parametrize("language,expected", [
    ("ko", '"!공격 속도.*증가|몬스터의 시전|피해 배율|방어력.*감폭"'),
    ("en", '"!Monster Attack|Monster Cast|Monster Critical|less Defences"'),
])
def test_bundled_multiline_avoid_byte_golden(language, expected):
    catalog = mapcheck.catalog()
    selected = [
        "#% increased monster attack speed",
        "#% increased monster cast speed",
        "#% to monster critical strike multiplier",
        "players have #% less defences",
    ]
    assert map_regex.build(selected, catalog, map_regex.load_patterns(catalog), language).text.encode() == expected.encode()


def test_maximum_resistance_avoid_matches_all_tiers():
    catalog = mapcheck.catalog()
    text = map_regex.build([RESIST], catalog, map_regex.load_patterns(catalog)).text
    assert text == '"!모든 저항"'
    pattern = re.compile(text[2:-1], re.I)
    for roll in (5, 8, 9, 12, 20):
        assert pattern.search(f"플레이어의 모든 저항 최대치 -{roll}%")


def test_maven_only_option_without_site_match_blocks_partial_regex():
    catalog = mapcheck.catalog()
    result = map_regex.build([REGEN, "maven releases all bosses at once"], catalog, map_regex.load_patterns(catalog))
    assert result.text == ""
    assert "메이븐이 모든 보스를 한꺼번에 내보냄" in result.issue


def test_maven_checkbox_is_disabled_and_old_selection_does_not_block_copy(app, monkeypatch):
    maven = "maven releases all bosses at once"
    settings = {"map_avoid": [maven, REGEN]}
    saved = []
    monkeypatch.setattr(map_avoid_panel, "load_settings", lambda: settings.copy())
    monkeypatch.setattr(map_avoid_panel, "save_settings", saved.append)
    host = QWidget()
    card = map_avoid_panel.MapAvoidCard(host, QVBoxLayout(host))
    (want, avoid), = [(want, avoid) for row, _, want, avoid in card.boxes if row["key"] == maven]
    assert all(not button.isEnabled() and not button.isChecked() for button in (want, avoid))
    assert len(saved) == 1 and saved[0]["map_avoid"] == [REGEN]
    assert card.regex_copy.isEnabled() and card.regex_text.text() == '"!마나 또는"'
    host.close()
