# FIX-001 커스텀판 업데이트·배포 분리

- 상태: 기획 v2 — 개발 완료 (개발 리뷰 2/3 APPROVED). 남은 일: 머성 수동 확인(`docs/checks/FIX-001-manual-check.md`), 커밋·첫 릴리스(머성 요청 때). 저장소는 2026-11-18 공개로 전환됨 → 릴리스가 생기면 친구 PC도 자동 업데이트 가능

## 0. v1 → v2 변경

| 리뷰 지적 | 결정 | 위치 |
|---|---|---|
| 1 단일 실행 키가 원본과 같음 (`app/main.py:495`) | 키를 `DIR_NAME` 기반으로 | 2절, 3.2, 5·6절 |
| 2 `build.ps1` 정리가 다른 폴더의 원본 exe 프로세스를 끌 수 있음 | 정리·종료 대상은 `PoeDelta*`만, 종료는 실행 경로가 이 저장소 `dist\`인 프로세스만 | 3.3, 5절 |
| 3 배포물에 MIT 고지 없음 | `pack_app.py`가 두 LICENSE를 묶고, 첫 설치 zip에도 동봉 | 3.3, 5절 |
| 4 설정 복사 중간 실패 시 반쪽 폴더 고착 | 임시 폴더에 복사를 끝낸 뒤 한 번에 이름 바꾸기 | 3.2, 5·6절 |
| 참고: 복사된 업데이트 상태 키 | 복사 후 `app_update_seen`·`app_update_skip`·`app_updated` 삭제 | 3.2 |
| 참고: origin 비교 방식 | https/ssh, `.git` 유무, 대소문자를 맞춘 뒤 비교 | 3.3 |
| 참고: 비공개 저장소 안내, PoB 엔진 복사 선택지 | 7절에 추가 | 7절 |
| 참고: 로더 오류 창 제목 | `POE Delta 실행 오류`로 함께 바꿈 | 3.2 |
- 브랜치: `custom` (커밋 fa6ec7c 기준, `origin` = hsk260214-maker/poe-delta 비공개, `upstream` = KyungseokKANG/exile-delta 읽기 전용)
- 작성: poe 기획 세션

## 1. 목표

머성 커스텀판(이하 "POE Delta")을 친구에게 줘도:

1. 원작자 릴리스로 덮어써지지 않고, 업데이트는 `hsk260214-maker/poe-delta`에서만 받는다.
2. 같은 PC에 원본 Exile Delta가 있어도 서로의 데이터·받은 코드를 건드리지 않는다.
3. 릴리스 스크립트가 원작자 저장소가 아닌 `poe-delta`로 올린다.

## 2. 문제 (실제 코드 근거)

| 문제 | 위치 | 결과 |
|---|---|---|
| 업데이트 대상이 원작자 저장소 | `app/app_update.py:31` `REPO = "KyungseokKANG/exile-delta"`, L99·L124·L355 | 원작자가 1.0.16을 내면 커스텀판이 원본 코드로 바뀜 (처음 실행이면 묻지도 않고 설치: `StartupUpdater._got`) |
| 단일 실행 키가 원본과 같음 | `app/main.py:495` `key = "ExileDelta-" + md5(APPDATA)`, L496~501 | 원본이 켜져 있으면 POE Delta는 원본 창만 앞으로 띄우고 꺼짐 (반대도 같음) |
| 데이터 폴더 이름이 원본과 같음 | `app/paths.py:15` `DIR_NAME = "ExileDelta"`, `launcher/launcher.py:23` 같은 값 | 원본과 커스텀판이 `%LOCALAPPDATA%\ExileDelta\app\state.json`과 받은 앱 코드를 함께 씀 → 로더가 버전이 더 높은 쪽의 코드를 실행할 수 있음 (`launcher.py` 1번 경로). 설정·캐릭터도 섞임 |
| exe 이름이 원본과 같음 | `build.ps1` 기본 `-Name ExileDelta`, `release.ps1` `ExileDelta-<ver>.zip` | 친구가 어느 프로그램인지 구분 못 함. 빌드 스크립트가 같은 이름의 실행 중 프로세스를 끔 |
| 릴리스 대상 | `release.ps1` `gh release create`(저장소 지정 없음, remote가 2개), 마지막 안내 주소가 원작자 저장소 | 어느 저장소로 올라갈지 gh 판단에 맡겨짐 |
| 버전이 원본과 같음 | `app/version.py` `VERSION = "1.0.15"` | 원본과 구분 안 됨 |
| 비공개 저장소 | GitHub API는 로그인 없는 요청에 비공개 저장소를 404로 답함 | `latest()`는 404 → None이라 "최신 버전입니다"로 잘못 안내, `history()`는 `raise_for_status`로 "내역을 받지 못했습니다" 오류 |

## 3. 바꾸는 것

### 3.1 업데이트 대상 (`app/app_update.py`)

- `REPO = "hsk260214-maker/poe-delta"`. 이 상수 하나만 바꾸고 L99·L124·L355는 그대로 상수를 쓴다. 모듈 설명문의 저장소 주소도 고친다.
- `UA`의 `User-Agent`를 `"PoeDelta-updater"`로.
- 비공개·릴리스 없음(404) 처리:
  - `latest()`: 지금처럼 404 → `None`.
  - `history()`: 404면 오류 대신 빈 목록 → 기존 "아직 올라온 릴리스가 없습니다" 안내로 감.
  - 수동 확인(`StartupUpdater`, `manual=True`)에서 `latest()`가 `None`이면 "최신 버전입니다" 대신 "확인할 수 있는 릴리스가 없습니다 (지금 v<버전>). 저장소가 비공개이거나 아직 릴리스가 없습니다."를 보여 준다. 시작 시 자동 확인과 10분 주기 확인은 지금처럼 조용히 넘어간다.
- 저장소를 나중에 공개로 바꾸면 코드 변경 없이 자동 업데이트가 동작해야 한다.

### 3.2 데이터 폴더 분리 (`app/paths.py`, `launcher/launcher.py`)

- `DIR_NAME = "PoeDelta"` (두 파일 같은 값). `APP_NAME = "POE Delta"` (`paths.py`, 창 제목·상태 표시줄·`setApplicationName`에 쓰임: `app/main.py` L57·L87·L485).
- `OLD_DIR_NAMES` 이름 바꾸기(rename) 규칙은 커스텀판에서 없앤다. 원본 프로그램의 폴더를 옮기면 원본이 망가지기 때문이다.
- **처음 실행 때 원본 설정 복사 (ROAMING만):** `%APPDATA%\PoeDelta`가 없고 `%APPDATA%\ExileDelta`가 있으면 원본 폴더 전체(설정·등록 캐릭터·필터 탭·번역 사전 갱신본)를 복사한다. 원본 폴더는 읽기만 하고 바꾸지 않는다.
  1. `%APPDATA%\PoeDelta.partial-<pid>`에 복사한다.
  2. 복사한 `settings.json`에서 `app_update_seen`, `app_update_skip`, `app_updated` 키를 지운다 (원본의 업데이트 상태를 가져오지 않음. 커스텀판 첫 실행은 "처음 실행" 규칙대로 동작).
  3. 끝나면 `os.rename`으로 `PoeDelta`로 한 번에 바꾼다. 그래서 **`PoeDelta`가 있으면 복사가 끝난 것**이 보장된다.
  4. 1~3 중 하나라도 실패하면 임시 폴더를 지워 보고(실패해도 무시), **이번 실행의 ROAMING은 `PoeDelta`가 아닌 이번 실행 전용 임시 폴더**(`%TEMP%\PoeDelta-session-<pid>`)로 한다. 그래서 `PoeDelta`가 생기지 않고 다음 실행에 다시 복사를 시도한다. 이번 실행에서 바꾼 설정은 남지 않는다. 창이 뜬 뒤 상태 표시줄에 "원본 설정을 가져오지 못했습니다. 다음 실행 때 다시 시도합니다"를 한 번 보여 준다.
  5. 시작할 때 남아 있는 `PoeDelta.partial-*` 폴더는 지워 본다 (실패해도 무시, 사용하지 않음).
  - 복사는 `PoeDelta`가 **없을 때만** 한다. `ExileDelta`도 없으면 복사 없이 `PoeDelta`를 새로 쓴다.
  - **동시 실행 경합:** `main.py`는 단일 실행 검사(L495)보다 먼저 `paths`를 import한다(L8). 그래서 두 프로세스가 동시에 복사할 수 있다. 3번의 `os.rename`이 "`PoeDelta`가 이미 있음"으로 실패하면 실패로 보지 않는다. 다른 쪽이 복사를 끝낸 것이므로 `PoeDelta`를 쓰고 자기 partial 폴더만 지운다 (늦은 쪽은 곧 단일 실행 검사로 꺼짐). PoB 워커 같은 하위 프로세스도 `paths`를 import하므로 같은 규칙을 따른다.
- **LOCAL은 복사하지 않는다:** `%LOCALAPPDATA%\PoeDelta`는 새로 시작한다. PoB 엔진(약 370MB)은 처음 실행 때 한 번 다시 받는다. 원본의 받은 앱 코드·state.json을 가져오면 2절의 섞임 문제가 그대로 생기기 때문이다.
- `launcher._local_dir()`는 `paths.py`와 같은 규칙(이름 `PoeDelta`, rename 없음, LOCAL 복사 없음)으로 맞춘다. `launcher._error_box`의 창 제목도 `"POE Delta 실행 오류"`로 바꾼다 (L152).
- **단일 실행 키:** `app/main.py:495`의 키 접두를 `paths.DIR_NAME`으로 만든다 (`f"{DIR_NAME}-" + md5(APPDATA)…` → `"PoeDelta-…"`). 원본(`ExileDelta-…`)과 서로의 실행을 막지 않는다. 같은 POE Delta를 두 번 켜면 지금처럼 기존 창만 앞으로 나온다.

### 3.3 빌드·릴리스 (`build.ps1`, `release.ps1`)

- `build.ps1`:
  - 기본 `-Name PoeDelta`. 작업 폴더 이름 `exiledelta_build` → `poedelta_build`.
  - **프로세스 종료는 실행 경로가 이 저장소 `dist\` 안의 그 exe인 것만** 한다 (1단계의 `$exe` 종료, 예전 빌드 정리 모두. `Get-Process`의 `Path`를 그 파일의 전체 경로와 비교). 다른 폴더에서 실행 중인 원본 Exile Delta나 다른 POE Delta는 끄지 않는다.
  - 예전 빌드 정리 대상은 `dist\PoeDelta*.exe`/`.zip` 중 지금 이름(`$name`)이 아닌 것만이다. `ExileDelta*`/`ExileSieve*`는 커스텀판 정리 대상에서 뺀다 (남아 있으면 그대로 둠).
- `tools/pack_app.py`: `files()`에 저장소 루트 `LICENSE`(원본 MIT, zip 안 경로 `LICENSE`)와 `data/LICENSE-awakened-poe-trade.txt`를 더한다. 그래서 exe 안 기본 코드(appsrc)와 `app-<ver>.zip` 모두에 두 고지가 들어간다. `manifest.json` 형식은 바꾸지 않는다.
- `release.ps1`:
  - `build.ps1 -Name PoeDelta`, 처음 설치용 zip `PoeDelta-<ver>.zip`, 릴리스 제목 `POE Delta v<ver>`.
  - 처음 설치용 zip에 exe와 함께 `LICENSE`, `LICENSE-awakened-poe-trade.txt` 두 파일을 넣는다.
  - `gh release create`에 `--repo hsk260214-maker/poe-delta`를 붙인다.
  - `git push`는 `origin`(= poe-delta) 그대로. 맨 처음(빌드 전)에 `git remote get-url origin`을 확인한다. 비교 전에 `git@github.com:` → `https://github.com/`, 끝의 `.git`과 `/` 제거, 소문자로 맞추고 `https://github.com/hsk260214-maker/poe-delta`와 같지 않으면 아무것도 하지 않고 멈춘다.
  - 마지막 안내 주소를 `https://github.com/hsk260214-maker/poe-delta/releases/tag/$tag`로.
  - 파일은 ASCII만 쓴다는 기존 규칙(PowerShell 5.1)을 지킨다.

