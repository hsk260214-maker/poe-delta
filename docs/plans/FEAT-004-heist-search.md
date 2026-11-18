# FEAT-004 강탈 계약·도면 거래소 검색

- 상태: 기획 v2 — 기획 리뷰 2/3 APPROVED. 개발 순서: FEAT-003B → FEAT-003 후속 범위 → FEAT-004

## 0. v1 → v2 변경

| 리뷰 지적 | 결정 | 위치 |
|---|---|---|
| 1 구역 수 "정확값 = APT와 같음"이 틀림 (APT는 min만) | 우리 결정으로 정확값(min = max)을 기본으로 채움. APT와 다르다는 점과 의도를 명시. 사용자가 최대값을 지우면 APT와 같은 "이상" 검색 | 3.2, 5·6절 |
| 2 계약·도면의 검색 정체성(type / category / 등급) 미정 | 계약: 카테고리 기본 + 베이스 버튼(FEAT-003 후속 규칙과 같음). 도면: 정확 베이스 기본(APT와 같음) + 버튼으로 카테고리 전환. 둘 다 `nonunique`(APT와 같음). 선행에 FEAT-003 후속 범위 추가 | 1절 선행, 3.0 |
| 3 지역 레벨 게이트에 "실행 중 0개는 정상" 누락 | 3.3과 완료 기준 4에 추가 | 3.3, 5절 |
| 참고: NOT 필터 형식 | APT 형식 `{"id": …, "value": {}, "disabled": false}`로 정답 JSON 고정 | 3.2 |
| 참고: Lockdown 인챈트는 select 묶음 | 도면 종류에서 enchant ID가 나오는지 테스트 자료에 포함 | 6절 |
| 참고: 지원 품목·Item Class 이름 | B 자료나 ko 클라이언트 문자열로 확정 | 3.4 |
- 브랜치: `custom`
- 작성: poe 기획 세션
- 구분: POE Delta 추가 기능
- 참조: Awakened PoE Trade 고정 커밋 `803d188d1359c4d5b1e3826da5dc680ea74a158f` (이하 APT)
- 선행: FEAT-003B의 고정 APT 품목 분류 자료(`items.ndjson`)와 공통 `build_query`, **FEAT-003 후속 범위(장비 종류 기본 검색·베이스 버튼·`nonunique`)**. 기존 미커밋 거래소 기본 설정 변경은 범위 밖.

## 1. 목표

`Ctrl+D`로 강탈 계약·도면을 복사했을 때, 같은 조건의 가판대 매물을 찾는다.

- 계약: 필요 직업과 직업 레벨, 목표물 가치("값을 매길 수 없음")
- 도면: 공개된 구역 수·전체 구역 수, 인챈트 유무, 인챈트 종류
- 공통: 지역 레벨 (출시 전 확인 게이트를 통과한 경우에만)

## 2. 근거 (APT 고정 커밋)

| 조건 | APT 위치 | 거래소 필드 |
|---|---|---|
| 필요 직업 9종 + 레벨 | `filters/pseudo/heist.ts` `applyContractRules`, `trade/pathofexile-trade.ts` L516~547 | `heist_filters.filters.heist_{agility, brute_force, counter_thaumaturgy, deception, demolition, engineering, lockpicking, perception, trap_disarmament}.min/max` (APT 기본 min = 직업 레벨, 범위 검색 없음) |
| 목표물 가치 | `heist.ts`, `pathofexile-trade.ts` L552~554 | `heist_filters.filters.heist_objective_value.option = "priceless"` |
| 공개·전체 구역 | `heist.ts` `applyBlueprintRules`, L555~562 | `heist_filters.filters.heist_wings`, `heist_max_wings` (min/max) |
| 인챈트 없음 | `heist.ts` `applyBlueprintRules` | stat `pseudo.pseudo_number_of_enchant_mods`를 **NOT** 그룹으로 (`statToNotFilter`) |
| 인챈트 종류 | APT stat 매칭 | `enchant.stat_*` (고정 stats에 강탈 관련 enchant 항목 있음, 예: "Heist Targets are always Replica Unique Items", "Rogue Perks are doubled", "#% increased time before Lockdown") |
| 품목 분류 | `pathofexile-trade.ts` L13~55 | `heistmission.contract`, `heistmission.blueprint` (값은 개발 단계에서 고정 표와 대조) |
| 지역 레벨 | `pathofexile-trade.ts` L404~409 `map_filters.filters.area_level` | APT는 강탈 품목에 쓰지 않음 → **근거 없음** |

