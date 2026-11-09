# KIPRIS Plus API 확인 메모

실제 호출로 확인한 것만 ✅로 적습니다. 새로 확인하면 날짜와 함께 추가해 주세요.

| 서비스 / 항목 | 상태 | 확인 일자 · 출처 | 메모 |
|---|---|---|---|
| `patUtiModInfoSearchSevice/freeSearchInfo` | ✅ | 2025 학기 프로젝트 노트북 | `Sevice` 오타가 실제 경로 |
| 파라미터 `word`, `docsStart`, `docsCount`, `accessKey` | ✅ | 같음 | `docsStart`는 1부터 시작하는 순번으로 사용 (start = page×100+1). 연도별 최대 4,792건까지 정상 수집 |
| `docsCount=100` | ✅ | 같음 | 최댓값은 미확인 (30–500으로 알려짐) |
| 응답 `resultCode`=`00`, `TotalSearchCount`, `<PatentUtilityInfo>` | ✅ | 같음 | |
| 항목 태그 `ApplicationNumber`, `InventionName`, `Abstract`, `Applicant`, `InternationalpatentclassificationNumber`, `ApplicationDate`, `RegistrationDate`, `RegistrationStatus` | ✅ | 같음 | 출원인·IPC는 `\|`로 구분 |
| 공개일 태그 (`OpeningDate`?) | ⚠️ | — | park/kipris.py에서 두 이름을 모두 시도 |
| 검색식 `IPC=[..]`, `AD=[a~b]`, `*` | ✅ | 같음 | 나머지 문법은 skills/shared-references/kipris-query-syntax.md |
| 상세 API (서지 상세) | ❌ | 같음 | 노트북에서 404가 나서 제외했다는 기록 |
| `patFamilyInfoService/getFamilySearch` | ⚠️ | 같음 | 노트북에서 대체 라벨로 넘어간 흔적. 응답 형식 미확인 |
| 청구항 전문, 인용·피인용 | ⚠️ | — | 2단계·3단계 전에 확인 필요 |
| 호출 한도 | ✅ (FAQ) | KIPRIS Plus FAQ | 무료 월 1,000회 *호출* |
| `resultCode=31` `DEADLINE_HAS_EXPIRED_ERROR` | ✅ | 2026-11-09 실제 호출 | 키의 활용 기간 만료. `openapi/rest/...?accessKey=`와 `kipo-api/kipi/...?ServiceKey=` 두 경로 모두 같은 응답 → 경로 문제 아님. KIPRIS Plus 마이페이지에서 기간을 연장해야 한다 |
| 신 경로 `kipo-api/kipi/patUtiModInfoSearchSevice/getWordSearch` (`word`, `numOfRows`, `pageNo`, `ServiceKey`) | ⚠️ | 2026-11-09 | 키가 인식됨(만료 응답). 정상 응답 형식은 연장 후 확인 |
