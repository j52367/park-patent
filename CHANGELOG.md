# Changelog

## 0.1.0 — 2026-11-11

첫 공개 릴리스.

### 분석 흐름
- 기술 분류표와 검색식 설계 (`/tech-scoping`)
- KIPRIS Plus 검색: 캐시, 월 호출 한도 관리, 한 번에 500건 (`park search`)
- 엑셀/CSV 반입: KIPRIS 웹, WIPS 등 한글 헤더 인식, 다국가 (`park ingest`)
- 관련성 선별: 원문 인용 검증, 분류표 기반 정렬과 판정 학습 정렬 (`park rank --learn`)
- 라운드별 꼬리 표본으로 남은 유효특허와 추정 재현율 계산 (`park audit-sample`)
- 특허맵: 연도별 동향(미공개 구간 표시), 출원인 정규화, 기술분류·국가 매트릭스 (`park map`)
- 보고서: 단일 HTML, 숫자는 자리표시자로만 (`park report --strict`)

### 2단계 분석
- 핵심특허: 청구항·피인용·법적상태 수집, 독립항 기반 판정과 청구항 인용 검증 (`park enrich`, `park merge-review`)
- 특허 기반 SWOT (`park swot`)
- 청구항 대비표: 구성요소 분할, 기준일 이전 선행문헌, 심사관 인용, 명세서 본문 단락 대조 (`park chart --fulltext`)

### 스킬
`park-pipeline`, `tech-scoping`, `kipris-search`, `relevance-screening`, `patent-map`, `park-report`, `key-patent-review`, `ip-strategy`, `claim-chart-kr`

### 검증 강화 (릴리스 전 리뷰 반영)
- 청구항을 번호별로 구조화해 대조. 청구항 본문 속 숫자("설정값 10.")를 청구항 경계로 오인하지 않음
- 핵심특허·대비표 병합 시 검증에 실패한 판정은 결과와 결론에서 제외
- 대비표: 대상 특허 자신, 후보 목록 밖 문헌, 같은 칸 중복 판정을 거부. 선행문헌을 공지 / 확대된 선출원으로 구분
- 꼬리 표본 추정은 표본을 뽑은 모집단에만 적용하고 보류 판정을 노이즈로 세지 않음
- 노이즈 재검토 결과를 `:noise-audit` 태그로 기록하고 `park map`이 노이즈 누락률과 추정 거짓음성률 계산
- 피인용은 고유 출원번호로 세고, 빈 응답 코드는 정상 KIPRIS 응답일 때만 성공으로 처리
- 손으로 고친 구성요소 분할 유지 (`park chart --resplit`으로만 초기화)
- 미공개 구간에 30일 이상 걸친 연도만 미완으로 표시. `--strict`가 "1건씩", "100%" 같은 방법 설명은 허용

### 선택 백엔드
- Codex CLI 병렬 판정 (`scripts/codex-screen.sh`)
