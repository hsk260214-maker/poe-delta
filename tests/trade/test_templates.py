from copy import deepcopy

import pytest

from itemmodel import parse
from trade import config, heist, templates
from trade.query import item_info
from trade.trade_window import TradeWindow


def clip(kind, rarity, base, props="Item Level: 83"):
    return f"Item Class: {kind}\nRarity: {rarity}\n{base}\n--------\n{props}"


@pytest.mark.parametrize("kind,rarity,base,props,expected", [
    ("Jewels", "Rare", "Crimson Jewel", "Item Level: 83", templates.EQUIPMENT),
    ("Abyss Jewels", "Rare", "Searching Eye Jewel", "Item Level: 83", templates.EQUIPMENT),
    ("Jewels", "Rare", "Large Cluster Jewel", "Item Level: 83", templates.EQUIPMENT),
    ("Body Armours", "Unique", "Tabula Rasa\nSimple Robe", "Item Level: 83", templates.EQUIPMENT),
    ("Skill Gems", "Gem", "Fireball", "Level: 1", templates.GEM),
    ("Utility Flasks", "Magic", "Quicksilver Flask", "Item Level: 83", templates.FLASK),
    ("Maps", "Rare", "Map (Tier 16)", "Item Level: 83", templates.AREA_LEVEL),
    ("Maps", "Unique", "The Coward's Trial\nMap (Tier 8)", "Item Level: 83", templates.AREA_LEVEL),
    ("Expedition Logbooks", "Rare", "Logbook", "Area Level: 83", ""),
])
def test_template_comes_from_existing_item_branch(kind, rarity, base, props, expected):
    info = item_info(parse(clip(kind, rarity, base, props)))
    assert info.template == expected
    if not expected:
        assert not info.supported and "지원하지 않습니다" in info.message


@pytest.mark.parametrize("fixture,expected", [
    ("heist_contract_ko.txt", templates.AREA_LEVEL), ("heist_blueprint_ko.txt", templates.AREA_LEVEL),
    ("fix004_nightmare_map_ko.txt", templates.AREA_LEVEL), ("vaal_temple_map_ko.txt", templates.AREA_LEVEL),
    ("shaper_guardian_map_ko.txt", templates.AREA_LEVEL), ("forbidden_tome_ko.txt", templates.OTHER),
    ("viscera_lesser_blazing_skull_ko.txt", templates.OTHER),
])
def test_template_on_stored_copy(fixtures, fixture, expected):
    assert item_info(parse((fixtures / fixture).read_text(encoding="utf-8")), config.KAKAO).template == expected


@pytest.fixture
def window(app):
    config.save(mode="browser", league="Standard", server=config.OFFICIAL)
    window = TradeWindow()
    yield window
    window.close()


def picked(window):
    top = {name for name in ("monster_level", "corrupted", "links", "ilvl")
           if getattr(window, name).isChecked() and not getattr(window, name).isHidden()}
    return top | {row.kind for row, (check, _, _) in zip(window.stats, window.inputs) if check.isChecked()} | {
        name for name, check in window.influence_inputs.items() if check.isChecked()
    }


@pytest.mark.parametrize("level,corrupted", [(83, False), (83, True), (None, False)])
def test_map_default_is_monster_level_only(window, level, corrupted):
    level_line = f"\nMonster Level: {level}" if level is not None else ""
    text = clip("Maps", "Rare", "Map (Tier 16)", f"Item Level: 83{level_line}") + "\n--------\nMonsters have 30% increased Attack Speed"
    text += "\n--------\nCorrupted" if corrupted else ""
    window.load(text)
    assert picked(window) == ({"monster_level"} if level is not None else set())
    query = window._query()["query"]
    assert query["type"] == {"option": "Map", "discriminator": "map"}
    assert "misc_filters" not in query["filters"]
    assert query["filters"]["map_filters"]["filters"] == {
        "map_tier": {"min": 16, "max": 16}, "map_blighted": {"option": "false"},
        **({"area_level": {"min": 83, "max": 83}} if level else {}),
    }
    window.corrupted.click()
    assert window._query()["query"]["filters"]["misc_filters"]["filters"]["corrupted"] == {
        "option": "true" if corrupted else "false",
    }


@pytest.mark.parametrize("fixture,category", [
    ("heist_contract_ko.txt", heist.CONTRACT), ("heist_blueprint_no_enchant_ko.txt", heist.BLUEPRINT),
])
@pytest.mark.parametrize("state", ["open", "missing", "closed"])
def test_heist_only_checks_an_available_area_row(window, fixtures, monkeypatch, fixture, category, state):
    config.save(server=config.KAKAO)
    text = (fixtures / fixture).read_text(encoding="utf-8")
    if state == "missing":
        text = "\n".join(line for line in text.splitlines() if not line.startswith("지역 레벨:"))
    monkeypatch.setattr(heist, "AREA_API_VERIFIED", {category})
    monkeypatch.setattr(heist, "AREA_BROWSER_VERIFIED", {category} if state != "closed" else set())
    window.load(text)
    assert window.info.supported
    assert picked(window) == ({"heist_area"} if state == "open" else set())
    query = window._query()["query"]
    assert "heist_filters" not in query["filters"] and "misc_filters" not in query["filters"]
    assert query["stats"] == [{"type": "and", "filters": []}]
    assert query["filters"].get("map_filters") == (
        {"filters": {"area_level": {"min": 83}}} if state == "open" else None)


@pytest.mark.parametrize("kind,rarity,base,props", [
    ("Rings", "Rare", "Gold Ring", "Item Level: 83"),
    ("Skill Gems", "Gem", "Fireball", "Level: 1"),
    ("Utility Flasks", "Magic", "Quicksilver Flask", "Item Level: 83"),
])
def test_corrupted_condition_default_outside_area_templates(window, kind, rarity, base, props):
    text = clip(kind, rarity, base, props)
    window.load(text)
    assert window.corrupted.isChecked() and window.corrupted.text() == "타락 아님"
    window.load(text + "\n--------\nCorrupted")
    assert not window.corrupted.isChecked() and window.corrupted.text() == "타락"
    assert "corrupted" not in window._query()["query"]["filters"].get("misc_filters", {}).get("filters", {})


@pytest.mark.parametrize("fixture", ["forbidden_tome_ko.txt", "viscera_lesser_blazing_skull_ko.txt"])
def test_other_template_keeps_corruption_hidden(window, fixtures, fixture):
    config.save(server=config.KAKAO)
    window.load((fixtures / fixture).read_text(encoding="utf-8"))
    assert window.info.supported and window.corrupted.isHidden()


def test_unique_map_preserves_identity_and_scope(window):
    text = clip("Maps", "Unique", "The Coward's Trial\nMap (Tier 8)", "Item Level: 83\nMonster Level: 83")
    window.load(text)
    assert picked(window) == {"monster_level"}
    actual = deepcopy(window._query()["query"])
    assert actual["name"] == {"option": "The Coward's Trial", "discriminator": "map"}
    assert actual["type"] == {"option": "Map", "discriminator": "map"}
    assert window.base_button.isHidden()
