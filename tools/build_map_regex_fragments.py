"""FIX-012: 고정 RePoE 데이터로 지도 조각 및 독립 회귀용 롤 코퍼스를 생성한다."""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from build_map_mods import ROOT, TAGS
from map_regex_rolls import Renderer, source_lines
import mapcheck

SOURCE_VERSION = "3.30.0.3"
SHA256 = {
    "mods.min.json": "6733f6bec5795c3c9129c68564058baf9f33f11aaa633d01a811e58e09f54803",
    "Korean/mods.min.json": "824d63bc46290e7f03901824bb55b926285618095e9d75ade1b471e40b3e1c1e",
    "base_items.min.json": "8b947604966476f153078a984803be9b7ee7f83b3d3644e57a7263278f1928de",
    "Korean/base_items.min.json": "fdd596205cd790ea8fb7cb97c79235e517675bd310ed93c952dd8121091b7484",
    "uniques.min.json": "29bb16512ae347fbf1e2c13438061ad00eca3b3fd050cfb8040514e7004203d8",
    "Korean/uniques.min.json": "41312148fb605cdd598b7aa98a1d229936b78139ee520bdbfa59d20b1e70140f",
    "stat_translations.min.json": "74ecc9bb45e47635c9fc25ac34a90d379713b9e185adc6e12f2ea903c9e9193d",
    "Korean/stat_translations.min.json": "bc0ec19086bc6f18a5e1c949f26bc12187f363f1b58306c6a36d5fc804ff8ab5",
    "stat_value_handlers.min.json": "ddd42bbdf39b2b5daf894f8a192f8ddd1a0f2e776161123f504c2dd61562d8aa",
}
LANGUAGES = {"ko": ("Korean/", "Korean"), "en": ("", "English")}
MAP_TAGS = TAGS | {"maven_void_map", "maven_void_map_feared", "maven_void_map_hidden"}
FIXTURES = ROOT / "tests/trade/fixtures"
LEGACY = FIXTURES / "map_regex_v1_2_8.json"
LEGACY_SHA256 = "2ddd809488742955221440adfe2709dacf909bfbba2a3d1d564b63f613d3e3ae"
LIFE = "#% more monster life"
LIFE_PATTERN = "터의 생명력 (1..|[1-9].)%"
LIFE_HITS = [f"몬스터의 생명력 {value}% 증폭" for value in (15, 24, 25, 30, 40, 49, 90, 99, 100)]
LIFE_MISSES = ["룬 몬스터의 생명력 200% 증폭", "몬스터의 생명력이 흡수되지 않음", "고유 보스의 생명력 35% 증가"]
COUNT = re.compile(r"[0-9]+(?:개|회|마리|명|중첩|단계)?")
DIGIT = re.compile(r"[0-9]")
FIXTURE_SUFFIX = re.compile(r"\s*(?:— (?:변경이 불가능한 값|Unscalable Value)|\((?:implicit|augmented|enchant)\))\s*$", re.I)


def verified_json(path, expected):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError(f"{path}: SHA-256 {digest}, 기대값 {expected}")
    return json.loads(data)


def selectable(mod):
    return (mod["generation_type"] in ("prefix", "suffix")
            and any(w["weight"] > 0 and w["tag"].strip() in MAP_TAGS for w in mod["spawn_weights"]))


def key_for(line):
    entry = mapcheck.entry_for(FIXTURE_SUFFIX.sub("", line))
    return entry["key"] if entry else None


def corpus(sources, keys):
    en = sources["mods.min.json"]
    ids = sorted(mod_id for mod_id, mod in en.items() if mod["domain"] == "area"
                 and (mod_id.startswith("Map") or selectable(mod)))
    out = {}
    for language, (prefix, locale) in LANGUAGES.items():
        localized = sources[prefix + "mods.min.json"]
        renderer = Renderer(sources[prefix + "stat_translations.min.json"], locale,
                            sources["stat_value_handlers.min.json"])
        mods = {}
        for mod_id in ids:
            mod = localized[mod_id]
            source = source_lines(mod)
            # 기존 골격은 언어마다 동일하지 않을 수 있으므로 모드 소속은 두 원문으로 판정한다.
            own = sorted({key_for(line) for line in (*source, *source_lines(en[mod_id]),
                                                     *source_lines(sources["Korean/mods.min.json"][mod_id]))}
                         & keys)
            mods[mod_id] = [selectable(en[mod_id]), own, renderer.render(mod, mapcheck.skel)]
        names = {entry["name"] for entry in sources[prefix + "base_items.min.json"].values()
                 if entry["item_class"] in ("Map", "MapFragment")}
        names.update(entry["name"] for entry in sources[prefix + "uniques.min.json"].values())
        fixed = [[None, name] for name in sorted(names) if name]
        if language == "ko":
            lines = {line.strip() for file in FIXTURES.glob("*map*_ko.txt")
                     for line in file.read_text(encoding="utf-8-sig").splitlines() if line.strip()}
            fixed.extend([key_for(line), line] for line in sorted(lines))
        out[language] = {"mods": mods, "fixed": fixed}
    return out


