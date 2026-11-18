"""캐릭터 가져오기: pathofexile.com 공개 프로필 / PoB 빌드 코드·링크."""
from __future__ import annotations

import base64
import json
import re
import zlib
from urllib.parse import quote

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ExileDelta/1.0",
      "Cache-Control": "no-cache", "Pragma": "no-cache"}
HOST = "https://www.pathofexile.com/"
REALMS = [("PC", "pc"), ("Xbox", "xbox"), ("PlayStation", "sony")]


class ImportError_(Exception):
    pass


# ---------------------------------------------------------------- 계정 (공개 프로필)
def normalize_account(name: str, realm: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", "", name) if realm == "pc" else name.replace(" ", "+")
    return re.sub(r"(.*)[#-](\d{4})$", r"\1#\2", name)


# ---------------------------------------------------------------- 요청 한도
# pathofexile.com 은 IP 마다 한도가 있음 (예: 캐릭터 요청 15/1분, 90/30분, 180/2시간 — 넘기면 최대 1시간 차단).
# 응답 헤더(X-Rate-Limit-*)로 지금 사용량을 기억해 두고, 자동 갱신은 한도에 가까우면 쉰다.
RL: dict[str, tuple[float, list[tuple[int, int, int]]]] = {}  # 정책 → (기록 시각, [(지금 횟수, 최대, 기간초)])
PAUSE_UNTIL = 0.0  # 429 를 받으면 이 시각까지 요청 안 함


def _note_rate(r: requests.Response) -> None:
    import time
    from ratelimit import parse_headers

    global PAUSE_UNTIL
    now = time.time()
    note = parse_headers(r.headers, r.status_code, now)
    if note.policy and note.rows:
        RL[note.policy] = (now, note.rows)
    PAUSE_UNTIL = max(PAUSE_UNTIL, note.restricted_until)


def budget_note() -> str | None:
    """자동 갱신을 쉬어야 하면 이유, 아니면 None. 10분 이상 기간 한도의 85% 를 넘으면 아낌
    (나머지는 직접 '다시 가져오기'·새 캐릭터 등록용으로 남김)."""
    import time

    left = PAUSE_UNTIL - time.time()
    if left > 0:
        return f"요청 한도 초과로 {int(left // 60) + 1}분 쉬는 중"
    for at, rows in RL.values():
        if time.time() - at > 300:
            continue  # 5분 넘은 기록은 믿지 않음 → 한 번 요청해서 새로 확인
        for hits, mx, per in rows:
            if hits >= mx * 0.85 and per >= 600:
                return f"요청 한도 아끼는 중 ({hits}/{mx}, {per // 60}분 기준)"
    return None


def _get(url: str) -> requests.Response:
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except requests.RequestException as e:
        raise ImportError_(f"네트워크 오류: {e}") from e
    _note_rate(r)
    if r.status_code in (401, 403):
        raise ImportError_("계정 프로필이 비공개이거나 존재하지 않습니다.\n(pathofexile.com 프로필 → Privacy Settings 에서 Characters 탭 공개 필요)")
    if r.status_code == 404:
        raise ImportError_("계정 이름이 올바르지 않습니다. (예: Name#1234)")
    if r.status_code == 429:
        raise ImportError_("요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    if r.status_code != 200:
        raise ImportError_(f"서버 응답 오류 ({r.status_code})")
    return r


def list_characters(account: str, realm: str = "pc") -> tuple[str, list[dict]]:
    """(정확한 계정명, 캐릭터 목록)."""
    account = normalize_account(account, realm)
    r = _get(f"{HOST}character-window/get-characters?accountName={quote(account)}&realm={realm}")
    chars = r.json()
    if not isinstance(chars, list) or not chars:
        raise ImportError_("이 계정에는 가져올 캐릭터가 없습니다.")
    # get-characters 는 대소문자 무시, 나머지 API 는 구분 → 프로필 페이지에서 정확한 이름 확인 (PoB 와 동일)
    try:
        p = requests.get(f"{HOST}account/view-profile/{quote(account)}", headers=UA, timeout=30)
        m = re.search(r"/view-profile/([^/\"']+)/characters", p.text)
        if m:
            from urllib.parse import unquote

            account = normalize_account(unquote(m.group(1)), realm)
    except requests.RequestException:
        pass
    return account, chars


_PASSIVES: dict[tuple, tuple[float, object, object]] = {}  # (계정, 캐릭터) → (받은 시각, 레벨, 패시브)
PASSIVE_EVERY = 10 * 60


def refetch_character(account: str, realm: str, char: dict, auto: bool = False) -> tuple[dict, str]:
    """다시 가져오기: 캐릭터 목록을 새로 받아 현재 레벨·직업·리그로 갱신한 뒤 전체 데이터를 받는다.
    auto=True (1분 자동 갱신): 계정 이름은 저장된 것 그대로(프로필 페이지 요청 생략), 패시브는 레벨이 그대로면
    10분에 한 번만 → 캐릭터 요청이 2시간 한도(180회) 안에 들어감."""
    account = normalize_account(account, realm)
    if auto:
        r = _get(f"{HOST}character-window/get-characters?accountName={quote(account)}&realm={realm}")
        chars = r.json()
        if not isinstance(chars, list):
            raise ImportError_("캐릭터 목록을 받지 못했습니다.")
    else:
        account, chars = list_characters(account, realm)
    want = char["name"].lower()
    cur = next((x for x in chars if str(x.get("name", "")).lower() == want), None)
    if cur is None:
        raise ImportError_(f"'{char['name']}' 캐릭터를 계정에서 찾을 수 없습니다. (삭제되었거나 이름이 바뀜)")
    return cur, fetch_character(account, realm, cur, reuse_passives=auto)


def fetch_character(account: str, realm: str, char: dict, reuse_passives: bool = False) -> str:
    """PoB 의 계정 가져오기와 같은 형태(OAuth 응답 형태)의 JSON 문자열을 만든다."""
    import time

    name = quote(char["name"])
    acc = quote(account)
    key = (account.lower(), char["name"].lower(), realm)
    hit = _PASSIVES.get(key)
    if reuse_passives and hit and hit[1] == char.get("level") and time.time() - hit[0] < PASSIVE_EVERY:
        passives = hit[2]
    else:
        passives = _get(f"{HOST}character-window/get-passive-skills?accountName={acc}&character={name}&realm={realm}").json()
        if isinstance(passives, dict):
            _PASSIVES[key] = (time.time(), char.get("level"), passives)
    items = _get(f"{HOST}character-window/get-items?accountName={acc}&character={name}&realm={realm}").json()
    if passives is False or items is False:
        raise ImportError_("캐릭터 데이터를 받지 못했습니다.")
    data = dict(char)
    data["passives"] = passives
    data["jewels"] = passives.get("items", [])
    data["equipment"] = items.get("items", [])
    if items.get("guardian"):
        data["guardian"] = items["guardian"]
    return json.dumps({"character": data}, ensure_ascii=False)


# ---------------------------------------------------------------- PoB 코드 / 링크
SITES = [
    (r"maxroll\.gg/poe/pob/(.+?)\s*$", "https://maxroll.gg/poe/api/pob/{}"),
    (r"pob\.codes/b/(.+?)\s*$", "https://api.pob.codes/{}/raw"),
    (r"pobb\.in/(.+?)\s*$", "https://pobb.in/pob/{}"),
    (r"poe\.ninja/?p?o?e?1?/pob/(\w+)\s*$", "https://poe.ninja/poe1/pob/raw/{}"),
    (r"pastebin\.com/(\w+)\s*$", "https://pastebin.com/raw/{}"),
    (r"pastebinp\.com/(\w+)\s*$", "https://pastebinp.com/raw/{}"),
    (r"rentry\.co/(\w+)\s*$", "https://rentry.co/paste/{}/raw"),
    (r"poedb\.tw/pob/(.+?)\s*$", "https://poedb.tw/pob/{}/raw"),
]


def decode_code(code: str) -> str:
    code = re.sub(r"\s+", "", code).replace("-", "+").replace("_", "/")
    code += "=" * (-len(code) % 4)
    try:
        raw = base64.b64decode(code)
    except ValueError as e:
        raise ImportError_("PoB 코드 형식이 올바르지 않습니다.") from e
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
        try:
            xml = zlib.decompress(raw, wbits).decode("utf-8", "replace")
            break
        except zlib.error:
            continue
    else:
        raise ImportError_("PoB 코드 압축을 풀 수 없습니다.")
    if "<PathOfBuilding" not in xml:
        raise ImportError_("PoB 빌드 데이터가 아닙니다.")
    return xml


def resolve_code_or_link(text: str) -> tuple[str, str]:
    """(xml, 출처 설명)."""
    text = text.strip()
    if not text:
        raise ImportError_("PoB 코드나 링크를 입력하세요.")
    if text.startswith("<?xml") or text.startswith("<PathOfBuilding"):
        return text, "PoB XML"
    if re.match(r"^https?://", text, re.I) or re.match(r"^[\w.]+\.\w+/", text):
        for pat, raw in SITES:
            m = re.search(pat, text)
            if m:
                url = raw.format(m.group(1))
                try:
                    r = requests.get(url, headers=UA, timeout=30)
                    r.raise_for_status()
                except requests.RequestException as e:
                    raise ImportError_(f"링크에서 빌드를 받지 못했습니다: {e}") from e
                return decode_code(r.text), text
        raise ImportError_("지원하지 않는 링크입니다. (pobb.in, pastebin, poe.ninja, pob.codes, maxroll, rentry, poedb)")
    return decode_code(text), "PoB 코드"
