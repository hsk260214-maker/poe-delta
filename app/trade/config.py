"""거래소 주소와 즉시 저장하는 설정."""
from storage import load_settings, save_settings

OFFICIAL = "https://www.pathofexile.com"
KAKAO = "https://poe.kakaogames.com"
KAKAO_ENABLED = True


def settings() -> dict:
    return load_settings().get("trade", {}).copy()


def mode() -> str:
    trade = settings()
    return "api" if trade.get("mode") == "api" and trade.get("api_ack_at") else "browser"


def save(**changes) -> None:
    data = load_settings()
    data["trade"] = {**data.get("trade", {}), **changes}
    save_settings(data)


def validate_server(server: str, lang: str) -> None:
    if server not in (OFFICIAL, KAKAO):
        raise ValueError("지원하지 않는 거래소 서버입니다")
    if server == KAKAO and (lang != "ko" or not KAKAO_ENABLED):
        raise ValueError("카카오 서버는 한글 클라이언트에서만 지원합니다. 거래소 설정에서 서버를 '공식'으로 바꾸세요")
