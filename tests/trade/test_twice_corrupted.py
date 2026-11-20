import json

import pytest

from itemmodel import compose_en, parse, skeleton
from trade import config
from trade.trade_window import TradeWindow


@pytest.mark.parametrize("filename,server,flag,original", [
    ("twice_corrupted_jewel_ko.txt", config.KAKAO, "두 번 타락", "타락"),
    ("twice_corrupted_jewel_en_derived.txt", config.OFFICIAL, "Twice Corrupted", "Corrupted"),
])
def test_twice_corrupted_matches_standard_corruption(app, fixtures, filename, server, flag, original):
    text = (fixtures / filename).read_text(encoding="utf-8")
    model = parse(text)
    assert model.flags == [flag]
    standard = parse(text.replace(f"\n{flag}\n", f"\n{original}\n"))
    assert model.mods == standard.mods
    assert all("2 divine" not in mod.text for mod in model.mods)
    assert any(mod.kind == "implicit" for mod in model.mods)
    if flag == "두 번 타락":
        assert all(mod.sub == "corrupted" for mod in model.mods if mod.kind == "implicit")
    for source in (text, text.replace(f"\n{flag}\n", f"\n{original}\n{flag}\n")):
        output, _ = compose_en(parse(source))
        assert output.splitlines().count("Corrupted") == 1
        assert "Twice Corrupted" not in output.splitlines()

    config.save(mode="browser", league="Standard", server=server)
    window = TradeWindow()
    try:
        window.load(model)
        assert window.info.corrupted and window.corrupted.isChecked()
        assert window.corrupted.text() == "타락"
        packet = window._query()
        assert packet["query"]["filters"]["misc_filters"]["filters"]["corrupted"] == {"option": "true"}
        assert "twice_corrupted" not in json.dumps(packet)
        window.load(standard)
        assert json.dumps(window._query()) == json.dumps(packet)
    finally:
        window.close()


@pytest.mark.parametrize("header,plain,twice,ordinary,translated", [
    ("Implicit Modifier", "Corrupted", "Twice Corrupted", "Mirrored", False),
    ("고정 속성 부여", "타락", "두 번 타락", "복제", True),
])
def test_only_unheaded_rows_infer_corruption_from_new_marker(monkeypatch, header, plain, twice, ordinary, translated):
    from types import SimpleNamespace

    import ko2en

    head = ("아이템 종류: 주얼\n아이템 희귀도: 희귀\n코발트색 주얼\n--------\n아이템 레벨: 83\n--------\n"
            if translated else "Item Class: Jewels\nRarity: Rare\nCobalt Jewel\n--------\nItem Level: 83\n--------\n")
    en = "10% increased Damage"
    line = "피해 10% 증가" if translated else en
    kind = {skeleton(en): {"corrupted"}}
    monkeypatch.setattr(ko2en, "_dict", lambda: SimpleNamespace(implicit_kinds=kind, base_implicits={}))
    monkeypatch.setattr(ko2en, "translate_base", lambda _: "Cobalt Jewel")
    monkeypatch.setattr(ko2en, "translate_mod", lambda _: en)
    normal = head + line + " (implicit)\n--------\n"
    advanced = head + f"{{ {header} }}\n{line}\n--------\n"
    assert parse(normal + twice).mods[0].sub == "corrupted"
    assert parse(advanced + twice).mods[0].sub == parse(advanced + ordinary).mods[0].sub == ""
    assert parse(advanced + plain).mods[0].sub == "corrupted"
