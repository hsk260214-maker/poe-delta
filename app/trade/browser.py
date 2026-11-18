"""HTTP 요청 없이 거래소 웹페이지 링크를 만든다."""
import json
from urllib.parse import quote

from trade.config import OFFICIAL, validate_server

MAX_URL_LEN = 2000


def build_url(league: str, query: dict, server: str = OFFICIAL, lang: str = "en") -> str:
    validate_server(server, lang)
    league = league.strip()
    if not league:
        raise ValueError("리그 이름을 입력하세요")
    data = quote(json.dumps(query, ensure_ascii=False, separators=(",", ":")), safe="")
    url = f"{server}/trade/search/{quote(league, safe='')}?q={data}"
    if len(url) > MAX_URL_LEN:
        raise ValueError(f"검색 조건이 너무 깁니다 (현재 {len(url)}자 / 기준 {MAX_URL_LEN:,}자). 켜 둔 옵션을 줄여 주세요")
    return url


def result_url(league: str, query_id: str, server: str = OFFICIAL, lang: str = "en") -> str:
    validate_server(server, lang)
    return f"{server}/trade/search/{quote(league, safe='')}/{quote(query_id, safe='')}"


def open_url(url: str) -> bool:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    return QDesktopServices.openUrl(QUrl(url))
