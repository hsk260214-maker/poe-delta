import hashlib
import importlib.util
import json
from pathlib import Path

import dict_builder
import pytest


def test_pytest_cache_is_isolated(pytestconfig):
    assert not pytestconfig.pluginmanager.hasplugin("cacheprovider")


def test_apt_base_and_flatten(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(dict_builder, "CACHE", cache)
    group = {"resolve": {"strat": "select", "test": [None, "ARMOUR"]},
             "stats": [{"ref": "global", "matchers": []}, {"ref": "local", "matchers": []}]}
    body = json.dumps(group) + "\n"
    (cache / "apt_en_stats.ndjson").write_text(body)
    base = "https://example.invalid/fixed/"
    filename = "apt_" + hashlib.sha256(base.encode()).hexdigest()[:16] + "_en_stats.ndjson"
    (cache / filename).write_text(body)
    assert dict_builder.apt_ndjson("en/stats.ndjson", False) == group["stats"]
    assert dict_builder.apt_ndjson("en/stats.ndjson", False, base=base, flatten=False) == [group]
    assert {p.name for p in cache.iterdir()} == {"apt_en_stats.ndjson", filename}


def test_data_provenance_and_converter():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "data" / "trade_stats.json").read_text(encoding="utf-8"))
    assert data["source"]["commit"] == "803d188d1359c4d5b1e3826da5dc680ea74a158f"
    assert len(data["groups"]) == 86
    assert "MIT License" in (root / "data" / "LICENSE-awakened-poe-trade.txt").read_text()
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "(docs/THIRD_PARTY_NOTICES.md)" in readme
    notice = (root / "docs" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Awakened PoE Trade" in notice and "Alexander Drozdov" in notice
    assert "(../data/trade_stats.json)" in notice and "(../data/LICENSE-awakened-poe-trade.txt)" in notice
    spec = importlib.util.spec_from_file_location("build_trade_stats", root / "tools" / "build_trade_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sample = {"resolve": {"strat": "select", "test": [None, "ARMOUR"]},
              "stats": [{"ref": "# Armour", "trade": {"ids": {"explicit": ["explicit.global"]}}, "matchers": [{"string": "# Armour"}]},
                        {"ref": "# Armour", "trade": {"ids": {"explicit": ["explicit.local"]}, "inverted": True},
                         "matchers": [{"string": "# Armour", "negate": True, "value": 1, "advanced": True}]}]}
    result = module.convert([sample])
    assert result["entries"][1]["test"] == "ARMOUR"
    assert result["entries"][1]["inverted"]
    assert result["matchers"][1] == {"string": "# Armour", "negate": True, "has_value": True, "value": 1,
                                     "advanced": True, "entry": 1}
    wrong_influence = {"ref": "Has Shaper Influence",
                       "trade": {"ids": {"pseudo": ["pseudo.pseudo_has_elder_influence"]}}, "matchers": []}
    with pytest.raises(ValueError, match="APT 영향력 ID 불일치"):
        module.convert([wrong_influence])


def test_build_license_metadata_stays_in_cache(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("build_trade_stats", root / "tools" / "build_trade_stats.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache, output = tmp_path / "cache", tmp_path / "output"
    monkeypatch.setattr(dict_builder, "apt_ndjson", lambda *args, **kwargs: [
        {"ref": f"Has {name} Influence", "trade": {"ids": {"pseudo": [stat_id]}}, "matchers": []}
        for name, stat_id in module.INFLUENCE_IDS.items()
    ] + [{"ref": "# Enchant Modifiers",
          "trade": {"ids": {"pseudo": ["pseudo.pseudo_number_of_enchant_mods"]}}, "matchers": []},
         {"ref": "+#% total Elemental Resistance",
          "trade": {"ids": {"pseudo": ["pseudo.pseudo_total_elemental_resistance"]}}, "matchers": []}])

    def fake_download(url, path, refresh):
        assert path.is_relative_to(cache)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("MIT License\n", encoding="utf-8")
        path.with_name(path.name + ".etag").write_text("fake-etag", encoding="utf-8")

    monkeypatch.setattr(dict_builder, "download", fake_download)
    monkeypatch.setattr(module.sys, "argv", ["build_trade_stats.py", "--cache", str(cache), "--out", str(output)])
    module.main()
    assert {path.name for path in output.iterdir()} == {"trade_stats.json", "LICENSE-awakened-poe-trade.txt"}
    assert (output / "LICENSE-awakened-poe-trade.txt").read_text() == "MIT License\n"
    assert len(list(cache.glob("*.etag"))) == 1