## 3. 기능 범위

### 3.0 검색 정체성

| 품목 | 기본 검색 | 베이스 버튼 | 등급 조건 | 근거 |
|---|---|---|---|---|
| 계약 | 카테고리 `heistmission.contract`, `type` 없음 | 켜면 정확 베이스(`type`)만 | `nonunique` | APT `create-item-filters.ts` L230~244 (HeistContract는 카테고리 기본 켬), L302~310 |
| 도면 | 정확 베이스(`type`), 카테고리 없음 | 끄면 카테고리 `heistmission.blueprint`, `type` 없음 | `nonunique` | APT (HeistBlueprint는 카테고리 기본 꺼짐) — 도면은 장소(베이스)가 필요 직업·곁보상에 영향을 줌 |

- 계약은 FEAT-003 후속 범위의 "카테고리 기본, 베이스 버튼으로 정확 검색" 규칙과 같다. 도면만 기본이 반대(정확 베이스)이고, 같은 버튼으로 전환한다.
- 등급은 두 검색 범위 모두 `nonunique`로 고정한다 (FEAT-003 후속 범위의 희귀 장비 카테고리 규칙과 같고, 강탈 품목은 정확 베이스에서도 APT처럼 `nonunique`를 붙인다는 점이 장비와 다르다).
- 공식 서버는 영문 정식 베이스, 카카오는 같은 베이스의 정식 한글 이름을 `type`으로 보낸다 (FEAT-003B 자료). 베이스를 확정하지 못하면 검색을 막는다.
- 카테고리 ID는 고정 APT `CATEGORY_TO_TRADE_ID`(L43~44)의 값을 쓴다.

### 3.1 계약

- 복사 텍스트에서 필요 직업과 레벨을 읽는다. 9종 중 하나에 정확히 대응할 때만 조건을 만들고, 기본 체크한다. 최소 = 직업 레벨, 최대는 비움 (APT와 같음, 사용자가 바꿀 수 있음).
- 목표물 가치가 "값을 매길 수 없음"이면 해당 조건을 기본 체크로 표시한다. 아니면 조건을 만들지 않는다.
- 계약의 일반(explicit) 옵션은 기존 stat 매칭과 A의 구역 규칙을 그대로 쓴다.
- 직업 이름을 읽지 못하거나 9종에 대응하지 않으면 그 조건을 회색 처리하고 사유를 보인다. 직업 조건을 빼고 더 넓게 검색하지 않는다 — 검색 버튼을 막는다.

### 3.2 도면

- 공개된 구역 수·전체 구역 수를 각각 조건으로 만들고 기본 체크한다. **기본값은 정확값(min = max = 복사 값)이며, 이것은 APT와 다른 POE Delta의 결정이다.** APT는 min만 보낸다(`heist.ts` `applyBlueprintRules` → `filterFillMinMax`의 PositiveRoll). `1/4` 도면을 `2/4`·`4/4`와 섞지 않고 같은 상태의 도면 시세를 보려는 의도다. 사용자가 최대값 칸을 비우면 APT와 같은 "이상" 검색이 된다.
- 인챈트 줄이 있으면 각 줄을 기존 stat 매칭(종류 `enchant`)으로 맞춰 조건을 만들고 기본 체크한다. 맞추지 못한 인챈트 줄이 있으면 사유를 표시하고 검색을 막는다 (인챈트를 빼고 넓히지 않음).
- 인챈트 줄이 없으면 "인챈트 없음" 조건을 기본 체크로 표시한다. 이 조건은 공통 쿼리의 `stats`에 별도 그룹 `{"type": "not", "filters": [{"id": "pseudo.pseudo_number_of_enchant_mods", "value": {}, "disabled": false}]}`로 넣는다 (APT `tradeIdToQuery` 형식, `pathofexile-trade.ts` L609~613). 정답 JSON도 이 형식으로 고정한다. 체크를 끄면 인챈트 유무와 상관없이 검색한다.
- `pseudo.pseudo_number_of_enchant_mods`는 FEAT-003A의 영향력 pseudo처럼 고정 APT 데이터에서 추출해 예상 ID와 대조하고, 없으면 생성을 멈춘다.

