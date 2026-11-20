"""RePoE 원본 두 파일에서 §5.2 상한 입력 및 오탐 검사 코퍼스를 추출한다."""
import argparse
import hashlib
import json
from pathlib import Path

from build_map_mods import TAGS, clean

STATS = {
    "drops": "map_drop_scaling_+%",
    "rarity": "map_item_drop_rarity_+%",
    "pack": "map_pack_size_+%",
    "currency": "map_currency_drop_chance_+%_final_from_uber_mod",
    "map": "map_map_item_drop_chance_+%_final_from_uber_mod",
}


def extract(en, ko):
    eligible = {key: mod for key, mod in en.items()
                if mod["domain"] == "area" and mod["generation_type"] in ("prefix", "suffix")
                and any(w["tag"].strip() in TAGS and w["weight"] > 0 for w in mod["spawn_weights"])}
    maxima = {
        key: {kind: sorted((stat["max"] for mod in eligible.values() if mod["generation_type"] == kind
                            for stat in mod["stats"] if stat["id"] == stat_id), reverse=True)[:4]
              for kind in ("prefix", "suffix")}
        for key, stat_id in STATS.items()
    }
    lines = sorted({line for key in eligible for line in ko[key].get("text", "").splitlines()})
    # §5.2 상한의 접사 모집단과 달리, 선호는 명시적으로 지도에 붙는 비접사도 검사한다.
    map_tags = (TAGS - {"default"}) | {"maven_void_map", "maven_void_map_feared", "maven_void_map_hidden"}
    tagged = {key for key, mod in en.items() if mod["domain"] == "area"
              and any(w["tag"].strip() in map_tags and w["weight"] > 0 for w in mod["spawn_weights"])}
    mods = {key: {lang: [clean(line) for line in source[key].get("text", "").splitlines()]
                  for lang, source in (("ko", ko), ("en", en))}
            for key in sorted(eligible.keys() | tagged)}
    return {"eligible": len(eligible), "maxima": maxima, "lines": lines, "mods": mods}


def bounds(data):
    bonus = {"drops": 30, "pack": 10, "rarity": 20, "currency": 0, "map": 0}
    ceilings = {key: (sum(sum(values) for values in groups.values()) * 3 + 1) // 2 + bonus[key]
                for key, groups in data["maxima"].items()}
    ceilings["rarity"] += ceilings["drops"]
    if any(value >= 1000 for value in ceilings.values()):
        raise ValueError(f"수치 패턴 지원 범위 초과: {ceilings}")
    return ceilings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("en", type=Path)
    parser.add_argument("ko", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sources = [path.read_bytes() for path in (args.en, args.ko)]
    data = extract(*(json.loads(source) for source in sources))
    print(bounds(data))
    data["sha256"] = [hashlib.sha256(source).hexdigest() for source in sources]
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
