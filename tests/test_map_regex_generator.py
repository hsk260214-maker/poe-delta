import json
import re
from pathlib import Path

import pytest

import map_regex
import mapcheck


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/trade/fixtures"


@pytest.fixture
def generator(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    import build_map_regex_fragments
    return build_map_regex_fragments


def test_fixed_sources_fail_closed_on_hash_mismatch(generator, tmp_path):
    path = tmp_path / "mods.min.json"
    path.write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError, match="SHA-256"):
        generator.verified_json(path, generator.SHA256[path.name])


def test_renderer_covers_digit_edges_and_wording_intervals_without_hidden_stats(generator):
    from map_regex_rolls import Renderer, roll_points

    assert roll_points(-12, 102, [{"min": 40, "max": 51}]) == [
        -12, -10, -9, -1, 0, 1, 9, 10, 39, 40, 51, 52, 99, 100, 102,
    ]

    def wording(text, condition, handlers=()):
        return {"condition": [condition], "format": ["#"], "index_handlers": [handlers], "string": text}

    translations = [
        {"ids": ["count"], "English": [wording("{0} charge", {"max": 1}), wording("{0} charges", {"min": 2})]},
        {"ids": ["penalty"], "English": [wording("-{0}% resistance", {}, ["negate"])]},
        {"ids": ["hidden"], "English": [wording("Invisible stat {0}", {})]},
    ]
    mod = {"text": "(1-12) charge\n-8% resistance", "stats": [
        {"id": "count", "min": 1, "max": 12}, {"id": "penalty", "min": -8, "max": -8},
        {"id": "hidden", "min": 5, "max": 5},
    ]}
    renderer = Renderer(translations, "English", {"negate": {"type": "int", "multiplier": -1}})
    assert set(renderer.render(mod, mapcheck.skel)) == {
        (count, "-8% resistance") for count in ("1 charge", "2 charges", "9 charges", "10 charges", "12 charges")
    }


def test_shortest_candidate_rules_exclude_rolled_numbers(generator):
    assert set(generator.candidates("몬스터 피해 14% 증가", set())) == {"몬스터 피해", "몬스터 피해.*증가", "피해.*증가"}
    assert "속성 1개" not in set(generator.candidates("속성 1개 추가", set()))
    assert "속성 1개" in set(generator.candidates("속성 1개 추가", {"1개"}))
    assert "many" not in set(generator.candidates("many Totems", set()))


def test_generated_replacement_and_all_mod_rolls_in_both_copy_modes(generator):
    corpora = json.loads((FIXTURES / "map_regex_fix012_corpus.json").read_bytes())
    legacy = generator.verified_json(generator.LEGACY, generator.LEGACY_SHA256)
    artifact = json.loads((ROOT / "data/map_regex_fragments.json").read_bytes())
    assert generator.generate(corpora, legacy) == artifact
    catalog = mapcheck.catalog()
    patterns = map_regex.load_patterns(catalog)
    assert set(patterns) == set(legacy)
    for i, (lang, data) in enumerate(corpora.items()):
        assert len(data["mods"]) == 1726
        assert sum(row[0] for row in data["mods"].values()) == 336
        assert artifact["changed_keys"][lang] == sorted(legacy)
        for key, pair in artifact["fragments"].items():
            term = pair[i]
            assert term, (lang, key)
            search = re.compile(term, re.I).search
            positives = []
            for mod_id, (selectable, keys, rolls) in data["mods"].items():
                if selectable and key in keys:
                    positives.append(mod_id)
                    assert all(any(search(line) for line in roll) for roll in rolls), (lang, key, mod_id)
                elif mod_id.startswith("Map") and key not in keys:
                    assert not any(search(line) for roll in rolls for line in roll), (lang, key, mod_id)
            assert positives, (lang, key)
            assert not any(search(line) for skeleton, line in data["fixed"] if skeleton != key), (lang, key)
            assert map_regex.build([], catalog, patterns, lang, wanted=[key]).text == f'"{term}"'
            assert map_regex.build([key], catalog, patterns, lang).text == f'"!{term}"'


def test_korean_monster_life_exception_matches_only_approved_cases():
    catalog = mapcheck.catalog()
    pattern = re.compile(map_regex.load_patterns(catalog)["#% more monster life"][0][0])
    for value in (15, 24, 25, 30, 40, 49, 90, 99, 100):
        assert pattern.search(f"몬스터의 생명력 {value}% 증폭")
    for line in ("룬 몬스터의 생명력 200% 증폭", "몬스터의 생명력이 흡수되지 않음", "고유 보스의 생명력 35% 증가"):
        assert not pattern.search(line)
