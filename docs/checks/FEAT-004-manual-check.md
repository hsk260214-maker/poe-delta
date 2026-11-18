# FEAT-004 지역 레벨 확인

공식 거래소 Standard에서 `Blueprint: Mansion`, `securable`, `nonunique`, `map_filters.filters.area_level` 83~83으로 search 1회와 fetch 1회를 실행했다. 검색은 1,871개를 반환했고, 받아 온 10개 모두 `properties`의 `Area Level`이 83이었다. 그중 아이템 레벨(`ilvl`)이 84인 매물도 2개였으므로 아이템 레벨과 혼동하지 않았다. 이 결과는 도면에만 적용하며, 계약은 이번 요청으로 확인하지 않았다.

머성 확인: [카카오 Standard — 도면: 대저택, 지역 레벨 83~83][blueprint]. 검색 화면에서 가판대·고유 제외·지역 레벨 83~83을 확인하고, 매물 상세의 **지역 레벨**이 83인지 확인한다. 아이템 레벨은 다른 값이어도 된다. 매물이 없거나 보안 확인 등으로 확인할 수 없으면 미확인으로 남긴다. 구역 수와 인챈트 조건은 지역 레벨 확인을 위해 이 링크에 넣지 않았다.

2026-11-18 머성이 위 카카오 도면 링크로 확인했고 통과했다. `AREA_BROWSER_VERIFIED`에 `BLUEPRINT`를 반영했다.

2026-11-18 공식 거래소 Standard에서 `Contract: Bunker`, `securable`, `nonunique`, 지역 레벨 83~83으로 search 1회와 fetch 1회를 실행했다. 검색 응답의 `total`은 10,000이었고, 상세 조회 10개 모두 `properties`의 `Area Level`이 83이었다. `ilvl`은 83~86이었다. `AREA_API_VERIFIED`에 `CONTRACT`를 반영했으며, 계약의 지역 레벨 조건은 카카오 확인 전까지 비활성이다.

머성 확인: [카카오 Standard — 계약: 벙커, 지역 레벨 83~83][contract]. 도면과 같은 기준으로 확인한다. 이 링크에는 지역 레벨 검증과 관계없는 직업·목표물 조건을 넣지 않았다.

[contract]: https://poe.kakaogames.com/trade/search/Standard?q=%7B%22query%22%3A%7B%22status%22%3A%7B%22option%22%3A%22securable%22%7D%2C%22type%22%3A%22%EA%B3%84%EC%95%BD%3A%20%EB%B2%99%EC%BB%A4%22%2C%22stats%22%3A%5B%7B%22type%22%3A%22and%22%2C%22filters%22%3A%5B%5D%7D%5D%2C%22filters%22%3A%7B%22type_filters%22%3A%7B%22filters%22%3A%7B%22rarity%22%3A%7B%22option%22%3A%22nonunique%22%7D%7D%7D%2C%22map_filters%22%3A%7B%22filters%22%3A%7B%22area_level%22%3A%7B%22min%22%3A83%2C%22max%22%3A83%7D%7D%7D%7D%7D%2C%22sort%22%3A%7B%22price%22%3A%22asc%22%7D%7D

[blueprint]: https://poe.kakaogames.com/trade/search/Standard?q=%7B%22query%22%3A%7B%22status%22%3A%7B%22option%22%3A%22securable%22%7D%2C%22type%22%3A%22%EB%8F%84%EB%A9%B4%3A%20%EB%8C%80%EC%A0%80%ED%83%9D%22%2C%22stats%22%3A%5B%7B%22type%22%3A%22and%22%2C%22filters%22%3A%5B%5D%7D%5D%2C%22filters%22%3A%7B%22type_filters%22%3A%7B%22filters%22%3A%7B%22rarity%22%3A%7B%22option%22%3A%22nonunique%22%7D%7D%7D%2C%22map_filters%22%3A%7B%22filters%22%3A%7B%22area_level%22%3A%7B%22min%22%3A83%2C%22max%22%3A83%7D%7D%7D%7D%7D%2C%22sort%22%3A%7B%22price%22%3A%22asc%22%7D%7D
