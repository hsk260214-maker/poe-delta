# FEAT-001 인게임 거래소 시세 검색

- 상태: 기획 v4.3 — 개발 완료 (개발 리뷰 2/3 APPROVED). 남은 일: 머성 수동 확인(`docs/checks/FEAT-001-manual-check.md`), 배포 전 FIX-001. 커밋 안 됨
- 브랜치: `custom` (원본 `upstream` = KyungseokKANG/exile-delta, 기준 커밋 4fa6d68)
- 작성: poe 기획 세션

## 0. 변경 이력

- v1 → v3: 기획 리뷰 1/3·2/3 지적 반영, 3/3 APPROVED (리그 출처, 단축키 등록·플래그, 서버·언어, 대상·최소값 규칙, 요청 제한, POESESSID, 창 동작, 테스트 격리, `map_warn.py` 공용 함수).
- v3 → v4: 개발 세션이 GGG 개발자 문서(https://www.pathofexile.com/developer/docs/index)와의 충돌을 보고했다. 문서는 API Reference·Data Exports 밖의 엔드포인트를 분석해 쓰는 것을 약관 7i 위반으로 적고 있고, v3이 쓰는 `/api/trade/*`는 그 목록에 없다. 머성 결정: **두 방식을 모두 만들고 설정에서 고른다.**

| v4 변경 | 위치 |
|---|---|
| 검색 방식 2개 (브라우저 모드 기본, 게임 위 시세 모드는 위험 확인 후 사용) | 1.1, 4.3, 4.6, 7절 |
| stat ID 자료를 런타임 `/api/trade/data/stats` 요청 대신 저장소에 넣은 데이터로 (두 모드 공통) | 6.6 |
| 카카오 거래소 주소 정정: `poe.game.daum.net` → `poe.kakaogames.com` | 6.4 |
| 브라우저 모드의 리그 결정 (요청 없이) | 4.2 |
| 모드별 완료 기준·테스트 | 9, 10절 |

v4 → v4.1 (설계 변경 리뷰 1/3):

| 리뷰 지적 | 결정 | 위치 |
|---|---|---|
| 1 리그 목록 요청 시점 | (가) 게임 위 시세 모드의 첫 검색 버튼을 누를 때 함께 받음. 창 열기만으로는 요청 없음 | 4.2, 6.7, 7절 |
| 2 리그 없는 브라우저 링크 | 리그 없는 링크는 만들지 않음. 리그 칸이 비면 버튼을 막고 입력 안내 | 4.2, 4.3, 6.4, 9절 |
| 3 링크 길이 | 기준 2,000자. 넘으면 버튼을 막고 옵션을 줄이라고 안내. 가장 긴 샘플은 머성이 실제로 열어 봄 | 4.3, 6.4, 9·10절 |
| 4 APT negate·value 매처 | 매처별 negate 저장, negate 줄은 최소·최대를 바꾸고 부호를 뒤집어 보냄. value 고정 매처는 "맞추지 못함" | 6.6 |
| 5 APT 받기·해석 코드 중복 | `dict_builder.apt_ndjson`·`_skel` 재사용, 기준 주소를 인자로 받게만 바꿈 | 3절, 6.1, 6.6 |
| 참고 2건 | 완료 기준 5 "거래소 관련 요청 0회", `sys.modules`에 `trade.api` 없음 확인 | 9·10절 |

v4.1 → v4.2 (설계 변경 리뷰 2/3):

| 리뷰 지적 | 결정 | 위치 |
|---|---|---|
| 1 `dict_builder` 회귀 테스트가 저장소 `tools/.cache`를 씀 | 테스트에서 `dict_builder.CACHE`를 임시 폴더로 바꿈 (`updater.py:224`와 같은 방식). 격리 원칙에 `tools/.cache` 포함 | 10절 |
| 참고: 2,000자 초과 샘플 | 실제 샘플로 못 만들면 테스트에서 `MAX_URL_LEN`을 작게 바꿔 경계 검사 | 10절 |
| 참고: SSF·사설 리그 | 다음 버전 후보로 남김 | 5절 |

v4.2 → v4.3 (개발 blocker + 머성 요청):

개발 세션 형식 확인 결과(고정 커밋 `803d188d1359c4d5b1e3826da5dc680ea74a158f`): 종류별 ID는 `entry.trade.ids[종류]`에 있고, `(Local)` 표시나 Local 필드는 없으며, `trade.inverted`가 97개 항목에 있다. 기획 세션이 같은 커밋의 APT 코드를 확인한 결과는 다음과 같다.

- 같은 문장의 전역·Local 항목은 묶음 줄 `{"resolve": {...}, "stats": [...]}` 하나에 들어 있다 (86줄). 묶음의 `resolve.strat`는 `select` 30 / `trivial-merge` 40 / `percent-merge` 11 / `flag-merge` 5.
- `select` 묶음은 `resolve.test[i]`가 `stats[i]`가 붙는 아이템 종류다 (`null` = 그 밖, `"WEAPON"`, `"ARMOUR"`, 정확한 종류 이름). 예: `+# to Armour` → `test: [null, "ARMOUR"]`, ID `809229260`(전역) / `3484657501`(방어구 Local). APT는 아이템 종류가 맞는 칸을 먼저, 없으면 `null` 칸을 고른다 (`renderer/src/parser/stat-translations.ts` `_resolveTranslation`, `testItemCategory`).
- `WEAPON`·`ARMOUR` 묶음 정의는 `renderer/src/parser/meta.ts` (WEAPON: 한손·양손 근접, 활, 완드, 낚싯대 / ARMOUR: 갑옷, 장화, 장갑, 투구, 방패).
- 부호: `create-stat-filters.ts`가 `tradeInvert = stat.trade.inverted`로 시작해 `matcher.negate`면 뒤집는다. 최종 반전 = `inverted` XOR `negate`.
- 기존 `dict_builder.apt_ndjson`은 묶음 줄을 펼치면서 `resolve`를 버린다. 그래서 Local 정보가 사라져 보였다.

| 변경 | 위치 |
|---|---|
| Local 판별을 APT `select` 묶음 규칙으로 바꿈 (`(Local)` 문자열 판별 삭제) | 6.6 |
| `trivial-merge`·`percent-merge`·`flag-merge` 묶음은 이번 버전에서 "맞추지 못함" | 6.6 |
| 부호 반전 = `inverted` XOR `negate` | 6.6 |
| `apt_ndjson`에 묶음 정보를 버리지 않고 받는 방법 추가 | 3절, 6.6 |
| **머성 요청: 가판대(즉시 구매) 매물만 검색** — 판매 상태 `securable` 고정, "온라인 판매자만" 삭제, 결과의 온라인 여부 칸 삭제 | 4.2, 4.3, 9절 |

v3 승인 내용 중 위 표에 없는 부분(단축키, `_on_clipboard` 분기, 머리 해석, 매칭·최소값 규칙, 요청 제한, POESESSID 보호, 창 동작, 테스트 격리)은 그대로다.

## 1. 목표

게임에서 아이템에 마우스를 올리고 단축키를 누르면, 그 아이템과 비슷한 옵션의 매물 검색 조건을 만들어 준다.
옵션을 켜고 끄거나 최소값을 바꾼 뒤, 설정에서 고른 방식으로 검색한다.

### 1.1 두 가지 검색 방식

| | 브라우저 모드 (기본) | 게임 위 시세 모드 |
|---|---|---|
| 동작 | 조건이 채워진 공식 거래소 웹페이지를 브라우저로 연다 | 프로그램이 거래소에 직접 검색해 결과를 게임 위 창에 보여 준다 |
| 프로그램의 거래소 요청 | **0회** | 검색 버튼 1회당 search 1 + fetch 최대 2 (+ 실행 후 첫 검색에만 리그 목록 1). 창 열기만으로는 0회 |
| GGG 개발자 문서와의 관계 | 공개 웹페이지 링크만 연다 (Path of Building과 같은 방식) | 문서에 없는 내부 API 사용 — 문서상 약관 7i 위반. Awakened PoE Trade 등과 같은 방식으로 사실상 묵인되고 있으나 보장 없음 |
| 켜는 방법 | 기본값 | "거래소 설정"에서 고르고, 위험 안내 창에서 확인해야 켜짐 (4.6) |

## 2. 레퍼런스

| 프로그램 | 참고할 점 | 이번에 가져오지 않는 점 |
|---|---|---|
| Awakened PoE Trade (SnosMe, MIT) | `Ctrl+D` 시세 확인, 옵션 체크·최소값 조정, 기본 최소값을 실제 수치보다 약간 낮게 잡기, 옵션 문장 ↔ 거래소 stat ID 대응 데이터(`stats.ndjson`) | pseudo 합산 옵션, 대량 거래, 위키 열기, OCR, 마우스가 벗어나면 닫히는 창 |
| PoE Overlay Community Fork | 공식 거래소 결과 요약, 클릭으로 필터 켜고 끄기 | poeprices.info 예측, poe.ninja 환율, 인게임 브라우저 |
| Path of Building Community | 검색 JSON을 `/trade/search/{리그}?q={URL 인코딩 JSON}` 링크로 브라우저에 여는 방식 | — |
| PoeTradeSearch (한국어 도구) | 카카오 거래소도 공식과 같은 경로를 쓴다는 점 | — |

## 3. 기존 코드와의 연결

| 기존 요소 | 위치 | 이번 기능에서의 쓰임 |
|---|---|---|
| 클립보드 감시 | `app/main.py` `_on_clipboard` (L296) | 거래소 대기 플래그가 살아 있으면 거래소 창으로 보낸다 (6.3) |
| 아이템 해석 | `app/itemmodel.py` `parse`, `skeleton` (L262), `TAG_RE` (L18) | 옵션 줄과 종류(kind)를 그대로 쓴다. 희귀도·아이템 레벨·링크·타락은 `ItemModel.head`/`flags`에서 `trade/query.py`가 뽑는다 (6.5) |
| 한글 → 영문 | `app/ko2en.py` `translate_mod` (L197), `translate_base` (L328) | 한글 클라이언트 옵션 줄을 영문으로 바꾼 뒤 stat ID와 맞춘다 (6.4) |
| 포커스·키 입력 | `app/item_editor.py` `_send_copy_to` (L47), `_foreground_other` (L118), `_focus_window` (L135), `_key_down` (L169), `_press_ctrl_c` (L181). `app/map_warn.py` L144~184가 이 5개를 `from item_editor import …`로 가져다 씀 | 5개 모두 새 공용 모듈 `app/winutil.py`로 옮겨 옵션변경 창·지도 경고 창·거래소 기능이 함께 쓴다 (중복 금지). item_editor 안의 호출 위치(L852, L1137, L1168, L1175, L1187)도 새 이름으로 |
| 요청 제한 해석 | `app/pob/importers.py` `_note_rate` (L36) | 헤더 해석 부분을 새 공용 모듈 `app/ratelimit.py`로 옮겨 함께 쓴다 (6.7) |
| 백그라운드 실행 | `app/asyncjob.py` `run_async` | 게임 위 시세 모드의 요청 실행. 동시에 하나만 (6.7) |
| 리그 | 계정으로 가져온 캐릭터의 `source["character"]["league"]` (`app/import_dialog.py:212`) | 기본 리그 후보 1순위 (4.2) |
| 설정 | `app/storage.py` `load_settings` / `save_settings` | `trade` 키에 저장 (6.9) |
| 출처 표기 | `README.md` "고마운 프로젝트들"에 Awakened PoE Trade(MIT) 이미 있음 (L102) | 거래소 stat 데이터 사용을 같은 줄에 덧붙인다 |
| APT 데이터 받기·해석 | `app/dict_builder.py` `APT` (L239, master 주소), `apt_ndjson` (L242, 묶음 줄 펼치기), `_skel` (L263, `itemmodel.skeleton`과 같은 규칙) | `tools/build_trade_stats.py`가 그대로 재사용한다 (6.6). 새로 쓰지 않는다 |

**바뀌는 기존 파일** (기능 동작 변경 없이 연결만):

| 파일 | 바뀌는 내용 |
|---|---|
| `app/main.py` | 거래소 기능 시작·종료, `_on_clipboard` 분기 추가(6.3), 메뉴에 "거래소 설정" 항목 |
| `app/item_editor.py` | 5개 함수를 `winutil`로 옮기고 그곳에서 가져오도록 바꿈(동작 동일), "거래소 검색" 버튼 1개 |
| `app/map_warn.py` | L144·L159·L168·L176·L184의 `from item_editor import …`를 `from winutil import …`로만 바꿈 (동작 동일) |
| `app/pob/importers.py` | `_note_rate`의 헤더 해석을 `ratelimit` 호출로 바꿈 (`RL`, `PAUSE_UNTIL` 동작 동일) |
| `app/dict_builder.py` | `apt_ndjson`에 기준 주소 인자(`base`, 기본값 = 지금의 `APT`)를 추가. 기본값과 다른 주소면 캐시 파일 이름에 그 주소를 구분하는 값을 붙여 기존 master 캐시와 섞이지 않게 한다 (개발 세션이 이미 반영). 이어서 `flatten` 인자(기본값 `True` = 지금 동작)를 추가해, `False`면 묶음 줄을 펼치지 않고 원래 줄(`resolve` 포함) 그대로 돌려준다. 기존 호출(`apt_stat_pairs`)의 동작은 그대로 |
| `README.md` | 출처 한 줄 보충 |
| `requirements-dev.txt` (새 파일) | `pytest` |

나머지는 모두 새 파일이다: `app/winutil.py`, `app/ratelimit.py`, `app/trade/*`, `data/trade_stats.json`, `data/LICENSE-awakened-poe-trade.txt`, `tools/build_trade_stats.py`, `tests/*`.

## 4. 기능 범위 (MVP)

### 4.1 검색 실행

- 단축키 `Ctrl+D`: **PoE 창이 앞에 있을 때만 등록**되어 있다 (6.2). 다른 프로그램에서는 `Ctrl+D`가 원래대로 동작한다.
- 누르면 게임에 `Ctrl+C`를 한 번 보내 아이템 텍스트를 복사하고, 그 복사분을 거래소 창으로 보낸다.
- "Ctrl+C 감지" 설정(`watch_clipboard`)을 꺼 두어도 `Ctrl+D`는 동작한다.
- 옵션변경 창의 "거래소 검색" 버튼: 지금 열려 있는 아이템으로 거래소 창을 연다.
- 거래소 창이 열리기만 해서는 아무 요청도 보내지 않는다. 검색은 창의 검색 버튼(또는 `Enter`)을 누를 때 한 번만 한다. 자동 반복·자동 새로고침 없음.

### 4.2 검색 대상과 조건

**대상:** 아이템 종류가 무기·방어구·장신구(반지·목걸이·벨트)·화살통·주얼(어비스 주얼 포함)이고, 희귀도가 레어 또는 유니크인 식별된 아이템.

그 밖의 경우(마법·일반 희귀도, 젬, 화폐, 플라스크, 지도, 미확인 아이템, 해석 실패)는 검색 버튼 없이 "이 아이템은 아직 시세 검색을 지원하지 않습니다 (종류: …)"를 표시한다.

**머리 조건:**

| 항목 | 레어 | 유니크 |
|---|---|---|
| 이름 | 넣지 않음 | `name` + `type` 둘 다 넣음 (Foulborn 등 같은 베이스의 다른 유니크 구분) |
| 베이스 | `type` = 베이스 이름 | 위와 같음 |
| 아이템 레벨 | 최소값 = 실제 값 (기본 꺼짐) | 넣지 않음 |
| 링크 | 5링크 이상일 때만 최소 링크 수 (기본 켬) | 같음 |
| 타락 | 타락이면 타락 필터 켬, 아니면 "타락 아님" 필터 켬 | 같음 |
| 판매 방식 | **가판대(즉시 구매) 매물만**: `"status": {"option": "securable"}` 고정, 화면에서 바꾸지 않음 (머성 요청. 가판대 가격은 판매자가 거절할 수 없는 실제 가격이라 미끼 가격 걱정이 없음) | 같음 |

**리그:** 다음 순서로 정한다.

1. 현재 캐릭터가 계정으로 가져온 캐릭터면 `source["character"]["league"]`
2. 없으면(PoB 코드로 가져온 캐릭터 등) 마지막으로 고르거나 입력한 리그 (`settings["trade"]["league"]`)
3. 그것도 없으면 모드별로:
   - 게임 위 시세 모드: 검색 버튼을 누를 때 받는 `/api/trade/data/leagues` 목록(6.7)의 첫 리그. 1·2번 값이 이 목록에 없을 때도 첫 리그로 바꾸고, 바뀐 사실을 창에 표시한다.
   - 브라우저 모드: 리그 칸을 비워 두고, "브라우저로 검색" 버튼을 막은 채 "리그 이름을 입력하세요 (예: 현재 챌린지 리그 이름)"를 표시한다. 리그 없는 링크는 만들지 않는다 (리그를 비운 링크가 다른 리그를 여는 문제가 PoB #6906·#7564에서 보고됨). 1·2번 값의 유효성은 확인하지 않는다.

거래소 창의 리그 칸은 두 모드 모두 직접 입력 칸이다. 게임 위 시세 모드에서는 리그 목록을 받은 뒤 같은 칸에 목록 선택을 함께 붙인다. 바꾸면 2번 값으로 저장한다.

**옵션 줄:** 줄마다 체크박스, 종류 배지, 최소값·최대값 입력칸.

- 기본 체크: 유니크는 옵션을 모두 끔(이름으로 찾음), 레어는 explicit·fractured 줄을 켬. implicit·enchant·crafted는 기본 끔.
- 기본 최소값은 6.6 규칙을 따른다.
- 거래소 stat과 맞추지 못한 줄, 그리고 scourge·crucible 줄은 회색으로 표시하고 체크할 수 없게 한다. 마우스를 올리면 이유를 보여 준다 ("거래소 옵션과 맞추지 못함" / "후보가 여러 개" / "이번 버전은 미지원 종류").

### 4.3 검색 버튼과 결과 (모드별)

**브라우저 모드:**

- 버튼 이름 "브라우저로 검색". 누르면 6.4의 링크를 기본 브라우저로 연다 (`QDesktopServices.openUrl`).
- 버튼이 막히는 경우 (창에 이유 표시, 막힌 동안 링크를 만들거나 열지 않음):
  - 리그 칸이 비어 있음 → "리그 이름을 입력하세요"
  - 링크 길이가 기준(2,000자)을 넘음 → "검색 조건이 너무 깁니다 (현재 N자 / 기준 2,000자). 켜 둔 옵션을 줄여 주세요". 옵션 체크나 값을 바꿀 때마다 길이를 다시 계산한다.
- 거래소 창에는 결과 칸이 없고, "브라우저에서 결과를 확인하세요" 안내만 보인다.

**게임 위 시세 모드:**

- 버튼 이름 "검색". 결과는 가판대 매물 가격 오름차순 최대 20개: 가격(수량 + 화폐), 판매자 이름, 등록 시각(몇 분 전), 매물 아이템 레벨. 판매자 온라인 여부는 가판대 구매와 무관하므로 표시하지 않는다.
- 요약 한 줄: 전체 매물 수, 최저가, 상위 10개 중간값(같은 화폐끼리만, 섞여 있으면 가장 많은 화폐 기준이라고 표시).
- 조건을 바꾸면 자동 검색하지 않는다. 검색 버튼을 다시 누를 때만 요청한다.
- "거래소에서 열기": 검색 ID로 같은 검색을 브라우저로 연다.
- 창 위쪽에 "게임 위 시세 모드 (공식 문서 밖 API 사용)" 표시를 작게 둔다.

### 4.4 거래소 창 동작

- 항상 위에 뜨는 창. 처음에는 마우스 커서 근처에 뜨고, 화면 밖으로 나가지 않게 위치를 맞춘다. 사용자가 옮기면 그 위치를 기억한다 (`settings["trade"]["window"]`).
- 뜰 때 키보드 포커스를 가져온다 (최소값 입력용, `winutil.focus_window`).
- `Esc` 또는 닫기 버튼으로 닫는다. 닫을 때 단축키를 누를 때 기록해 둔 게임 창으로 포커스를 돌려준다.
- 브라우저 모드에서 "브라우저로 검색"을 눌러도 창은 닫히지 않는다 (조건을 바꿔 다시 열 수 있게).
- 마우스가 벗어나도 닫히지 않는다. "마우스가 벗어나면 닫힘"과 `Ctrl+Alt+D` 고정 모드는 MVP에서 제외한다.
- 창이 열린 채로 다시 `Ctrl+D`를 누르면 같은 창의 내용을 새 아이템으로 바꾼다.

### 4.5 오류·제한 표시 (게임 위 시세 모드)

- 요청 제한에 걸리면 남은 대기 시간을 초 단위로 표시하고, 그동안 검색 버튼을 막는다.
- 네트워크 오류, 리그 없음, 결과 0개, 로그인 필요(401·403)를 구분해 고정 문구로 알려 준다. 응답 원문과 헤더는 화면에 보이지 않는다.

### 4.6 거래소 설정 창 (메뉴 → "거래소 설정")

| 항목 | 내용 |
|---|---|
| 검색 방식 | 브라우저 모드(기본) / 게임 위 시세 모드 |
| 서버 | 공식 / 카카오 (6.4) |
| 리그 | 4.2의 2번 값 직접 입력·지우기 |
| 기본 최소값 비율 | 기본 0.9 |
| 단축키 사용 | 켬/끔 |
| POESESSID | 게임 위 시세 모드일 때만 입력 가능 (6.8) |
| 연락처 | 게임 위 시세 모드 User-Agent용 (6.7) |

**게임 위 시세 모드로 바꿀 때 위험 안내:**

- 브라우저 모드 → 게임 위 시세 모드로 바꿀 때마다 확인 창을 띄운다. 문구에 담을 내용: 이 방식은 GGG 개발자 문서에 없는 거래소 내부 API를 쓴다 / 문서는 이를 약관 위반으로 적고 있고 계정 정지 위험이 있다 / Awakened PoE Trade 등도 같은 방식이지만 GGG는 허용을 보장하지 않는다 / 위험은 사용자 계정이 진다.
- 버튼은 "위험을 이해하고 사용" / "취소". 기본 선택은 "취소". 취소하면 브라우저 모드로 남는다.
- 확인하면 `settings["trade"]["api_ack_at"]`에 시각을 기록하고 모드를 바꾼다.
- 게임 위 시세 모드에서 브라우저 모드로 바꿀 때는 확인 없이 바로 바뀐다.

## 5. 이번에 하지 않는 것

거래 귓속말, 대량 거래(화폐 교환), pseudo 합산 옵션(총 저항 등), 가격 예측, poe.ninja 시세, 지도·젬·화폐·플라스크 시세, 자동 새로고침, PoE2, 영문 클라이언트에서 카카오 서버 검색(6.4), stat 데이터 자동 갱신(6.6), 원본 캐릭터 불러오기 방식 변경, SSF·사설 리그 안내(다음 버전 후보: 리그 이름에 "SSF"가 들어 있으면 공개 거래소 검색이 없다는 안내).
기존 DPS/EHP 비교, 지도 경고, 아이템 필터 동작은 바꾸지 않는다.

## 6. 기술 설계

### 6.1 모듈

| 모듈 | 하는 일 |
|---|---|
| `app/winutil.py` (새, 옮김) | `send_copy_to`, `foreground_other`, `focus_window`, `key_down`, `press_ctrl_c` (item_editor에서 본문 그대로 옮기고 밑줄 없는 이름으로), `is_poe_window(hwnd)` (창 클래스 `POEWindowClass` 확인). item_editor·map_warn은 새 이름으로 가져온다 |
| `app/ratelimit.py` (새, 옮김) | `X-Rate-Limit-Policy` / `-Rules` / `-{rule}` / `-{rule}-State` / `Retry-After` 해석. 정책별 상태 기록과 다음 요청 가능 시각 계산 |
| `app/trade/stats.py` | `data/trade_stats.json`을 읽어 옵션 줄 + 아이템 종류 → stat ID·부호 반전 여부 (네트워크 없음, 골격은 `itemmodel.skeleton`) |
| `app/trade/query.py` | `ItemModel` 머리 해석 + 조건 → 검색 JSON, 결과 JSON → 화면 행 |
| `app/trade/browser.py` | 검색 JSON → 거래소 링크 만들기, 브라우저로 열기 (네트워크 없음) |
| `app/trade/api.py` | 게임 위 시세 모드 전용 HTTP 요청, User-Agent, 쿠키, 요청 직렬화, 오류 분류 |
| `app/trade/hotkey.py` | PoE 창 감시, `Ctrl+D` 등록/해제, 대기 플래그 |
| `app/trade/secret.py` | POESESSID 암호화 저장·읽기 (DPAPI) |
| `app/trade/trade_window.py` | 검색 조건·결과 창 (기존 `theme.py` 사용) |
| `app/trade/settings_dialog.py` | 거래소 설정 창과 위험 안내 확인 창 (4.6) |
| `tools/build_trade_stats.py` | 개발자용: `dict_builder.apt_ndjson(…, base=고정 커밋 주소, flatten=False)`로 영문 `stats.ndjson`을 묶음 정보째 받고, `dict_builder._skel`로 골격을 만들어 `data/trade_stats.json`으로 변환 (6.6). 받기·해석 코드를 새로 쓰지 않는다 |

`browser.py`와 `stats.py`는 `api.py`와 `requests`를 import하지 않는다. 브라우저 모드에서는 `api.py`를 import하지 않는다.

### 6.2 단축키 등록 방식

- `QTimer` 200ms마다 `GetForegroundWindow`를 확인한다. 앞 창이 `POEWindowClass`면 `RegisterHotKey(Ctrl+D)`, 아니게 되면 `UnregisterHotKey`. 그래서 PoE가 앞에 없을 때 다른 프로그램의 `Ctrl+D`를 가로채지 않는다.
- 핫키 메시지는 Qt 네이티브 이벤트 필터(`QAbstractNativeEventFilter`, `WM_HOTKEY`)로 받는다. 새 라이브러리는 쓰지 않는다.
- 눌리면: 게임 창 hwnd 기록 → 대기 플래그 설정(만료 시각 = 지금 + 1.0초) → `winutil.press_ctrl_c()` 1회.
- 프로그램 종료 시 등록을 해제한다.
- `RegisterHotKey`가 실패하면(Awakened PoE Trade 등이 이미 `Ctrl+D`를 등록) 상태 표시줄에 "Ctrl+D를 다른 프로그램이 쓰고 있습니다"를 보여 준다. 200ms마다 다시 시도하지만, 안내는 실패가 처음 생길 때 한 번만 보여 주고 등록에 성공하면 초기화한다.

### 6.3 `_on_clipboard` 분기

빈 값 재시도는 최대 약 1.53초(60+120+250+400+700ms)로 플래그 만료(1.0초)보다 길다. 그래서 **어디로 보낼지는 첫 클립보드 변경 알림(attempt 0)에서 한 번만 정하고, 재시도 동안 그 결정을 넘겨준다.**

1. attempt 0에서 대기 플래그를 확인한다. 살아 있으면 목적지 = 거래소로 정하고 플래그를 지운다. 아니면 목적지 = 기존 흐름.
2. 목적지가 기존 흐름이고 `watch_clipboard`가 꺼져 있으면 끝 (attempt 0 기준 판정).
3. 빈 값이면 기존과 같이 재시도 (60~700ms, 최대 5회). 재시도 호출에 목적지를 함께 넘기고, 재시도에서는 플래그를 다시 보지 않는다.
4. **목적지가 거래소면** 텍스트를 거래소 창으로 보낸 뒤 끝. 지도·`parse_item` 판정보다 먼저 한다.
5. 기존 흐름: `_show_map` → `parse_item` → `parse_model` → 옵션변경 창.

플래그는 attempt 0에서 한 번 쓰이면 바로 지워지고, 클립보드 변경이 없으면 1.0초가 지나 저절로 만료된다. 만료 뒤의 `Ctrl+C`는 기존처럼 옵션변경 창으로 간다.
아이템이 아닌 곳에서 `Ctrl+D`를 눌러 클립보드가 바뀌지 않으면 아무 창도 뜨지 않는다.

### 6.4 서버, 언어, 링크

stat ID는 서버와 상관없이 같으므로, 매칭은 항상 영문 데이터(`data/trade_stats.json`)로 한다.

| 서버 | 주소 | 옵션 줄 | 이름·베이스 |
|---|---|---|---|
| 공식 (기본) | `https://www.pathofexile.com` | 영문 클라이언트: 원문 / 한글 클라이언트: `ko2en.translate_mod`로 바꾼 영문 → stat ID | 영문 (한글 클라이언트는 `ko2en.translate_base`, 유니크는 `translate_item` 결과의 영문 이름) |
| 카카오 | `https://poe.kakaogames.com` (v3의 `poe.game.daum.net`은 옛 주소) | 위와 같이 stat ID | 한글 클라이언트 원문 한글 이름·베이스 |

- 서버 주소는 `app/trade/` 안 한 곳의 상수로만 둔다.
- 카카오 서버는 한글 클라이언트일 때만 고를 수 있다. 영문 클라이언트에서 카카오를 고르면 "카카오 서버는 한글 클라이언트에서만 지원합니다"를 표시하고 검색하지 않는다.
- 한글 클라이언트 사용자가 공식 서버로 검색하면 창 아래에 "카카오 서버와 매물·시세가 다를 수 있습니다"를 작게 표시한다. (FIX-002에서 삭제: 같은 서버)
- 카카오가 한글 이름·베이스를 받는지 확인: 게임 위 시세 모드에서 실제 search 1회(개발 세션), 브라우저 모드에서 링크 1회 열어 보기(머성 확인 목록). 받지 않으면 카카오 선택을 숨기고 기획에 알린다.

**브라우저 링크 (`browser.py`):**

- 형식: `{서버}/trade/search/{URL 인코딩 리그}?q={URL 인코딩 검색 JSON}`. 리그는 반드시 있어야 하고, 비어 있으면 링크를 만들지 않는다 (4.2, 4.3).
- 검색 JSON은 게임 위 시세 모드가 search에 보내는 본문과 같은 것(`query.py`가 만든 것)을 쓴다. 인코딩은 JSON을 공백 없이 직렬화(`separators=(",", ":")`)한 뒤 `urllib.parse.quote(…, safe="")`.
- 길이 기준 `MAX_URL_LEN = 2000` (완성된 링크 전체 글자 수, `browser.py` 상수 하나). 넘으면 링크를 열지 않는다 (4.3). 2,000은 Windows 셸 실행·브라우저에서 흔한 경계값이고 실제 한계는 확인되지 않았다. 머성 확인에서 문제가 있으면 이 상수만 바꾼다.
- 테스트 샘플 중 링크가 가장 긴 것(옵션이 가장 많은 레어, 기준 이하)의 실제 길이를 개발 세션이 재서 보고하고, 머성 확인 목록에서 그 링크를 실제로 열어 조건이 모두 채워지는지 본다.

### 6.5 머리 해석 (`query.py`)

`ItemModel`에는 희귀도·아이템 레벨·링크 필드가 없으므로 `query.py`가 `head`와 `flags`에서 직접 뽑는다.

| 값 | 영문 줄 | 한글 줄 |
|---|---|---|
| 아이템 종류 | `Item Class:` | `아이템 종류:` |
| 희귀도 | `Rarity:` | `아이템 희귀도:` |
| 아이템 레벨 | `Item Level:` | `아이템 레벨:` |
| 링크 | `Sockets:` 값에서 `-`로 이어진 가장 긴 묶음 | `홈:` 값, 같은 방식 |
| 미확인·타락 | `flags` (`itemmodel.FLAG_LINES`) | 같음 |

한글 키 문자열은 기존 `itemmodel`/`itemcheck`/`ko2en`에 정의된 상수를 그대로 쓰고, 없는 것만 `query.py`에 둔다.

### 6.6 stat 데이터, 매칭, 기본 최소값

**데이터 출처 (v4 변경):** 런타임에 `/api/trade/data/stats`를 요청하지 않는다 (두 모드 공통).

- `tools/build_trade_stats.py`는 `dict_builder.apt_ndjson("en/stats.ndjson", refresh, base=<고정 커밋 주소>, flatten=False)`로 Awakened PoE Trade(MIT) 영문 데이터를 **묶음 정보째** 받는다. 고정 커밋 = `803d188d1359c4d5b1e3826da5dc680ea74a158f` (개발 세션 확인), 주소 = `https://raw.githubusercontent.com/SnosMe/awakened-poe-trade/<커밋 해시>/renderer/public/data/`. `matchers`·`ref` 형식 처리는 기존 코드가 이미 하므로 다시 쓰지 않는다.
- `data/trade_stats.json`에 저장하는 것:
  - 매처마다: 골격(`dict_builder._skel(matcher.string)`), `negate` 여부, `value` 유무, `advanced` 여부, 속한 항목 번호.
  - 항목마다: 종류별 trade ID 목록(explicit / implicit / crafted / fractured / enchant), `trade.inverted` 여부, 묶음에 속하면 묶음 번호와 그 묶음 안의 `resolve.test` 값(`select`일 때).
  - 묶음마다: `resolve.strat`.
  - 사용한 커밋 해시.
- 같은 커밋의 LICENSE를 `data/LICENSE-awakened-poe-trade.txt`로 함께 둔다.
- 이 스크립트는 개발자가 필요할 때 손으로 돌린다. 앱은 저장소에 들어 있는 `data/trade_stats.json`만 읽는다.
- 형식 확인은 끝났다 (0절 v4.3). 묶음 줄에 `resolve`·`stats` 말고 다른 키가 있거나 `resolve.strat`이 위 4가지 밖이면 개발을 멈추고 기획에 알린다.

**아이템 종류 → APT 종류 이름:** `query.py`가 `Item Class:`/`아이템 종류:` 값을 다음으로 바꾼다 (APT `meta.ts`와 같은 묶음).

| APT 이름 | 아이템 종류 |
|---|---|
| `WEAPON` | 한손 도끼·철퇴·검, 발톱, 단검, 룬 단검, 셉터, 완드, 양손 도끼·철퇴·검, 지팡이, 전쟁 지팡이, 활, 낚싯대 |
| `ARMOUR` | 갑옷, 장화, 장갑, 투구, 방패 |
| 그 밖 | 반지, 목걸이, 벨트, 화살통, 주얼, 어비스 주얼 (`select`의 `null` 칸으로 감) |

영문·한글 Item Class 이름표는 `query.py`에 둔다 (기존 `ko2en` 사전에 종류 이름이 있으면 그것을 쓴다).

**매칭:**

1. 영문 옵션 줄의 골격을 `itemmodel.skeleton`으로 만든다 (데이터 쪽 `dict_builder._skel`과 같은 규칙: 숫자·범위·자리표시 → `#`, 부호 제거, 소문자).
2. 같은 골격의 매처를 찾는다. `value`가 고정된 매처(선택형 stat)에 걸리면 이번 버전에서는 "맞추지 못함"으로 처리한다.
3. 매처가 묶음에 속하면 `resolve.strat`에 따라 항목을 고른다.
   - `select`: 아이템 종류(위 표)가 맞는 `test` 칸의 항목을 먼저 고르고, 없으면 `test`가 `null`인 칸의 항목을 고른다 (APT `_resolveTranslation`과 같은 순서). 예: 방어구의 `+# to Armour` → `3484657501`, 반지의 `+# to Armour` → `809229260`.
   - 고른 뒤에는 **고른 항목 안에서** 같은 골격의 매처를 다시 찾아 그 매처의 `negate`·`value`를 쓴다. 고른 항목에 그 골격의 매처가 없으면 "맞추지 못함" (APT `findAndResolveTranslation`과 같음. 칸마다 매처 목록이 다른 묶음이 있음 — 예: 무기의 "Intimidate Enemies for 4 seconds on Hit"는 `WEAPON` 칸에 매처가 없어 맞추지 못함).
   - `trivial-merge`, `percent-merge`, `flag-merge`: 이번 버전에서는 "맞추지 못함" (회색, 사유 "이번 버전은 미지원 옵션"). 다음 버전 후보.
4. 묶음이 아니면 그 매처의 항목을 쓴다.
5. 고른 항목에서 종류에 맞는 ID를 쓴다: explicit → `explicit.`, implicit → `implicit.`, crafted → `crafted.`, fractured → `fractured.`, enchant → `enchant.`. 그 종류의 ID가 없거나 둘 이상이면 "맞추지 못함". scourge·crucible은 매칭하지 않는다(회색).
6. 같은 골격이 서로 다른 곳 둘 이상(단일 항목끼리, 묶음끼리, 묶음과 단일 항목이 섞인 경우 모두)에 나오면 "맞추지 못함". 임의로 고르지 않는다 (고정 커밋 기준 골격 12,479개 중 26개).
7. 줄에 **부호 반전 여부 = 항목의 `trade.inverted` XOR 매처의 `negate`**를 기록한다.

**부호 반전 줄의 값 보내기:**

화면의 최소·최대값은 **줄에 보이는 문장 그대로의 뜻**(예: "#% reduced X"의 # 값, 양수)으로 입력받는다. 부호 반전 줄은 거래소에 보낼 때 위치를 바꾸고 부호를 뒤집는다 (APT `pathofexile-trade.ts` `getMinMax`와 같은 처리).

| 화면 입력 | 거래소에 보내는 값 |
|---|---|
| 최소 a | 최대 = −a |
| 최대 b | 최소 = −b |
| 둘 다 비움 | 값 없이 stat만 |

예:
- "10% reduced Movement Speed": increased 항목(`inverted` 없음)의 negate 매처 → 반전. 최소 10을 넣으면 `{"max": -10}`.
- "10% reduced Action Speed": `#% increased Action Speed` 항목은 `inverted=true`이고 reduced 매처는 negate가 없음 → 반전. 최소 10을 넣으면 `{"max": -10}`.
- "10% increased Action Speed": `inverted=true`, increased 매처는 `negate=true` → 반전 아님. 그대로 `{"min": 10}`.

반전 아닌 줄은 그대로 보낸다.

**기본 최소값:**

| 줄의 수치 | 기본 최소값 | 기본 최대값 |
|---|---|---|
| 숫자 1개, 0보다 큼 | `floor(값 × 0.9)` (소수 수치는 소수 첫째 자리 버림) | 비움 |
| 숫자 2개 (`Adds # to #` 등) | 거래소 방식대로 두 값의 평균 × 0.9 버림 | 비움 |
| 숫자가 0 이하이거나, 영문 줄에 `reduced` / `less`가 들어 있음 | 비움 (사용자가 직접 입력) | 비움 |
| 숫자 없음 | 비움 (값 없이 stat만 조건) | 비움 |

비율 0.9는 설정값(`settings["trade"]["min_ratio"]`)이다.

### 6.7 거래소 요청 규칙 (게임 위 시세 모드 전용, `api.py`, `ratelimit.py`)

- **User-Agent:** 브라우저로 위장하지 않는다. `ExileDelta-custom/<app/version.py VERSION> (contact: <연락처>)` 형식. 연락처는 설정값 하나에서만 읽고, 비어 있으면 `(contact: …)` 부분을 뺀다.
- **요청 직렬화:** `api.py` 안의 `threading.Lock`으로 거래소 요청은 한 번에 하나만 보낸다. 거래소 창은 요청 중에 검색 버튼을 막는다.
- **요청 순서:** 검색 1회 = `POST /api/trade/search/{league}` 1회 + `GET /api/trade/fetch/{ids}?query={id}` 최대 2회(10개씩, 20개).
- **leagues:** 프로그램 실행 후 **처음 검색 버튼을 누를 때** search 앞에 1회 받고 `%LOCALAPPDATA%\ExileDelta\trade\`(`paths.LOCAL`)에 저장한다. 그 실행 동안은 다시 받지 않는다. 창을 열기만 해서는 받지 않는다. stat 목록은 요청하지 않는다(6.6).
- **제한 상태:** `ratelimit.py`는 응답마다 `X-Rate-Limit-Policy` 이름별로 규칙 상태를 따로 기록한다 (search와 fetch는 다른 정책).
  - 각 규칙 `최대:기간:벌칙`과 상태 `현재:기간:제한중남은초`를 읽는다.
  - 상태의 세 번째 값이 0보다 크면 그 정책의 다음 요청 가능 시각 = 지금 + 그 값.
  - 현재 횟수가 최대에 닿은 규칙이 있으면 그 기간이 지날 때까지 기다린다.
  - 429면 `Retry-After`만큼 막는다.
  - 다음 요청 가능 시각 전에는 요청을 보내지 않고 남은 시간을 돌려준다.
  - 제한 숫자는 코드에 고정하지 않는다.
- **`_note_rate`와의 관계:** 같은 헤더 형식이므로 해석 함수 하나를 `ratelimit.py`에 두고, `importers._note_rate`는 그 함수를 불러 기존 `RL`, `PAUSE_UNTIL` 값을 채우도록 바꾼다 (캐릭터 자동 갱신 동작 동일).
- **오류 분류:** `api.py`는 `TradeError(kind)`만 밖으로 던진다 (`network` / `rate_limited` / `login_required` / `bad_league` / `server`). 메시지는 고정 한글 문구이고, 응답 본문·헤더·쿠키를 넣지 않는다. `run_async`의 `str(e)`로 화면에 가도 안전하다.
- **모드 확인:** `api.py`의 요청 함수는 보내기 직전에 `settings["trade"]["mode"]`가 게임 위 시세 모드이고 `api_ack_at`이 있는지 확인한다. 아니면 요청하지 않고 오류를 낸다.

### 6.8 POESESSID (게임 위 시세 모드 전용)

- 선택 설정. 입력칸은 비밀번호 방식(가려서 표시)이고 브라우저 모드에서는 비활성이다.
- `settings.json`에 넣지 않는다. Windows DPAPI(`CryptProtectData`, ctypes)로 암호화해 `%APPDATA%\ExileDelta\trade_session.bin`에 저장한다. 같은 Windows 사용자만 풀 수 있다. "지우기" 버튼으로 파일을 삭제한다.
- 쿠키는 서버 주소가 정확히 `https://www.pathofexile.com`인 요청에만 붙인다. 카카오 서버 요청에는 보내지 않는다.
- 로그, `last_item.txt`, 오류 문구, 화면 어디에도 값이 나오지 않는다. 브라우저 링크에도 넣지 않는다.
- 쿠키 없이 401·403을 받으면 "로그인이 필요할 수 있습니다. 거래소 설정에서 POESESSID를 넣어 주세요" 문구를 보여 준다.

### 6.9 설정 저장

`settings["trade"]` = `{mode, api_ack_at, server, league, min_ratio, hotkey_enabled, window, contact}`.

- `mode` 기본값은 `"browser"`. 값이 없거나 알 수 없는 값이면 브라우저 모드로 본다. `"api"`인데 `api_ack_at`이 없으면 브라우저 모드로 본다.
- 바꿀 때마다 `load_settings()` → `trade` 키만 바꿈 → `save_settings()`로 바로 저장한다. `main.py closeEvent`의 일괄 저장 목록에는 넣지 않는다.

## 7. 규칙 준수

**공통:**

- 매크로 규칙: 단축키는 사용자가 직접 누를 때만 동작하고, 게임에 `Ctrl+C`(클라이언트 안 복사, 서버 동작 아님) 1회만 보낸다.
- 오버레이 규칙: 클립보드는 단축키 한 번에 한 번만 읽는다.
- 게임 파일·메모리를 건드리지 않는다.

**브라우저 모드:** 프로그램은 거래소에 어떤 요청도 보내지 않는다. 공개 웹페이지 링크를 사용자의 브라우저로 열 뿐이다.

**게임 위 시세 모드:**

- GGG 개발자 문서에 없는 내부 API를 쓴다. 문서상 약관 7i 위반이며, 이 사실을 4.6 위험 안내로 사용자에게 알리고 확인을 받은 뒤에만 켠다.
- 위험을 줄이는 장치: 검색 버튼 1회 = search 1 + fetch 최대 2 (프로그램 실행 후 첫 검색에만 leagues 1 추가), 창 열기·단축키만으로는 요청 없음, 자동 반복 없음, 요청 제한 헤더를 항상 따르고 숫자를 고정하지 않음, 동시 요청 없음, 프로그램 이름을 밝히는 User-Agent, stat 목록 요청 없음.

## 8. 선행 조건 (별도 작업 FIX-001)

`app/app_update.py:31` `REPO = "KyungseokKANG/exile-delta"` 때문에 원본 릴리스가 나오면 커스텀 코드가 원본 코드로 바뀐다.
FEAT-001을 실행 파일로 배포하기 전에 자동 업데이트를 끄거나 머성 저장소로 바꾸는 FIX-001이 먼저 필요하다. 개발 모드(`python app\main.py`) 실행과 테스트에는 영향이 없다.

## 9. 완료 기준

1. 영문·한글 클라이언트의 레어·유니크 장비 샘플마다 만든 검색 JSON이 정답 파일과 같다 (이름/베이스, 체크한 옵션의 stat ID와 최소값, 링크, 타락, 판매 상태 `securable`). 두 모드 모두 검색 JSON의 판매 상태는 항상 `securable`이다.
2. 같은 샘플마다 만든 브라우저 링크가 정답 링크와 같다 (공식·카카오). 리그 칸이 비거나 링크가 2,000자를 넘으면 링크를 만들거나 열지 않고 버튼이 막히며 이유가 표시된다.
3. 지원하지 않는 아이템(마법, 화폐, 젬, 미확인)은 검색 버튼 없이 안내만 나온다.
4. 거래소 stat과 맞추지 못한 줄, 후보가 여럿인 줄, value 고정 매처 줄, `trivial-merge`·`percent-merge`·`flag-merge` 묶음 줄, scourge·crucible 줄은 검색에 들어가지 않고 회색으로 표시된다. `select` 묶음 줄은 아이템 종류에 맞는 ID가 들어간다(같은 문장이 방어구와 반지에서 다른 ID). 부호 반전 줄(`inverted` XOR `negate`)은 6.6 표대로 최소·최대가 바뀌고 부호가 뒤집혀 들어간다.
5. **브라우저 모드에서는 거래소 창 열기부터 "브라우저로 검색"까지 거래소 관련 HTTP 요청이 0회이고, `trade.api` 모듈이 로드되지 않는다.** 게임 위 시세 모드에서도 창 열기만으로는 요청이 없고, leagues는 실행 후 첫 검색 때만 받는다. 두 모드 모두 `/api/trade/data/stats`를 요청하지 않는다. (업데이트 확인·캐릭터 자동 갱신 등 기존 기능의 요청은 이 기준과 무관하다.)
6. 설정 기본값은 브라우저 모드다. 게임 위 시세 모드는 위험 안내 창에서 "위험을 이해하고 사용"을 눌러야만 켜지고, 취소하면 브라우저 모드로 남는다. `api_ack_at` 없이 `mode`만 `"api"`인 설정은 브라우저 모드로 동작한다.
7. 게임 위 시세 모드로 실제 공식 거래소에 검색하면 가격순 결과와 요약이 창에 나오고, "거래소에서 열기"가 같은 검색을 연다.
8. 요청 제한 헤더 샘플로 정책별 대기 시간이 계산되고, 대기 중에는 요청을 보내지 않는다. 동시에 두 요청이 나가지 않는다.
9. `Ctrl+D`는 PoE 창이 앞일 때만 등록된다. 기존 `Ctrl+C` → 옵션변경 창 동작, 지도 `Ctrl+C` → 지도 경고 창 동작(포커스 가져오기·Esc로 게임에 돌려주기 포함), 캐릭터 자동 갱신 동작은 그대로다. 클립보드가 늦게 와도(빈 값 재시도) `Ctrl+D` 복사분은 거래소 창으로 간다.
10. POESESSID가 `settings.json`, 로그 폴더, `last_item.txt`, `TradeError` 문구, 화면, 브라우저 링크 어디에도 평문으로 남지 않고, 카카오 서버 요청에 붙지 않는다.
11. `data/trade_stats.json`에 출처 커밋 해시가 기록되어 있고, `data/LICENSE-awakened-poe-trade.txt`와 README 출처 표기가 있다.

## 10. 테스트 계획

- **도구:** `requirements-dev.txt`에 `pytest`. `tests/conftest.py`가 `app/`을 `sys.path` 앞에 넣어 앱 코드의 import 방식(`from itemmodel import …`)과 맞춘다. 실행: 저장소 루트에서 `python -m pytest tests`.
- **격리 (머성 PC의 실제 설정·세션 파일 보호):** `paths.ROAMING`/`LOCAL`은 import 때 `APPDATA`/`LOCALAPPDATA`로 정해진다 (`app/paths.py:38-39`, `storage.SETTINGS_FILE`). 그래서 `conftest.py`는 **앱 모듈을 하나라도 import하기 전에** 두 환경변수를 테스트 세션 전용 임시 폴더로 바꾼다. `settings.json`, `trade_session.bin`, 로그·캐시는 모두 그 임시 폴더에만 생긴다. **테스트는 임시 폴더 밖에 아무것도 쓰지 않는다. 저장소의 `tools/.cache`(`dict_builder.CACHE`, `app/dict_builder.py:16`)와 `data/`도 여기에 포함된다.**
- **번역 사전 고정:** 위 격리로 `%APPDATA%\ExileDelta\data`의 자동 갱신본이 보이지 않으므로, `data.resource_path`는 저장소의 `data/*.json`만 쓴다. `conftest.py`는 임시 `ROAMING\data` 폴더가 비어 있는지 확인해, 비어 있지 않으면 테스트를 실패시킨다.
- **네트워크 차단:** `conftest.py`가 `requests.Session.request`와 `socket.socket.connect`를 호출되면 실패하도록 바꾼다. 게임 위 시세 모드 테스트만 가짜 응답을 주입한다. 완료 기준 5는 브라우저 모드 흐름 전체(창 조건 → 링크 생성 → `openUrl` 호출을 가로챔)를 이 상태에서 돌리고, 끝에 `sys.modules`에 `trade.api`가 없는지 확인한다. 게임 위 시세 모드는 창 열기 후 요청 0회, 첫 검색에 leagues 1 + search 1 + fetch, 두 번째 검색에 leagues 없음을 가짜 응답의 호출 기록으로 검사한다.
- **회귀 검사:** `map_warn.py`·`item_editor.py`가 `winutil`의 5개 함수를 가져오는지 import 테스트 1개.
- **테스트 자료 (`tests/trade/fixtures/`):**
  - 아이템 텍스트: 영문 레어, 한글 레어, 영문 유니크, 한글 유니크, 지원하지 않는 아이템(마법·화폐).
  - 정답 JSON: 아이템 텍스트마다 기대 검색 JSON 1개. 정답 링크: 같은 샘플의 공식·카카오.
  - 링크 경계: 리그 빈칸 1건, 2,000자 초과 1건(옵션을 많이 켠 레어). 실제 샘플로 2,000자를 넘기지 못하면 그 테스트 안에서만 `browser.MAX_URL_LEN`을 작은 값으로 바꿔 경계(기준 이하는 열림, 초과는 막힘)를 검사한다.
  - 부호 샘플: negate만 있는 줄("reduced Movement Speed" 등), `inverted` 항목의 두 매처("increased/reduced Action Speed" 등)를 각각 1개 이상 (화면 최소·최대 → 거래소 값 변환 확인).
  - `select` 묶음 샘플: 같은 문장(`+# to Armour` 등)이 방어구와 반지에서 서로 다른 ID로 들어가는지, 무기의 `#% increased Attack Speed`가 `WEAPON` 칸 ID로 들어가는지.
  - 미지원 묶음 샘플: `trivial-merge` 등 묶음 줄이 회색으로 빠지는지 1개.
  - 요청 제한 헤더 샘플: 정상, 한도 도달, 제한 중(State 세 번째 값 > 0), 429 + `Retry-After`. search·fetch 정책 각각.
  - 결과 JSON 샘플: fetch 응답 → 화면 행.
  - stat 매칭은 저장소의 `data/trade_stats.json`을 그대로 쓴다. 같은 문장이 전역·Local로 나뉘는 줄(`select` 묶음)을 샘플에 하나 이상 넣는다.
- **단위 테스트:** 완료 기준 1~6, 8, 10, 11. 6은 위험 안내 창의 확인/취소와 `mode`·`api_ack_at` 조합별 실제 동작 모드. 10은 가짜 POESESSID 값으로 `TradeError` 문구, 저장된 `settings.json`, 로그 폴더 파일, 브라우저 링크에 그 값이 없는지, 카카오 서버 요청 헤더에 쿠키가 없는지 검사한다. `importers._note_rate`는 기존과 같은 `RL`/`PAUSE_UNTIL` 값을 채우는지 검사한다.
- **실제 거래소 확인 (개발 세션, 게임 위 시세 모드, 요청 최소화):** 공식 서버 search 1회 + fetch. 카카오 서버 한글 이름 search 1회(6.4 확인). 그 밖의 실제 요청은 하지 않는다.
- **`dict_builder` 회귀 (`flatten`):** `flatten` 기본값 호출은 지금과 같이 묶음을 펼친 목록, `flatten=False`는 원래 줄(`resolve` 포함)을 돌려주는지. 아래와 같은 임시 캐시 방식으로 검사한다.
- **`dict_builder` 회귀:** 테스트 시작 때 `dict_builder.CACHE`를 테스트 임시 폴더로 바꾸고(`app/updater.py:224`가 이미 쓰는 방식), 끝나면 원래 값으로 되돌린다. 그 임시 캐시에 가짜 캐시 파일을 미리 두고 네트워크 없이, `apt_ndjson` 기본 인자 호출이 기존과 같은 캐시 파일 이름을 쓰고 다른 `base`는 다른 캐시 파일 이름을 쓰는지 검사한다. 저장소의 `tools/.cache`에는 파일을 만들거나 바꾸지 않는다 (가짜 파일이 남으면 `download()`가 다시 받지 않아 `build_names.py`·`build_trade_stats.py`가 그것으로 실제 데이터를 만들게 됨).
- **머성 확인 목록 (개발 세션이 작성):** 단축키가 PoE 앞일 때만 동작하는지, 창 위치·포커스·Esc 닫기, 기존 `Ctrl+C` 동작 유지, 브라우저 링크가 조건이 채워진 검색을 여는지(공식·카카오), 테스트 샘플 중 가장 긴 링크(길이 함께 표기)가 잘리지 않고 열리는지, 게임 위 시세 모드 위험 안내 창.

## 11. 머성 확인 필요

| 항목 | 현재 적용 |
|---|---|
| 검색 서버 | 공식 해외 거래소 기본 (한글 클라이언트는 설정에서 카카오로 변경 가능) |
| 단축키 | `Ctrl+D` |
| User-Agent 연락처 | 비어 있음 (설정에서 입력, 게임 위 시세 모드에서만 쓰임) |
| 자동 업데이트(FIX-001) | 미정: 끄기 vs 머성 GitHub 저장소로 바꾸기 |
