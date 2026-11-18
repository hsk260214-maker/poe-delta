"""고정 APT 품목·지도 식별 자료를 거래소용으로 추출한다."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from build_trade_stats import BASE, COMMIT, dict_builder

MAP_ID = re.compile(r"implicit\.stat_(?:3624393862\|[1-4]|2563183002\|[1-4]|1792283443\|[12])")


def extract(lang):
    rows = dict_builder.apt_ndjson(f"{lang}/items.ndjson", False, base=BASE, flatten=False)
    bases = {}
    records = []
    for row in rows:
        if row["namespace"] == "ITEM" and "craftable" in row:
            bases.setdefault(row["refName"], set()).add(row["craftable"]["category"])
    for row in rows:
        ref, name, ns = row["refName"], row["name"], row["namespace"]
        disc = row.get("tradeDisc")
        if ns == "ITEM" and "craftable" in row:
            records.append((ns, ref, name, row["craftable"]["category"], disc, None))
        elif ns == "GEM":
            gem = row["gem"]
            records.append((ns, ref, name, "Gem", disc, bool(gem.get("vaal") or gem.get("transfigured"))))
        elif ns == "UNIQUE":
            base = row["unique"]["base"]
            for category in sorted(bases.get(base, set()) & {"Map", "Flask"}):
                records.append((ns, ref, name, category, disc, base))
    stats = dict_builder.apt_ndjson(f"{lang}/stats.ndjson", False, base=BASE)
    identity = {}
    for stat in stats:
        for stat_id in stat["trade"]["ids"].get("implicit", []):
            if MAP_ID.fullmatch(stat_id):
                if stat_id in identity:
                    raise ValueError(f"중복 지도 식별 ID: {stat_id}")
                identity[stat_id] = [entry["string"] for entry in stat["matchers"]]
    if len(identity) != 10:
        raise ValueError("지도 식별 ID 10개가 필요합니다")
    return records, identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dict_builder.CACHE = args.cache
    en, en_map = extract("en")
    ko, ko_map = extract("ko")
    keys = lambda records: Counter((ns, ref, cls, disc, extra) for ns, ref, _, cls, disc, extra in records)
    if keys(en) != keys(ko) or en_map.keys() != ko_map.keys():
        raise ValueError("한·영 원본 품목 레코드가 일치하지 않습니다")
    payload = {"source": {"project": "SnosMe/awakened-poe-trade", "commit": COMMIT},
               "items": {"en": en, "ko": ko}, "map_identity": {"en": en_map, "ko": ko_map}}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
