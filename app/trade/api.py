"""게임 위 시세 모드 전용. 요청을 직렬화한다."""
from __future__ import annotations

import json
import threading
from urllib.parse import quote

import requests

from paths import LOCAL
from ratelimit import RateLimiter
from trade import config, secret
from version import VERSION

_LOCK = threading.Lock()
_LIMITS = RateLimiter()
_POLICIES: dict[tuple[str, str], str] = {}
_LEAGUES: list[str] | None = None
MESSAGES = {
    "network": "네트워크 오류입니다. 연결을 확인한 뒤 다시 검색하세요",
    "rate_limited": "요청 제한으로 기다리는 중입니다",
    "login_required": "로그인이 필요할 수 있습니다. 거래소 설정에서 POESESSID를 넣어 주세요",
    "bad_league": "리그를 찾을 수 없습니다. 리그 이름을 확인하세요",
    "server": "거래소 서버 오류입니다. 잠시 후 다시 검색하세요",
    "mode_disabled": "게임 위 시세 모드에서만 요청할 수 있습니다",
}


class TradeError(Exception):
    def __init__(self, kind: str, retry_after: float = 0):
        self.kind = kind
        self.retry_after = retry_after
        super().__init__(MESSAGES[kind])


class TradeClient:
    def remaining(self, server: str = config.OFFICIAL, endpoint: str | None = None) -> float:
        keys = [key for (host, name), key in _POLICIES.items() if host == server and (endpoint is None or name == endpoint)]
        return max((_LIMITS.remaining(key) for key in keys), default=0)

    def _request(self, method: str, endpoint: str, path: str, server: str, *, lang: str = "en", **kwargs) -> dict:
        config.validate_server(server, lang)
        with _LOCK:
            if config.mode() != "api":
                raise TradeError("mode_disabled")
            policy = _POLICIES.get((server, endpoint), server + ":" + endpoint)
            wait = _LIMITS.remaining(policy)
            if wait > 0:
                raise TradeError("rate_limited", wait)
            contact = config.settings().get("contact", "").strip()
            headers = {"User-Agent": f"ExileDelta-custom/{VERSION}" + (f" (contact: {contact})" if contact else "")}
            if server == config.OFFICIAL:
                try:
                    cookie = secret.load_session()
                except secret.SecretError:
                    raise TradeError("login_required") from None
                if cookie:
                    headers["Cookie"] = "POESESSID=" + cookie
            try:
                response = requests.request(method, server + path, headers=headers, timeout=30,
                                            allow_redirects=False, **kwargs)
            except requests.RequestException:
                raise TradeError("network") from None
            raw_policy = response.headers.get("X-Rate-Limit-Policy", endpoint)
            key = server + ":" + raw_policy
            _LIMITS.note({**response.headers, "X-Rate-Limit-Policy": key}, response.status_code, key)
            _POLICIES[(server, endpoint)] = key
            if response.status_code == 429:
                raise TradeError("rate_limited", _LIMITS.remaining(key))
            if response.status_code in (401, 403):
                raise TradeError("login_required")
            if response.status_code in (400, 404) and endpoint in ("search", "leagues"):
                raise TradeError("bad_league")
            if response.status_code != 200:
                raise TradeError("server")
            try:
                result = response.json()
            except ValueError:
                raise TradeError("server") from None
            if not isinstance(result, dict) or result.get("error"):
                raise TradeError("server")
            return result

    def leagues(self, server: str = config.OFFICIAL, lang: str = "en") -> list[str]:
        global _LEAGUES
        if _LEAGUES is None:
            data = self._request("GET", "leagues", "/api/trade/data/leagues", server, lang=lang)
            leagues = [entry["id"] for entry in data.get("result", []) if entry.get("id")]
            if not leagues:
                raise TradeError("bad_league")
            _LEAGUES = leagues
            directory = LOCAL / "trade"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "leagues.json").write_text(json.dumps(leagues, ensure_ascii=False), encoding="utf-8")
        return _LEAGUES.copy()

    def search(self, league: str, query: dict, server: str = config.OFFICIAL, lang: str = "en") -> dict:
        if query.get("query", {}).get("status") != {"option": "securable"}:
            raise TradeError("server")
        return self._request("POST", "search", "/api/trade/search/" + quote(league, safe=""), server, lang=lang, json=query)

    def fetch(self, ids: list[str], query_id: str, server: str = config.OFFICIAL, lang: str = "en") -> dict:
        return self._request("GET", "fetch", "/api/trade/fetch/" + ",".join(quote(i, safe="") for i in ids[:10]),
                             server, lang=lang, params={"query": query_id})
