import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

import map_avoid_panel
import mapcheck
import map_regex


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


def test_map_panel_filters_preserve_selection_and_invalid_state_cannot_copy(app, monkeypatch):
    monkeypatch.setattr(map_avoid_panel, "load_settings", lambda: {"map_avoid": [REGEN]})
    monkeypatch.setattr(map_avoid_panel, "save_settings", lambda _: None)
    monkeypatch.setattr(map_regex, "load_patterns", lambda _: PATTERNS)
    host = QWidget()
    card = map_avoid_panel.MapAvoidCard(host, QVBoxLayout(host))
    clipboard = QApplication.clipboard()
    card.search.setText("목록에 없음")
    assert card.regex_copy.isEnabled()
    QTest.keyClick(card.regex_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.text() == '"!재생"'
    assert clipboard.mimeData().hasFormat(map_regex.CLIPBOARD_MIME)
    card.regex_language.setCurrentIndex(1)
    card.regex_copy.click()
    assert clipboard.text() == '"!gen"'
    assert list(card.avoid) == [REGEN]
    card._toggled(RESIST, True)
    card._toggled(REGEN, False)
    card._toggled(REGEN, True)
    assert card.regex_text.text() == '"!o al|gen"'

    card._toggled("missing key", True)
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
