import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from char_leagues import league_groups, league_of, league_sort_key
from import_dialog import ImportDialog


@pytest.fixture
def characters():
    path = Path(__file__).parent / "fixtures" / "characters.json"
    return json.loads(path.read_text(encoding="utf-8"))


def buttons(dialog):
    return dialog.league_group.buttons()


def button(dialog, league):
    return next(item for item in buttons(dialog) if item.property("league") == league)


def checked(dialog):
    return dialog.league_group.checkedButton().property("league")


def items(dialog):
    return [dialog.char_list.item(row) for row in range(dialog.char_list.count())]


def character(item):
    return item.data(Qt.ItemDataRole.UserRole)


def visible_names(dialog):
    return [character(item)["name"] for item in items(dialog) if not item.isHidden()]


def assert_visible_selection(dialog):
    current = dialog.char_list.currentItem()
    assert current is not None and not current.isHidden()


def test_league_normalization_counts_and_order(characters):
    assert league_groups(characters) == [
        ("Standard", 2), ("Hardcore", 1), ("Autumn Event", 1), ("New Challenge", 3), ("리그 정보 없음", 3)]
    for value in (None, "", "  ", 123, False, []):
        assert league_of({"league": value}) == "리그 정보 없음"
    assert league_of({}) == "리그 정보 없음"
    assert league_of({"league": " \tRuthless\n"}) == "Ruthless"
    expected = ["Standard", "Hardcore", "SSF Standard", "SSF Hardcore", "Ruthless", "Hardcore Ruthless",
                "SSF Ruthless", "SSF Hardcore Ruthless", "alpha League", "ZETA League", "리그 정보 없음"]
    assert sorted(reversed(expected), key=league_sort_key) == expected


def test_buttons_show_only_present_leagues_with_counts(app, characters):
    dialog = ImportDialog({})
    assert not buttons(dialog)
    assert dialog.league_layout.count() == 0
    assert dialog.char_list.count() == 0
    dialog._on_list(("account", characters))
    assert [item.text() for item in buttons(dialog)] == [
        "전체 10", "Standard 2", "Hardcore 1", "Autumn Event 1", "New Challenge 3", "리그 정보 없음 3"]
    assert all(item.isCheckable() and item.objectName() == "FilterChip" for item in buttons(dialog))
    assert checked(dialog) == ""
    assert_visible_selection(dialog)
    dialog._on_list(("empty-account", []))
    assert [item.text() for item in buttons(dialog)] == ["전체 0"]
    assert dialog.char_list.currentItem() is None
    assert dialog.status.text() == "캐릭터 0개. 가져올 캐릭터를 선택하세요."
    dialog.close()


def test_filter_switch_preserves_or_replaces_selection_and_remembers_only_clicks(app, characters):
    settings = {}
    dialog = ImportDialog(settings)
    dialog._on_list(("account", characters))
    assert "import_league" not in settings
    first = dialog.char_list.currentItem()
    button(dialog, "").click()
    assert settings["import_league"] == ""
    button(dialog, "Standard").click()
    assert visible_names(dialog) == ["standard_high", "standard_low"]
    assert dialog.char_list.currentItem() is first
    button(dialog, "Hardcore").click()
    hardcore = dialog.char_list.currentItem()
    assert visible_names(dialog) == ["hardcore"]
    assert dialog.status.text() == "Hardcore 캐릭터 1개 (전체 10개). 가져올 캐릭터를 선택하세요."
    button(dialog, "").click()
    assert len(visible_names(dialog)) == 10
    assert dialog.char_list.currentItem() is hardcore
    assert dialog.status.text() == "캐릭터 10개. 가져올 캐릭터를 선택하세요."
    button(dialog, "New Challenge").click()
    assert visible_names(dialog) == ["challenge_high", "challenge_low", "challenge_null_level"]
    low = next(item for item in items(dialog) if character(item)["name"] == "challenge_low")
    dialog.char_list.setCurrentItem(low)
    button(dialog, "").click()
    button(dialog, "New Challenge").click()
    assert dialog.char_list.currentItem() is low
    button(dialog, "리그 정보 없음").click()
    assert visible_names(dialog) == ["unknown_null", "unknown_missing", "unknown_blank"]
    assert settings["import_league"] == "리그 정보 없음"
    assert dialog.status.text() == "리그 정보 없음 캐릭터 3개 (전체 10개). 가져올 캐릭터를 선택하세요."
    assert_visible_selection(dialog)
    dialog.close()


