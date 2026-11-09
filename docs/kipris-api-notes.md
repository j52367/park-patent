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
| 서지 상세 `kipo-api/kipi/patUtiModInfoSearchSevice/getBibliographyDetailInfoSearch` (`applicationNumber`, `ServiceKey`) | ✅ | 2026-11-09 | 호출 1회에 청구항 전문, 청구항 수, 우선권, 심사관 인용문헌(`priorArtDocumentsInfo`, `examinerQuotationFlag`), 법적상태 이력, 패밀리, R&D 과제. 삭제된 청구항은 '삭제'로 옴 |
| 피인용 `openapi/rest/CitingService/citingInfo` (`standardCitationApplicationNumber`, `accessKey`) | ✅ | 2026-11-09 | 성공해도 `resultCode`가 **빈 값**. `<citingInfo>`마다 인용한 출원번호와 인용 종류 |
| 패밀리 (서지 상세의 `familyInfoArray`) | ⚠️ | 2026-11-09 | 표본에서 대부분 비어 있음. 해외 패밀리는 '특허 패밀리' 서비스 확인 필요 |
| 호출 한도 | ✅ (FAQ) | KIPRIS Plus FAQ | 무료 월 1,000회 *호출* |
| `resultCode=31` `DEADLINE_HAS_EXPIRED_ERROR` | ✅ | 2026-11-09 실제 호출 | 키의 활용 기간 만료. `openapi/rest/...?accessKey=`와 `kipo-api/kipi/...?ServiceKey=` 두 경로 모두 같은 응답 → 경로 문제 아님. KIPRIS Plus 마이페이지에서 기간을 연장해야 한다 |
| 신 경로 `kipo-api/kipi/patUtiModInfoSearchSevice/getWordSearch` (`word`, `numOfRows`, `pageNo`, `ServiceKey`) | ⚠️ | 2026-11-09 | 키가 인식됨(만료 응답). 정상 응답 형식은 연장 후 확인 |