### 3.4 버전 (`app/version.py`)

- `VERSION = "1.1.0"` (커스텀판 첫 버전. 원본 1.0.x와 구분). `MIN_LOADER = 1`, `launcher.LOADER_VERSION = 1` 그대로.

## 4. 하지 않는 것

원본 설정 복사가 매번 실패하는 경우의 탈출 방법(다음 버전 후보: 예를 들어 "원본 설정 없이 새로 시작" 버튼), `release.ps1`의 `git add -A`가 추적하지 않는 파일까지 릴리스 커밋에 넣는 기존 동작(실제 릴리스 전에 머성에게 알림), 실제 릴리스 올리기(머성 요청 때만), 저장소 공개 전환, 비공개 저장소용 로그인 업데이트, README 고치기(원본과 충돌 방지), 화면 문구의 "Exile Delta" 일괄 변경(`APP_NAME`을 쓰는 곳만 바뀜), PoB 엔진 업데이터(`app/updater.py`, PoB 공식 저장소) 변경, 원본 폴더 삭제·이동.

## 5. 완료 기준

1. 업데이트 확인·내역·"새 설치 파일 필요" 페이지가 모두 `hsk260214-maker/poe-delta`를 본다. 코드 어디에도 `KyungseokKANG/exile-delta`를 업데이트 대상으로 쓰는 곳이 없다 (출처 설명은 예외).
2. 404 응답에서 `latest()`는 `None`, `history()`는 빈 목록이고, 수동 확인은 3.1의 안내 문구를 보여 준다. 자동 확인은 아무 창도 띄우지 않는다.
3. `%APPDATA%\ExileDelta`만 있는 상태에서 처음 실행하면 `%APPDATA%\PoeDelta`에 같은 내용이 복사되고(설정의 업데이트 상태 키 3개는 빠짐), `ExileDelta`는 파일 하나도 바뀌지 않는다. `PoeDelta`가 이미 있으면 복사하지 않는다. 복사 중 실패하면 `PoeDelta`가 생기지 않고 다음 실행에 다시 복사된다. `%LOCALAPPDATA%\ExileDelta`는 읽지도 바꾸지도 않는다. `ExileSieve` 폴더도 이름을 바꾸지 않는다.
4. `paths.LOCAL`과 `launcher._local_dir()`가 같은 `%LOCALAPPDATA%\PoeDelta`를 가리킨다.
5. 단일 실행 키가 `PoeDelta-`로 시작하고, 원본의 `ExileDelta-` 키와 다르다.
6. `build.ps1 -NoRun`으로 `dist\PoeDelta.exe`, `dist\app-1.1.0.zip`, `dist\manifest.json`(version 1.1.0)이 만들어지고, `app-1.1.0.zip` 안에 `app/trade/`, `data/trade_stats.json`, `LICENSE`, `data/LICENSE-awakened-poe-trade.txt`가 들어 있다. `build.ps1`의 프로세스 종료는 `dist\` 안 실행 경로인 것만 대상이다.
7. `release.ps1`은 `origin`이 poe-delta가 아니면(https·ssh 형식 모두) 빌드 전에 멈추고, 첫 설치 zip에 exe와 두 LICENSE가 들어가며, `gh release create`가 `--repo hsk260214-maker/poe-delta`로 불린다 (실제 릴리스는 만들지 않고 스크립트 내용과 origin 비교 함수 단위 확인으로 검증).
8. FEAT-001 테스트를 포함한 기존 테스트가 모두 통과한다.

## 6. 테스트 계획

- 단위 테스트 (FEAT-001의 `tests/conftest.py` 격리·네트워크 차단 그대로):
  - `app_update`: 가짜 응답으로 요청 주소가 `REPO` 기반인지, 404에서 `latest()`=None·`history()`=[]인지, 수동 확인 안내 문구.
  - `paths`: 임시 `APPDATA`/`LOCALAPPDATA`에서 검사한다. `paths`는 import 때 경로가 정해지므로 모듈을 다시 불러와 검사한다.
    - `ExileDelta`만 둔 경우: 복사됨, 업데이트 상태 키 3개 빠짐, 원본 불변(파일 목록과 내용 해시 비교).
    - `PoeDelta`가 이미 있는 경우: 복사 안 함.
    - 복사 중 실패(복사 함수를 실패하게 바꿈): `PoeDelta` 없음, 원본 불변, 이번 ROAMING은 이번 실행 전용 임시 폴더. 다음 import에서 다시 복사되어 `PoeDelta` 생김.
    - `PoeDelta.partial-*`가 남아 있는 경우: 사용하지 않고, 지우기에 실패해도 시작은 됨.
    - `ExileSieve`가 있어도 이름이 바뀌지 않음.
  - `launcher._local_dir()`: 같은 임시 환경에서 `paths.LOCAL`과 같은 경로, rename 없음.
  - 단일 실행 키: 키 만드는 부분을 함수로 떼어 `PoeDelta-`로 시작하는지 검사.
  - `pack_app.files()`: 두 LICENSE가 들어 있는지.
  - `release.ps1`의 origin 비교: https, https+`.git`, ssh, 대소문자 다른 경우 통과 / 원작자 저장소·다른 저장소는 멈춤. PowerShell 함수로 떼어 두고 개발 세션이 그 함수만 따로 불러 확인한다 (빌드·push·릴리스는 실행하지 않음).
- 빌드 확인 (개발 세션): scratch 가상환경에서 `build.ps1 -NoRun` 1회, 완료 기준 6의 산출물 확인. 만든 exe는 실행하지 않는다 (창이 뜨므로 머성 확인 목록으로).
- 머성 확인 목록: `PoeDelta.exe`를 켰을 때 창 제목 "POE Delta v1.1.0", 기존 캐릭터·설정이 보이는지, 원본 Exile Delta를 켜도 원래대로인지, 메뉴 "프로그램 업데이트 확인"의 안내 문구.

## 7. 머성 확인 필요

| 항목 | 기본안 |
|---|---|
| 프로그램 이름 | 창 제목·exe 모두 "POE Delta" / `PoeDelta.exe` |
| 원본 설정 가져오기 | 처음 실행 때 설정·캐릭터만 복사, PoB 엔진은 다시 받음(약 370MB, 한 번). 다른 안: `%LOCALAPPDATA%\ExileDelta\pob\`만 추가로 복사(`app\`·`state.json`은 제외)해 재다운로드를 피함 |
| 첫 버전 번호 | 1.1.0 |

**머성께 알릴 점:** 저장소가 비공개인 동안 친구 PC는 자동 업데이트를 받을 수 없다 (로그인 없는 요청은 404). "새 설치 파일 필요" 안내에서 열리는 릴리스 페이지도 친구에게는 404다. 친구에게는 새 `PoeDelta-<ver>.zip`을 직접 전달해야 한다.
