"""API 검색 한 번에서 받은 ID와 조회 진행 상태."""
from dataclasses import dataclass, field


@dataclass
class ResultSession:
    initial_count: int
    ids: list[str] = field(default_factory=list)
    total: int = 0
    next: int = 0
    rows: list[dict] = field(default_factory=list)
    query_id: str = ""
    prefix: str = ""
    summary: str | None = None
    error: str = ""