### 3.3 지역 레벨 (게이트)

- 복사 텍스트의 지역 레벨을 표시하고 조건 후보로 만든다.
- **출시 전 확인:** 개발 단계에서 `map_filters.filters.area_level`이 강탈 계약·도면에 실제로 적용되는지 공식 거래소 검색 1회(게임 위 모드) + 브라우저 링크 1회로 확인한다. 결과가 그 지역 레벨로 좁혀지지 않거나 확인할 수 없으면 이 조건을 만들지 않고 "지역 레벨 조건은 아직 지원하지 않습니다"를 표시한다. 나머지 검색은 그대로 가능하다.
- 확인을 통과하면 기본 체크 해제, 최소 = 복사 값.
- **실행 중:** 확인을 통과한 조건으로 검색해 매물이 0개면 기존 "검색 결과 없음"을 표시한다. 막지 않는다 (FEAT-003 v2.2와 같은 게이트 원칙).

### 3.4 공통

- 가판대(`securable`) 전용, 브라우저 모드 HTTP 0회, 게임 위 모드도 검색 버튼 전 요청 0회, 두 모드 같은 쿼리.
- 고유 계약·고유 도면은 APT처럼 위 규칙을 적용하지 않고 기존 고유 이름+베이스 규칙을 따른다.
- 미확인 계약·도면은 검색하지 않는다.
- 한글 머리줄·직업 이름·"값을 매길 수 없음"·구역 문구는 APT 고정 커밋의 ko 클라이언트 문자열과 대조해 정한다. 추측 금지.
- 지원 품목 목록(`query.SUPPORTED`)에 계약·도면을 넣는다. 한·영 Item Class 이름("Heist Contracts"/"Heist Blueprints"와 한글명)은 FEAT-003B 자료나 ko 클라이언트 문자열로 확정한다.
- `Ctrl+D` → 일반 `Ctrl+C` 지도 경고 순서는 바꾸지 않는다.

## 4. 하지 않는 것

강탈 장비(로그 장비)·강탈 목표물 아이템, 계약 직업 범위 검색, 지역 레벨 게이트 미통과 시의 대체 조건, 도면 구역 이름(구역 이름은 최종 보상에 영향 없음, 3.23).

## 5. 완료 기준

1. 한·영 계약(직업별 최소 2종, "값을 매길 수 없음" 있음/없음)의 공통 쿼리에 해당 `heist_filters`가 들어간다.
2. 한·영 도면(인챈트 없음 1, 인챈트 1개 이상 1)의 쿼리에 구역 수 정확값(min = max), 인챈트 `enchant.*` 또는 APT 형식의 NOT `pseudo_number_of_enchant_mods` 그룹이 들어간다. 최대값을 비우면 min만 들어간다.
3. 맞추지 못한 직업·인챈트가 있으면 검색이 막히고 사유가 보인다.
4. 지역 레벨은 게이트 결과대로만 동작한다 (통과: 조건 생성 / 미통과: 안내만 / 통과한 조건의 실행 중 0개: "검색 결과 없음" 표시).
5. 계약은 카테고리 기본(`heistmission.contract`, `type` 없음) + 베이스 버튼으로 정확 베이스, 도면은 정확 베이스 기본 + 버튼으로 카테고리(`heistmission.blueprint`). 두 품목 모두 `nonunique`.
6. 체크 변경만으로 요청 없음, 두 모드 같은 쿼리, `securable` 유지, 기존 테스트 전부 통과.

## 6. 테스트 계획

FEAT-001 격리·네트워크 차단 규칙 그대로. "#% increased time before Lockdown"(select 묶음, test `[null, "HEIST_EQUIPMENT"]`)이 있는 도면에서 enchant ID가 실제로 골라지는지 포함한다 (안 나오면 "맞추지 못함"으로 막히는 것이 정상). 고정 자료: 머성이 게임에서 `Ctrl+C`(가능하면 `Ctrl+Alt+C`)로 복사한 한글 계약·도면 원문 각 1개 이상 + 영문 예시. 원문을 받기 전에는 한글 고정 자료를 만들어 내지 않는다. 실제 요청은 3.3 게이트의 공식 검색 1회와 브라우저 링크 1회뿐이며 횟수와 결과를 개발 보고에 적는다.

## 7. 머성 확인 필요

- 한글 계약·도면 복사 원문 (인챈트 있는 도면 포함)