def candidates(line, counts):
    words = line.split()
    numeric = [bool(DIGIT.search(word)) and word not in counts for word in words]
    for start in range(len(words)):
        if numeric[start]:
            continue
        parts = []
        count = 0
        for i in range(start, len(words)):
            if numeric[i]:
                continue
            if parts:
                parts.append(".*" if numeric[i - 1] else " ")
            parts.append(re.escape(words[i]))
            count += 1
            if count >= 2:
                term = "".join(parts)
                if '"' not in term:
                    yield term


def _own_lines(key, positives):
    return [tuple(line for line in variant if key_for(line) == key)
            for variants in positives.values() for variant in variants]


def _fixed_counts(lines):
    # 숫자 토큰(%)은 제외하고, 모든 모드와 검사 롤에서 살아남는 개수만 허용한다.
    choices = [{word for line in variant for word in line.split() if COUNT.fullmatch(word)} for variant in lines]
    return set.intersection(*choices) if choices else set()


def pools(data, key):
    positives, negatives = {}, set()
    for mod_id, (selectable_mod, own, variants) in data["mods"].items():
        if key in own:
            if selectable_mod:
                positives[mod_id] = variants
        elif mod_id.startswith("Map"):
            negatives.update(line for variant in variants for line in variant)
    negatives.update(line for skeleton, line in data["fixed"] if skeleton != key)
    return positives, negatives


def validates(pattern, positives, negatives, *, life=False):
    search = re.compile(pattern, re.I).search
    return (bool(positives)
            and all(variants and all(any(search(line) for line in variant) for variant in variants)
                    for variants in positives.values())
            and not any(search(line) for line in negatives)
            and (not life or (all(search(line) for line in LIFE_HITS) and not any(search(line) for line in LIFE_MISSES))))


def choose(data, key, language):
    positive, negative = pools(data, key)
    life = (language, key) == ("ko", LIFE)
    if life:
        return LIFE_PATTERN if validates(LIFE_PATTERN, positive, negative, life=True) else None
    lines = _own_lines(key, positive)
    counts = _fixed_counts(lines)
    options = {term for variant in lines for line in variant for term in candidates(line, counts)}
    return next((term for term in sorted(options, key=lambda s: (len(s), s))
                 if validates(term, positive, negative)), None)


def generate(corpora, legacy):
    fragments = {key: [choose(corpora[lang], key, lang) for lang in LANGUAGES] for key in sorted(legacy)}
    changed = {lang: [key for key, terms in fragments.items()
                      if list(dict.fromkeys(pair[i] for pair in legacy[key])) != ([terms[i]] if terms[i] else [])]
               for i, lang in enumerate(LANGUAGES)}
    return {"repoe_version": SOURCE_VERSION, "sha256": SHA256, "fragments": fragments, "changed_keys": changed}


def write_json(path, obj):
    path.write_bytes((json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/map_regex_fragments.json")
    parser.add_argument("--corpus", type=Path, default=FIXTURES / "map_regex_fix012_corpus.json")
    args = parser.parse_args()
    sources = {name: verified_json(args.source_dir / name, sha) for name, sha in SHA256.items()}
    legacy = verified_json(LEGACY, LEGACY_SHA256)
    corpora = corpus(sources, set(legacy))
    result = generate(corpora, legacy)
    write_json(args.output, result)
    write_json(args.corpus, corpora)
    for i, lang in enumerate(LANGUAGES):
        unresolved = [key for key, terms in result["fragments"].items() if terms[i] is None]
        print(f"{lang}: {len(legacy) - len(unresolved)}/{len(legacy)}, 미해결: {unresolved}")


if __name__ == "__main__":
    main()
