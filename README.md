# POE Delta — Exile Delta 커스텀판

**POE Delta는 [KyungseokKANG](https://github.com/KyungseokKANG)이 만든 [Exile Delta](https://github.com/KyungseokKANG/exile-delta)를 바탕으로 한 커스텀판입니다.**

- 템 비교(DPS·EHP), 캐릭터 불러오기, 패시브 트리, 젬, 지도 경고, 자동 업데이트 구조 같은 **프로그램의 핵심 기능은 모두 원작자 KyungseokKANG이 만들었습니다.**
- 이 저장소([hsk260214-maker](https://github.com/hsk260214-maker))는 여기에 **거래소 시세 검색(`Ctrl+D`) 기능을 추가**했습니다. 그 밖에는 배포에 필요한 이름·업데이트 경로 분리와 작은 편의 기능만 바꿨습니다.
- 원본 저장소: **https://github.com/KyungseokKANG/exile-delta** (MIT 라이선스)

설치와 사용법은 **[docs/INSTALL.md](docs/INSTALL.md)**에 있습니다. 받을 파일은 [Releases](https://github.com/hsk260214-maker/poe-delta/releases/latest)의 `PoeDelta-버전.zip`입니다.

## 한눈에 보기

| 구분 | 내용 | 만든 사람 |
|---|---|---|
| **원본 기능** | 템 비교, 한글 클라이언트 지원, 캐릭터 불러오기·자동 갱신, 장비·젬·패시브·아이템 도구, 지도 위험 옵션 경고, 아이템 필터, PoB 엔진 연동, 코드만 받는 자동 업데이트 구조 | 원작자 KyungseokKANG |
| **추가 기능** | 거래소 시세 검색 (`Ctrl+D`) | hsk260214-maker |
| 작은 추가·변경 | 캐릭터 가져오기 창의 리그별 보기, 프로그램 이름·데이터 폴더·업데이트 받는 곳을 원본과 분리 | hsk260214-maker |

원본과 이 저장소의 차이는 커밋 기록에서도 확인할 수 있습니다. `Release v1.0.15`(`4fa6d68`)까지는 원작자의 커밋이고, 그 뒤부터가 POE Delta의 변경입니다. 바뀐 내용 전체는 [4fa6d68...custom 비교](https://github.com/hsk260214-maker/poe-delta/compare/4fa6d68...custom)에서 볼 수 있습니다.

## POE Delta에서 추가한 것 (hsk260214-maker)

### 거래소 시세 검색 (`Ctrl+D`)

- 게임에서 아이템에 마우스를 올리고 `Ctrl+D`를 누르면 검색 조건 창이 뜹니다. PoE 창이 앞에 있을 때만 동작합니다.
- 옵션마다 켜고 끄거나 최소·최대값을 바꿀 수 있고, 최소값은 실제 수치의 90%로 미리 채워집니다.
- 가판대(즉시 구매) 매물만 검색합니다.
- 창 위쪽에 **실제 검색 대상**(정확한 베이스 또는 `반지 전체` 같은 종류)을 크게 보여 주고, 버튼으로 정확한 베이스와 종류 전체를 바꿀 수 있습니다. 희귀 아이템의 임의 이름처럼 검색에 쓰지 않는 이름은 따로 표시합니다.
- 옵션은 게임 툴팁 순서대로 보이고, 고정·일반·제작·분열·인챈트가 바뀌는 곳에 구분선이 있습니다. 전체 선택·전체 해제를 쓸 수 있습니다.
- **총 원소 저항:** 화염·냉기·번개 저항을 합산해 검색합니다(모든 원소 저항은 3배). 기본은 총합이고 `줄마다 검색`으로 바꿀 수 있습니다. 카오스 저항은 따로 검색합니다.
- 지원 품목: 장비(일반·마법·희귀·고유)와 주얼, 플라스크, 젬(레벨·퀄리티), 지도(등급·정복자·엘더·쉐이퍼 영향, 악몽·바알 사원·쉐이퍼 수호자 지도, 몬스터 레벨), 강탈 계약·도면, 금지된 책, 3.30 살덩이(하위·상위·여왕 단계). 아이템 레벨이 있으면 아이템 레벨 조건도 고를 수 있습니다.
- 변동 옵션 고유 아이템: 운명의 속박은 붙은 옵션 3개를, 어둠의 국왕은 소환수 종류(현재 살아 있는 번개)를 기본 조건으로 검색합니다.
- 거래소 조건과 확실히 맞출 수 없거나 카카오 거래소에서 아직 확인하지 않은 옵션은 회색으로 표시하고 검색에서 뺍니다.
- 검색 방식은 두 가지입니다.
  - **게임 위 시세 모드:** 가격이 싼 순서로 매물 20개와 요약을 게임 위 창에 보여 줍니다.
  - **브라우저 모드:** 조건이 채워진 거래소 페이지를 브라우저로 엽니다.
- 공식 거래소와 카카오 거래소(한글 클라이언트)를 고를 수 있습니다.

### 작은 추가·변경

- **리그별 캐릭터 보기:** 캐릭터 가져오기 창에서 계정에 있는 리그만 단추로 보여 주고, 고른 리그를 기억합니다. 원본의 캐릭터 가져오기 창에 단추를 덧붙인 것입니다.
- **원본과 분리:** 프로그램 이름(`PoeDelta.exe`), 데이터 폴더(`%APPDATA%\PoeDelta`, `%LOCALAPPDATA%\PoeDelta`), 업데이트 받는 곳(이 저장소)을 원본과 나눠서, 원본 Exile Delta와 함께 설치해도 서로 영향을 주지 않습니다.
- 원본 함수 일부를 공용 모듈(`app/winutil.py`, `app/ratelimit.py`)로 옮겼습니다(동작은 같음). 테스트(`tests/`)와 문서(`docs/`)를 추가했습니다.

## 원본 Exile Delta 기능 (원작자: KyungseokKANG)

> 이 절의 기능은 **모두 원작자 KyungseokKANG이 만든 것**입니다. 설명은 [원본 README](https://github.com/KyungseokKANG/exile-delta#readme)의 내용을 기능별로 다시 정리한 것입니다. 원문은 원본 저장소에서 볼 수 있습니다.

원작자가 이 프로그램을 만든 이유는 이렇습니다. "POE1 하다가 템 하나 주울 때마다 PoB 켜서 붙여넣고 비교하는 게 너무 귀찮아서 만든 프로그램입니다."

### 템 비교 (`Ctrl+C`)

- 게임에서 아이템에 마우스를 올리고 `Ctrl+C`를 누르면, 그 템을 지금 캐릭터에 꼈을 때 DPS·EHP·최대 피격이 얼마나 바뀌는지 게임 위에 보여 줍니다.
- 계산은 Path of Building(PoB) 원본 코드를 그대로 돌려서 하므로 PoB에서 직접 비교한 것과 숫자가 같습니다.
- 게임 포커스를 가져가지 않아서 다른 템에 계속 `Ctrl+C`를 할 수 있습니다.
- 반지처럼 낄 자리가 여러 개면 자리마다 Full DPS, EHP, 최대 피격(물리·화염·냉기·번개·카오스) 변화를 따로 보여 줍니다.
- 저항이 상한 밑으로 떨어지거나 힘·민첩·지능 요구치가 모자라면 경고합니다.
- 정의의 화염 같은 지속 피해를 뺀 실제 생명력 재생도 보여 줍니다.
- "왜 이렇게 바뀌나?"에서 옵션 한 줄 한 줄이 DPS·EHP에 준 영향을 보여 줍니다.
- 옵션을 끄거나 수치를 바꾸거나 총주교·포식자·타락 고정 옵션을 붙여 보면서 바로 다시 계산할 수 있습니다.

### 한글 클라이언트 지원

- 한글 클라이언트에서 복사한 아이템을 영문으로 바꿔서 계산합니다.
- 스킬·소환수 이름과 PoB 계산 설정 항목을 한글로 표시합니다.

### 캐릭터 불러오기·관리

- pathofexile.com 계정 이름이나 PoB 코드·링크로 캐릭터를 불러옵니다.
- "1분마다 갱신"을 켜 두면 레벨업, 장비 교체, 패시브 변경이 자동으로 반영됩니다. 사이트 요청 제한에 걸리지 않게 알아서 조절합니다.
- 젬 켜고 끄기, Full DPS 체크, 주 스킬, 계산 설정, 플라스크 설정은 다시 불러와도 그대로 남습니다.

### 장비·젬·패시브·아이템 도구

- 장착 장비·주얼마다 기여도를 보여 주고, 빼거나 다른 장비로 바꿔 볼 수 있습니다.
- 젬 레벨·퀄리티를 올렸을 때의 효과를 보여 줍니다.
- 패시브 트리를 보고 노드를 찍거나 빼면서 DPS·EHP 변화를 확인할 수 있습니다.
- 아이템 만들기(유니크, 베이스에 옵션 붙이기, 텍스트 붙여넣기)를 지원합니다.
- 슬롯별 최적 옵션 추천(베타)이 있습니다.

### 지도 위험 옵션 경고

- 피하고 싶은 지도 옵션을 골라 두면, 지도에 `Ctrl+C`했을 때 그 옵션이 있는지 알려 줍니다.

### 아이템 필터

- 검색 조건을 탭으로 저장해 두고 아이템을 판정하는 화면이 있습니다.

### 코드만 받는 자동 업데이트 구조

- 프로그램을 켤 때 GitHub 최신 릴리스를 확인하고, 실행 파일(exe) 대신 코드 묶음(1~2MB)만 받아 업데이트합니다.
- 받은 파일의 지문(SHA-256)이 맞지 않으면 설치하지 않습니다.
- 새 버전이 3번 연속 정상 시작에 실패하면 이전 버전으로 돌아갑니다.
- 계산에 쓰는 PoB 엔진(약 370MB)은 처음 실행 때 PoB 공식 GitHub에서 한 번 받고, 새 버전은 스스로 점검한 뒤 바꿉니다.
- POE Delta는 이 구조를 그대로 쓰고, **받는 곳만 이 저장소로 바꿨습니다.**

### 프로그램 구조와 빌드

- `app/`은 화면과 기능(PySide6), `app/pob/`은 PoB 엔진 연결 부분입니다. PoB의 Lua 코드를 lupa(LuaJIT)로 화면 없이 돌리고, 계산은 별도 프로세스에서 합니다.
- 실행 파일의 시작점은 `launcher/launcher.py`입니다. 앱 코드는 실행 파일 안에 컴파일하지 않고 파일로 읽어서, 업데이트로 받은 코드가 쓰이게 합니다.
- 이 저장소에서 빌드하는 방법은 아래와 같습니다. 빌드·릴리스 스크립트는 원작자가 만들었고, POE Delta는 이름과 올리는 곳만 바꿨습니다.

```powershell
python -m pip install -r requirements.txt
python app\main.py                                          # 개발 모드로 바로 실행
powershell -ExecutionPolicy Bypass -File .\build.ps1 -NoRun  # dist\PoeDelta.exe 만들기
python -m pip install -r requirements-dev.txt; python -m pytest tests   # 테스트 (POE Delta에서 추가)
```

## 레퍼런스

### 바탕이 된 프로그램

- **Exile Delta** — https://github.com/KyungseokKANG/exile-delta (원작자 KyungseokKANG, MIT). POE Delta는 이 저장소의 v1.0.15(`4fa6d68`)에서 갈라져 나왔습니다.

### 원본 Exile Delta가 쓰는 프로젝트 (원본 README의 "고마운 프로젝트들")

- [Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding) (MIT): DPS·EHP 계산 전부. 프로그램에 넣어 배포하지 않고, 실행할 때 공식 릴리스를 받아서 씁니다.
- [RePoE fork](https://repoe-fork.github.io/): 아이템 옵션, 영문·한글 문장 데이터
- [PySide6](https://doc.qt.io/qtforpython/), [lupa](https://github.com/scoder/lupa), [requests](https://github.com/psf/requests)

### POE Delta의 거래소 검색에서 쓰거나 참고한 것

- 거래소 및 번역 데이터의 출처와 고지는 [제3자 자료 고지](docs/THIRD_PARTY_NOTICES.md)에 있습니다.
- **3.30 살덩이 단계 자료:** [PoEDB 살덩이 목록](https://poedb.tw/kr/Viscera)의 단계별 공식 거래소 링크(이름·부위·거래소 ID·범위)를 `tools/build_viscera.py`로 정리한 `data/viscera.json`
- **이름이 바뀐 한글 옵션 대응표:** 카카오 거래소에서 확인한 항목만 `data/ko_aliases.json`에 기록합니다(예: `지역에 허상 등장`).
- 기능 아이디어만 참고하고 코드는 가져오지 않은 프로그램:
  - [PoE Overlay Community Fork](https://github.com/PoE-Overlay-Community/PoE-Overlay-Community-Fork): 거래소 결과 요약, 클릭으로 조건 켜고 끄기
  - [PoeTradeSearch](https://github.com/phiDelPark/PoeTradeSearch) (phiDelPark): 한글 거래소 검색 방식
  - [Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding): 검색 조건을 거래소 링크(`/trade/search/{리그}?q=…`)로 여는 방식

## 라이선스

- 원본 Exile Delta의 [MIT 라이선스](LICENSE)(Copyright (c) 2026 KyungseokKANG)를 그대로 따릅니다.
- POE Delta에서 생긴 문제는 원작자가 아니라 이 저장소의 [Issues](https://github.com/hsk260214-maker/poe-delta/issues)로 알려 주세요.

## 알림

**이 프로그램은 Grinding Gear Games와 아무 관련이 없고, Grinding Gear Games가 승인하거나 보증한 것도 아닌 개인이 만든 팬 도구입니다.** Path of Exile과 관련 이름, 데이터의 권리는 Grinding Gear Games에 있습니다.

*This product isn't affiliated with or endorsed by Grinding Gear Games in any way.*
