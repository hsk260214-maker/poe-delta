"""정확한 미확인 고유 후보. 기존 번들의 문자열은 지문으로 참조한다."""
from functools import lru_cache
from hashlib import sha256
import json

from data import resource_path

INDEX_FILE = "data/unidentified_unique_candidates.json"
DICTIONARIES = ("names_ko.json", "ko_en.json", "trade_items.json")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


@lru_cache(maxsize=1)
def load_candidates():
    path = resource_path(INDEX_FILE)
    try:
        payload = json.loads(path.read_bytes())
        wanted = {digest for _, _, ko, en in payload["references"] for digest in (ko, en)}
        resolved = {}
        conflicts = set()
        for filename in DICTIONARIES:
            for name in _strings(json.loads(path.with_name(filename).read_bytes())):
                digest = sha256(name.encode()).hexdigest()
                if digest in wanted:
                    if resolved.setdefault(digest, name) != name:
                        conflicts.add(digest)
    except (OSError, ValueError):
        return {}

    candidates = {}
    for base, category, ko, en in payload["references"]:
        if ko in resolved and en in resolved and ko not in conflicts and en not in conflicts:
            candidates.setdefault((base, category), []).append((resolved[ko], resolved[en]))
    for base, category, ko, en in payload["public_names"]:
        candidates.setdefault((base, category), []).append((ko, en))
    return candidates


def candidate_names(lang, base_ref, category, uniques):
    reserved = {key for row in uniques for key in row[1:3]}
    for ko, en in load_candidates().get((base_ref, category), ()):
        name = ko if lang == "ko" else en
        if en not in reserved and name not in reserved:
            yield name