@pytest.mark.parametrize("saved", [None, "Hardcore", "Missing League"])
def test_initial_preference_does_not_write_settings_even_on_fallback(app, characters, saved):
    settings = {} if saved is None else {"import_league": saved}
    dialog = ImportDialog(settings)
    dialog._on_list(("account", characters))
    assert checked(dialog) == ("Hardcore" if saved == "Hardcore" else "")
    assert settings.get("import_league") == saved
    assert ("import_league" in settings) == (saved is not None)
    assert_visible_selection(dialog)
    if saved == "Missing League":
        dialog._on_list(("another-account", [{"name": "remembered", "league": saved, "level": 1, "class": "Witch"}]))
        assert checked(dialog) == saved
        assert settings["import_league"] == saved
    button(dialog, "").click()
    assert settings["import_league"] == ""
    dialog.close()


@pytest.mark.parametrize("trigger", ["button", "double_click"])
def test_import_and_double_click_use_visible_character(app, characters, monkeypatch, trigger):
    import import_dialog

    calls = []
    monkeypatch.setattr(import_dialog, "run_async", lambda job, done, error: done(job()))

    def fetch(account, realm, char):
        calls.append((account, realm, char))
        return "fake-character-json"

    monkeypatch.setattr(import_dialog.importers, "fetch_character", fetch)
    dialog = ImportDialog({})
    dialog._on_list(("account#1234", characters))
    button(dialog, "New Challenge").click()
    current = dialog.char_list.currentItem()
    assert not current.isHidden()
    selected = character(current)
    if trigger == "button":
        dialog.ok_btn.click()
    else:
        dialog.char_list.itemDoubleClicked.emit(current)
    assert calls == [("account#1234", "pc", selected)]
    assert selected["name"] == "challenge_high"
    assert (dialog.kind, dialog.payload, dialog.name) == ("json", "fake-character-json", "challenge_high")
    assert dialog.source["character"] == selected
    dialog.close()


def test_reload_replaces_buttons_and_keeps_user_preference(app, characters):
    settings = {}
    dialog = ImportDialog(settings)
    dialog._on_list(("account", characters))
    button(dialog, "Hardcore").click()
    old_buttons = buttons(dialog)
    old_ids = {id(item) for item in old_buttons}
    previous_rows = [(item.text(), item.isHidden()) for item in items(dialog)]
    current = dialog.char_list.currentItem()
    dialog.account.setText("editing another account")
    dialog.realm.setCurrentIndex(1)
    dialog._on_err("fake list error")
    assert {id(item) for item in buttons(dialog)} == old_ids
    assert [(item.text(), item.isHidden()) for item in items(dialog)] == previous_rows
    assert dialog.char_list.currentItem() is current
    replacement = [{"name": "new-hardcore", "league": "Hardcore", "level": 20, "class": "Witch"},
                   {"name": "new-event", "league": "Changed Event", "level": 10, "class": "Ranger"}]
    dialog._on_list(("second-account", replacement))
    assert [item.text() for item in buttons(dialog)] == ["전체 2", "Hardcore 1", "Changed Event 1"]
    assert old_ids.isdisjoint({id(item) for item in buttons(dialog)})
    layout_buttons = [dialog.league_layout.itemAt(i).widget() for i in range(dialog.league_layout.count())
                      if dialog.league_layout.itemAt(i).widget() is not None]
    assert layout_buttons == buttons(dialog)
    assert checked(dialog) == "Hardcore"
    assert_visible_selection(dialog)
    dialog._on_list(("third-account", [{"name": "standard", "league": "Standard", "level": 1, "class": "Witch"}]))
    assert [item.text() for item in buttons(dialog)] == ["전체 1", "Standard 1"]
    assert checked(dialog) == ""
    assert settings["import_league"] == "Hardcore"
    assert_visible_selection(dialog)
    dialog._on_list(("account", characters))
    assert checked(dialog) == "Hardcore"
    assert settings["import_league"] == "Hardcore"
    assert_visible_selection(dialog)
    dialog.close()


def test_rows_follow_league_then_level_and_never_display_none(app, characters):
    dialog = ImportDialog({})
    dialog._on_list(("account", characters))
    assert [character(item)["name"] for item in items(dialog)] == [
        "standard_high", "standard_low", "hardcore", "event", "challenge_high", "challenge_low",
        "challenge_null_level", "unknown_null", "unknown_missing", "unknown_blank"]
    for item in items(dialog):
        assert item.text().endswith("  ·  " + league_of(character(item)))
        assert "None" not in item.text()
    zero_levels = {"challenge_null_level", "unknown_missing", "unknown_blank"}
    assert all("Lv 0  ·" in item.text() for item in items(dialog) if character(item)["name"] in zero_levels)
    dialog.close()
