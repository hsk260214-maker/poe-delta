"""거래소 주소와 즉시 저장하는 설정."""
from storage import load_settings, save_settings

OFFICIAL = "https://www.pathofexile.com"
KAKAO = "https://poe.kakaogames.com"
KAKAO_ENABLED = True
RESULT_COUNTS = tuple(range(10, 101, 10))
_routing_revision = 0


def result_count(value: object) -> int:
    return value if type(value) is int and value in RESULT_COUNTS else 20


def settings() -> dict:
    return load_settings().get("trade", {}).copy()


def mode() -> str:
    return "api" if settings().get("mode", "api") == "api" else "browser"


def default_server() -> str:
    return KAKAO if KAKAO_ENABLED else OFFICIAL


def save(**changes) -> None:
    global _routing_revision
    data = load_settings()
    previous = data.get("trade", {})
    current = data["trade"] = {**previous, **changes}
    save_settings(data)
    if any(previous.get(key, default) != current.get(key, default)
           for key, default in (("mode", "api"), ("server", default_server()))):
        _routing_revision += 1


def routing_revision() -> int:
    return _routing_revision


def validate_server(server: str, lang: str) -> None:
    if server not in (OFFICIAL, KAKAO):
        raise ValueError("지원하지 않는 거래소 서버입니다")
    if server == KAKAO and (lang != "ko" or not KAKAO_ENABLED):
        raise ValueError("카카오 서버는 한글 클라이언트에서만 지원합니다. 거래소 설정에서 서버를 '공식'으로 바꾸세요")
