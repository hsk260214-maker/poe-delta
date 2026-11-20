"""지도 프리셋 저장 형식과 이전 설정 이관."""
from copy import deepcopy
from uuid import uuid4

from map_regex import LIMIT_NAMES


MAVEN_ALL_BOSSES = "maven releases all bosses at once"


def blank(name):
    return {"id": uuid4().hex, "name": name, "order": [], "mode": "any",
            "limits": dict.fromkeys(LIMIT_NAMES, ""), "limit_mode": "or"}


def unique_name(stem, names, ending=""):
    used = {name.casefold() for name in names}
    i = 1
    while True:
        suffix = ending + (f" {i}" if i > 1 else "")
        candidate = stem[:20 - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in used:
            return candidate
        i += 1


def avoids(preset):
    return [key for key, mode in preset["order"] if mode == "avoid"]


def _valid(row):
    return (isinstance(row, dict) and isinstance(row.get("id"), str) and bool(row["id"])
            and isinstance(row.get("name"), str) and isinstance(row.get("order"), list)
            and all(isinstance(pair, list) and len(pair) == 2 and isinstance(pair[0], str)
                    and pair[1] in ("want", "avoid") for pair in row["order"])
            and row.get("mode") in ("any", "all") and row.get("limit_mode") in ("or", "and")
            and isinstance(row.get("limits"), dict)
            and all(key in LIMIT_NAMES and isinstance(value, str) for key, value in row["limits"].items()))


def _legacy_keys(value, keys):
    return list(dict.fromkeys(key for key in value if isinstance(key, str) and key in keys)) if isinstance(value, list) else []


def recover(settings, keys):
    """복구를 마친 새 데이터와 활성 ID를 반환한다."""
    raw = settings.get("map_presets")
    legacy = _legacy_keys(settings.get("map_avoid"), keys)
    rows, ids = [], set()
    for source in raw if isinstance(raw, list) else ():
        if not _valid(source) or source["id"] in ids:
            continue
        row = deepcopy(source)
        ids.add(row["id"])
        row["name"] = unique_name(row["name"].strip()[:20] or "기본", (p["name"] for p in rows))
        row["order"] = [[key, mode] for key, mode in dict(row["order"]).items() if key in keys]
        row["limits"] = {key: row["limits"].get(key, "") for key in LIMIT_NAMES}
        rows.append(row)
    if not rows:
        rows = [blank("기본")]
        rows[0]["order"] = [[key, "avoid"] for key in legacy]
    active = next((p for p in rows if p["id"] == settings.get("map_preset_active")), None)
    if active is None:
        active = rows[0]
    elif isinstance(settings.get("map_avoid"), list) and legacy != avoids(active):
        active["order"] = [[key, mode] for key, mode in active["order"] if mode == "want" and key not in legacy]
        active["order"].extend([key, "avoid"] for key in legacy)
    return rows, active["id"]


def records(rows, active):
    current = next(row for row in rows if row["id"] == active)
    return {"map_presets": deepcopy(rows), "map_preset_active": active, "map_avoid": avoids(current)}
