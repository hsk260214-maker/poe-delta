"""가져온 캐릭터의 리그 정규화·개수·표시 순서. 화면과 네트워크를 사용하지 않는다."""
from collections import Counter

PERMANENT_LEAGUES = (
    "Standard", "Hardcore", "SSF Standard", "SSF Hardcore",
    "Ruthless", "Hardcore Ruthless", "SSF Ruthless", "SSF Hardcore Ruthless",
)
NO_LEAGUE = "리그 정보 없음"


def league_of(char: dict) -> str:
    name = char.get("league")
    if not isinstance(name, str):
        return NO_LEAGUE
    return name.strip() or NO_LEAGUE


def league_sort_key(name: str) -> tuple:
    if name in PERMANENT_LEAGUES:
        return (0, PERMANENT_LEAGUES.index(name))
    if name == NO_LEAGUE:
        return (2,)
    return (1, name.casefold())


def league_groups(chars: list[dict]) -> list[tuple[str, int]]:
    counts = Counter(league_of(char) for char in chars)
    return sorted(counts.items(), key=lambda group: league_sort_key(group[0]))
