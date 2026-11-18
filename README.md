# POE Delta — Exile Delta 커스텀판

이 저장소는 **[KyungseokKANG/exile-delta](https://github.com/KyungseokKANG/exile-delta)**(Exile Delta, MIT 라이선스)를 바탕으로 [hsk260214-maker](https://github.com/hsk260214-maker)가 기능을 더한 커스텀판 **POE Delta**입니다.

**Exile Delta 자체와 그 기능, 이 문서 아래쪽의 "원본 Exile Delta 설명"은 모두 원작자 [KyungseokKANG](https://github.com/KyungseokKANG)이 만들고 쓴 것입니다.** POE Delta에서 더하거나 바꾼 것은 아래 표의 "POE Delta" 줄뿐입니다.

설치와 사용법: **[docs/INSTALL.md](docs/INSTALL.md)** · 받을 파일: [Releases](https://github.com/hsk260214-maker/poe-delta/releases/latest)의 `PoeDelta-버전.zip`

## 원본 기능과 POE Delta 변경 구분

| 구분 | 내용 | 만든 사람 |
|---|---|---|
| **원본 Exile Delta 기능** | 템 비교(`Ctrl+C`로 DPS·EHP·최대 피격 변화, "왜 이렇게 바뀌나", 옵션변경 창), 한글 클라이언트 지원, 캐릭터 불러오기·자동 갱신, 장비·주얼 기여도, 젬, 패시브 트리, 아이템 만들기, 최적 옵션 추천(베타), 지도 위험 옵션 경고, 아이템 필터, PoB 엔진 연동, 코드만 받는 자동 업데이트 구조 | KyungseokKANG |
| **POE Delta 추가 기능** | 거래소 시세 검색(`Ctrl+D`): 조건 창, 브라우저 모드·게임 위 시세 모드, 가판대(즉시 구매) 매물만 검색, 카카오 거래소 선택 | hsk260214-maker |
| **POE Delta 변경 사항** | 업데이트 받는 곳을 이 저장소로 변경, 프로그램 이름(`PoeDelta.exe`)·데이터 폴더(`%APPDATA%\PoeDelta`, `%LOCALAPPDATA%\PoeDelta`) 분리와 원본 설정 복사, 빌드·릴리스 스크립트 대상 변경, 원본 함수 일부를 공용 모듈(`app/winutil.py`, `app/ratelimit.py`)로 옮김(동작 동일), 테스트(`tests/`)와 문서(`docs/`) 추가 | hsk260214-maker |

- **코드로 확인하기:** 커밋 기록에서 `Release v1.0.15`(`4fa6d68`)까지는 원작자의 커밋이고, 그 뒤 `FEAT-001`부터가 POE Delta 변경입니다. 원본 대비 바뀐 내용 전체는 [4fa6d68...custom 비교](https://github.com/hsk260214-maker/poe-delta/compare/4fa6d68...custom)에서 볼 수 있습니다.
- **POE Delta가 더 쓰는 외부 자료:** [Awakened PoE Trade](https://github.com/SnosMe/awakened-poe-trade)(MIT)의 오프라인 거래소 stat 데이터 (고정 커밋 `803d188d1359c4d5b1e3826da5dc680ea74a158f`, `data/LICENSE-awakened-poe-trade.txt`)
- **라이선스:** 원본의 MIT 라이선스(`LICENSE`, Copyright (c) 2026 KyungseokKANG)를 그대로 따릅니다.
- **문의:** POE Delta에서 생긴 문제는 원작자가 아닌 이 저장소의 [Issues](https://github.com/hsk260214-maker/poe-delta/issues)로 알려 주세요.

---

> 아래부터는 **원본 Exile Delta의 README 원문**입니다 (작성: KyungseokKANG, 내용 수정 없음). 원문의 파일·폴더 이름(`ExileDelta.exe`, `%APPDATA%\ExileDelta` 등)과 "이 저장소" 같은 표현은 원본 저장소 기준입니다.

# Exile Delta

POE1 하다가 템 하나 주울 때마다 PoB 켜서 붙여넣고 비교하는 게 너무 귀찮아서 만든 프로그램입니다.

게임에서 아이템에 마우스 올리고 `Ctrl+C` 누르면, 그 템을 지금 내 캐릭터에 꼈을 때 DPS, EHP, 최대 피격이 얼마나 바뀌는지 게임 화면 위에 바로 띄워 줍니다.
계산은 Path of Building(PoB) 원본 코드를 그대로 돌려서 하기 때문에 PoB에서 직접 비교한 것과 숫자가 똑같이 나옵니다.
한글 클라이언트에서 복사한 템도 알아서 영문으로 바꿔서 계산해요.

> For English speakers: a Windows tool for Path of Exile 1. Press `Ctrl+C` on an item in game and it shows how your DPS / EHP / max hit would change, using the real Path of Building engine. Works with the Korean client too.

## 뭘 할 수 있나

**템 비교 (게임에서 Ctrl+C)**
- 게임 위에 작은 창이 떠요. 포커스를 안 가져가서 그대로 다른 템에 계속 Ctrl+C 하면 됩니다.
- 반지처럼 낄 자리가 여러 개면 자리마다 Full DPS / EHP / 최대 피격(물리, 화염, 냉기, 번개, 카오스) 변화를 따로 보여 줘요.
- 저항이 상한 밑으로 떨어지거나 힘/민/지 요구치가 모자라면 경고가 뜹니다.
- RF(정의의 화염) 같은 지속 피해를 뺀 실제 체젠도 같이 나와요.
- "ⓘ 왜 이렇게 바뀌나?" 버튼에 마우스를 올리면 요약이, 누르면 옵션 한 줄 한 줄이 DPS/EHP에 얼마나 영향을 줬는지 나옵니다.
- 옵션을 끄거나 수치를 바꾸거나, 총주교/포식자/타락 implicit을 붙여 보면서 바로 다시 계산할 수 있어요.

**캐릭터**
- pathofexile.com 계정 이름이나 PoB 코드/링크로 캐릭터를 불러옵니다.
- "1분마다 갱신"을 켜 두면 레벨업, 장비 교체, 패시브 찍은 게 알아서 반영돼요. 사이트 요청 제한에 안 걸리게 알아서 조절합니다.
- 젬 켜고 끄기, Full DPS 체크, 주 스킬, 계산 설정, 플라스크 같은 건 다시 불러와도 그대로 남아요.
- 장비/주얼별 기여도, 젬 레벨/퀄 올렸을 때 효과, 패시브 트리 보기와 찍어 보기, 아이템 만들기, 슬롯별 최적 옵션 추천(베타)도 있습니다.

## 설치

1. [Releases](../../releases/latest)에서 `ExileDelta-버전.zip`을 받아서 아무 폴더에 풀어 주세요.
2. `ExileDelta.exe`를 실행합니다.
   서명 안 된 프로그램이라 처음에 Windows가 "PC 보호" 경고를 띄울 수 있는데, **추가 정보 → 실행** 누르면 됩니다.
3. 처음 켜면 두 가지를 알아서 받아요.
   - 이 저장소에 더 새 버전이 올라와 있으면 그걸 받고 다시 켜집니다.
   - 계산에 쓰는 PoB 엔진(약 370MB)을 PoB 공식 GitHub에서 받습니다. 처음 한 번만 받아요.
4. 캐릭터 화면에서 `+` 눌러서 캐릭터를 등록하세요.
   계정으로 불러오려면 pathofexile.com 프로필 → Privacy Settings에서 Characters 탭을 공개로 해 둬야 합니다.
5. 게임은 **창 모드 전체 화면(Windowed Fullscreen)** 으로 해 주세요. 그래야 비교 창이 게임 위에 보여요.

## 업데이트는 어떻게 되나

exe를 매번 새로 받을 필요 없게 만들어 놨습니다.

프로그램을 켤 때마다 이 저장소의 최신 릴리스를 확인하고, 새 버전이 있으면 그동안 바뀐 내용을 보여 주면서 업데이트할지 물어봐요.
여러 버전이 밀려 있으면(예: 1.0.0 쓰는데 1.0.3까지 나옴) 1.0.1, 1.0.2, 1.0.3 내용을 다 보여 줍니다.
"지금 업데이트"를 누르면 몇 초 만에 받아서 다시 켜지고, "이 버전 건너뛰기"를 누르면 다음 버전이 나올 때까지 안 물어봐요.

메뉴(☰) → "프로그램 업데이트 확인"으로 직접 확인할 수도 있고, 지난 업데이트 내용은 메뉴의 "업데이트 내역 보기"나 아래 상태 표시줄의 버전 글씨를 누르면 볼 수 있습니다.

### 릴리스에 올라가는 파일

릴리스 하나에 파일이 세 개씩 올라갑니다. 사람이 받을 건 첫 번째 하나뿐이에요.

| 파일 | 크기 | 용도 |
|---|---|---|
| `ExileDelta-버전.zip` | 약 53MB | **처음 설치할 때 받는 파일.** 안에 `ExileDelta.exe` 하나 들어 있어요. 파이썬, Qt 같은 실행에 필요한 것과 그 버전의 프로그램 코드가 전부 들어 있습니다. |
| `app-버전.zip` | 약 1.4MB | 업데이트할 때 프로그램이 알아서 받는 파일이에요. 프로그램 코드(`app/`)와 옵션/번역 데이터(`data/`)만 들어 있습니다. 직접 받을 필요 없어요. |
| `manifest.json` | 1KB 미만 | "최신 버전은 몇이고, 코드 파일은 이거고, 정상 파일이면 지문(SHA-256)이 이거다"라는 정보예요. 프로그램이 업데이트 확인할 때 읽습니다. |

### 업데이트할 때 실제로 일어나는 일

1. 켜지면 `manifest.json`을 읽어서 지금 버전보다 새 게 있는지 봅니다. 시험판(Pre-release)으로 올린 버전은 무시해요.
2. 업데이트를 누르면 53MB짜리 exe가 아니라 `app-버전.zip`(1~2MB)만 받습니다.
3. 받은 파일 지문이 `manifest.json`에 적힌 거랑 다르면 깨진 파일로 보고 설치 안 합니다.
4. `%LOCALAPPDATA%\ExileDelta\app\버전\`에 풀고 프로그램을 다시 켭니다.
5. exe는 그대로 두고, 켜질 때 그 폴더에 있는 새 코드로 실행돼요. 그래서 exe는 일종의 실행기 역할만 합니다.

혹시 새 버전이 켜지다가 계속 죽으면(3번 연속으로 정상 시작을 못 하면) 그 버전은 고장 난 걸로 표시하고 알아서 이전 버전으로 돌아갑니다.
이전 버전 폴더는 하나씩 남겨 두고, 그보다 오래된 건 지워요.

### exe를 새로 받아야 하는 경우

대부분은 코드만 바꿔서 업데이트되지만, 새 라이브러리를 넣거나 파이썬 버전을 올리는 것처럼 exe 자체가 바뀌어야 하는 경우가 가끔 있어요.
그럴 땐 업데이트 창 대신 "새 설치 파일이 필요합니다"가 뜨고, 누르면 다운로드 페이지가 열립니다. 새 `ExileDelta-버전.zip`을 받아서 덮어쓰면 돼요. 설정이랑 캐릭터는 그대로 남습니다.

## 파일이 어디 저장되나

- 설정, 등록한 캐릭터: `%APPDATA%\ExileDelta\`
- PoB 엔진, 받은 업데이트, 로그: `%LOCALAPPDATA%\ExileDelta\`

프로그램이 접속하는 곳은 pathofexile.com(캐릭터 정보), github.com(PoB 엔진, 프로그램 업데이트), repoe-fork.github.io(번역 데이터)뿐이에요. 다른 데로 개인 정보를 보내지 않습니다.

예전 이름(Exile Sieve)으로 쓰던 분은 새 버전을 처음 켤 때 예전 폴더가 자동으로 옮겨져요. 예전 프로그램은 꺼 두고 켜 주세요.

## 직접 빌드하기

```powershell
python -m pip install -r requirements.txt
python app\main.py                                          # 개발 모드로 바로 실행
powershell -ExecutionPolicy Bypass -File .\build.ps1 -NoRun  # dist\ExileDelta.exe 만들기
```

- Windows 10/11, Python 3.12에서 만들고 있어요.
- `app/`이 화면이랑 기능(PySide6), `app/pob/`이 PoB 엔진 연결 부분입니다. PoB의 Lua 코드를 lupa(LuaJIT)로 화면 없이 돌리고, 계산은 별도 프로세스에서 해요.
- exe의 시작점은 `launcher/launcher.py`예요. 앱 코드는 exe에 컴파일해 넣지 않고 파일로 읽어서 돌립니다. 그래야 업데이트로 받은 코드가 쓰이거든요. `tools/pack_app.py`가 `app-버전.zip`이랑 `manifest.json`을 만들고, 업데이트 처리는 `app/app_update.py`에 있습니다.
- 옵션/번역 데이터(`data/*.json`)는 `build.ps1 -RefreshData`로 다시 만들 수 있어요.
- 릴리스 낼 때는 `app/version.py`의 버전을 올리고 `release.ps1 -NotesFile 변경내용.md`를 돌리면 빌드부터 GitHub 업로드까지 한 번에 됩니다. `-Pre`를 붙이면 시험판으로 올라가서 자동 업데이트 대상에서 빠져요.

## 고마운 프로젝트들

- [Path of Building Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding) (MIT): DPS/EHP 계산은 전부 이걸로 합니다. 프로그램에 넣어서 배포하지 않고, 실행할 때 공식 릴리스를 받아서 써요.
- [RePoE fork](https://repoe-fork.github.io/): 아이템 옵션, 영문/한글 문장 데이터
- [Awakened PoE Trade](https://github.com/SnosMe/awakened-poe-trade) (MIT): 한글 클라이언트 문장이랑 이름 데이터 보충
- [PySide6](https://doc.qt.io/qtforpython/), [lupa](https://github.com/scoder/lupa), [requests](https://github.com/psf/requests)

## 라이선스

[MIT](LICENSE)입니다. 마음대로 쓰고 고치고 배포하셔도 돼요.

## 알림

**이 프로그램은 Grinding Gear Games와 아무 관련이 없고, Grinding Gear Games가 승인하거나 보증한 것도 아닌 개인이 만든 팬 도구입니다.**
Path of Exile과 관련 이름, 데이터의 권리는 Grinding Gear Games에 있어요.

*This product isn't affiliated with or endorsed by Grinding Gear Games in any way.*
