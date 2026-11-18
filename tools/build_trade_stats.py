"""고정 APT 데이터로 오프라인 거래소 stat 사전을 만든다."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import dict_builder

COMMIT = "803d188d1359c4d5b1e3826da5dc680ea74a158f"
BASE = f"https://raw.githubusercontent.com/SnosMe/awakened-poe-trade/{COMMIT}/renderer/public/data/"
KINDS = ("explicit", "implicit", "crafted", "fractured", "enchant")
STRATEGIES = {"select", "trivial-merge", "percent-merge", "flag-merge"}


def convert(rows: list[dict]) -> dict:
    entries, groups, matchers = [], [], []
    for row in rows:
        group = None
        if "stats" in row:
            if set(row) != {"resolve", "stats"} or row["resolve"]["strat"] not in STRATEGIES:
                raise ValueError("승인되지 않은 APT 묶음 형식")
            group = len(groups)
            groups.append(row["resolve"])
            stats = row["stats"]
        else:
            stats = [row]
        for i, stat in enumerate(stats):
            entry = len(entries)
            entries.append({
                "ids": {k: stat["trade"]["ids"][k] for k in KINDS if k in stat["trade"]["ids"]},
                "inverted": bool(stat["trade"].get("inverted")),
                "group": group,
                "test": row["resolve"].get("test", [None] * len(stats))[i] if group is not None else None,
            })
            for matcher in stat["matchers"]:
                matchers.append({
                    "skeleton": dict_builder._skel(matcher["string"]),
                    "negate": bool(matcher.get("negate")),
                    "has_value": "value" in matcher,
                    "advanced": bool(matcher.get("advanced")),
                    "entry": entry,
                })
    return {"source": {"project": "SnosMe/awakened-poe-trade", "commit": COMMIT},
            "entries": entries, "groups": groups, "matchers": matchers}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=dict_builder.CACHE)
    parser.add_argument("--out", type=Path, default=dict_builder.OUT_DIR)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    dict_builder.CACHE = args.cache
    result = convert(dict_builder.apt_ndjson("en/stats.ndjson", args.refresh, base=BASE, flatten=False))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "trade_stats.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    license_cache = args.cache / f"apt_{COMMIT}_LICENSE"
    dict_builder.download(
        f"https://raw.githubusercontent.com/SnosMe/awakened-poe-trade/{COMMIT}/LICENSE",
        license_cache, args.refresh)
    shutil.copyfile(license_cache, args.out / "LICENSE-awakened-poe-trade.txt")
    print(f"commit={COMMIT} entries={len(result['entries'])} groups={len(result['groups'])} matchers={len(result['matchers'])}")


if __name__ == "__main__":
    main()
