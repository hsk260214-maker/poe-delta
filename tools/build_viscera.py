"""PoEDB 한국어 살덩이 목록에서 단계별 거래소 정체성 표(data/viscera.json)를 만든다.

  python tools/build_viscera.py <poedb Viscera kr HTML> [--output data/viscera.json]

단계마다 PoEDB 공식 거래소 링크의 type·stat ID·범위를 그대로 쓴다. 링크가 없거나, 같은 살덩이에서
같은 ID의 범위가 겹치거나, 앱의 문구 연결이 다른 ID를 고르는 행은 검색할 수 없는 행으로 남긴다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote_plus

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import ko2en  # noqa: E402
from itemmodel import skeleton  # noqa: E402
from trade.stats import index  # noqa: E402

SOURCE = "https://poedb.tw/kr/Viscera"
RANGE = re.compile(r"\((-?[\d.]+)\s*—\s*(-?[\d.]+)\)")
NUMBER_OR_RANGE = re.compile(r"\((-?[\d.]+)\s*—\s*(-?[\d.]+)\)|[+-]?\d+(?:\.\d+)?")
TIERS = ("Low", "Med", "High", "Queen")


def text_of(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", fragment))).strip()


def value_index(line: str) -> int | None:
    """복사본 줄의 숫자 중 단계 범위가 적용되는 숫자의 위치."""
    tokens = list(NUMBER_OR_RANGE.finditer(line))
    ranged = [i for i, token in enumerate(tokens) if token[1] is not None]
    return ranged[0] if len(ranged) == 1 else None


def parse(page: str) -> list[dict]:
    start = page.find('id="살덩이"')
    body = page[start:page.find("</tbody>", start)]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 3:
            continue
        name, slot = text_of(cells[0]), text_of(cells[1])
        for li in re.findall(r"<li>(.*?)</li>", cells[2], re.S):
            plain = text_of(li)
            label = re.match(r"(\w+)\b", plain)
            tier = label[1] if label else ""
            lines = [re.sub(r"\s+", " ", line).replace(" %", "%").strip()
                     for line in plain[label.end() if label else 0:].split("\n") if line.strip()]
            link = re.search(r'href="(https://www\.pathofexile\.com/trade/search/[^"]+)"', li)
            query = json.loads(unquote_plus(html.unescape(link[1]).split("q=", 1)[1]))["query"] if link else None
            stat = query["stats"][0]["filters"][0] if query else {}
            rows.append({"name": name, "slot": slot, "tier": tier, "lines": lines,
                         "type_en": query["type"] if query else "", "stat": stat.get("id", ""),
                         "low": stat.get("value", {}).get("min"), "high": stat.get("value", {}).get("max")})
    return rows


def blocked(row: dict, rows: list[dict]) -> str:
    if row["tier"] not in TIERS:
        return "단계 없는 고유 살덩이"
    if not row["stat"] or row["low"] is None or row["high"] is None or len(row["lines"]) != 1:
        return "거래소 조건 없음"
    if value_index(row["lines"][0]) is None:
        return "단계 범위 숫자 없음"
    same = [o for o in rows if o is not row and o["name"] == row["name"] and o["stat"] == row["stat"]]
    if any(not (row["high"] < o["low"] or row["low"] > o["high"]) for o in same if o["low"] is not None):
        return "단계 범위 겹침"
    english = ko2en.translate_mod(RANGE.sub(lambda m: m[2], row["lines"][0]))
    matched = index().match(english, "implicit", "Viscera").id if english else ""
    if matched and matched != row["stat"]:
        return "앱 문구 연결과 거래소 ID 불일치"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "viscera.json")
    args = parser.parse_args()
    rows = parse(args.page.read_text(encoding="utf-8"))
    out = []
    for row in rows:
        reason = blocked(row, rows)
        out.append({"name": row["name"], "slot": row["slot"], "tier": row["tier"], "type_en": row["type_en"],
                    "stat": row["stat"], "low": row["low"], "high": row["high"],
                    "skeleton": skeleton(RANGE.sub(lambda m: m[2], row["lines"][0])) if row["lines"] else "",
                    "value_index": value_index(row["lines"][0]) if row["lines"] else None,
                    "blocked": reason})
    args.output.write_text(json.dumps({"source": SOURCE, "rows": out}, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
    print(f"rows={len(out)} searchable={sum(not r['blocked'] for r in out)}")


if __name__ == "__main__":
    main()
