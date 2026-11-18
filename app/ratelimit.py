"""GGG의 정책별 요청 제한 헤더 공용 해석."""
from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime


@dataclass
class RateNote:
    policy: str
    rows: list[tuple[int, int, int]]
    restricted_until: float
    next_at: float


def parse_headers(headers, status: int = 200, now: float | None = None) -> RateNote:
    now = time.time() if now is None else now
    headers = {k.lower(): v for k, v in headers.items()}
    policy = headers.get("x-rate-limit-policy", "")
    rows, restricted_until, next_at = [], 0.0, 0.0
    for rule in headers.get("x-rate-limit-rules", "").split(","):
        rule = rule.strip().lower()
        limits = headers.get(f"x-rate-limit-{rule}", "")
        states = headers.get(f"x-rate-limit-{rule}-state", "")
        for limit, state in zip(limits.split(","), states.split(",")):
            try:
                maximum, period, _penalty = map(int, limit.split(":"))
                hits, _period, restricted = map(int, state.split(":"))
            except ValueError:
                continue
            rows.append((hits, maximum, period))
            if restricted > 0:
                restricted_until = max(restricted_until, now + restricted)
            if hits >= maximum:
                next_at = max(next_at, now + period)
    if status == 429:
        raw = headers.get("retry-after", "")
        try:
            wait = float(raw)
        except ValueError:
            try:
                wait = parsedate_to_datetime(raw).timestamp() - now
            except (ValueError, TypeError, OverflowError):
                wait = 60
        restricted_until = max(restricted_until, now + max(0, wait))
    return RateNote(policy, rows, restricted_until, max(next_at, restricted_until))


class RateLimiter:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.policies: dict[str, float] = {}

    def note(self, headers, status: int = 200, fallback: str = "") -> str:
        note = parse_headers(headers, status, self.clock())
        policy = note.policy or fallback
        self.policies[policy] = max(self.policies.get(policy, 0), note.next_at)
        return policy

    def remaining(self, policy: str) -> float:
        return max(0.0, self.policies.get(policy, 0) - self.clock())
