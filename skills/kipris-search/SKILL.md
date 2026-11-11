---
name: kipris-search
description: "Run KIPRIS Plus searches (cached, call-budgeted) or import KIPRIS/other DB CSV/Excel exports into candidates.csv, logging scope in SEARCH_LOG.md. Use when the user says \"키프리스 검색\", \"KIPRIS\", \"특허 검색해줘\", \"엑셀 불러와\", \"CSV 반입\", or as step 2 of park-pipeline."
argument-hint: "[analysis 폴더] [검색식 또는 파일 경로]"
allowed-tools: Read, Write, Edit, Glob, Bash(park *), Bash(python -m park *)
---

# 후보 문헌 수집

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`와 `../shared-references/kipris-query-syntax.md`를 읽는다.

## 경로 A: CSV·엑셀 반입 (API 키 불필요)

KIPRIS 웹 다운로드, WIPS ON 같은 상용 DB 엑셀 모두 된다. `국가코드` 열이 있으면 여러 나라 문헌이 함께 들어오고, `독립청구항`·`출원인 대표명화`·`출원인 국적` 열도 자동으로 쓴다.

```bash
park ingest <파일들> --out <DIR> --as-of <상태 조회일 YYYY-MM-DD> --show-mapping
```

- `--show-mapping` 출력에서 출원번호, 명칭, 요약, 출원인, IPC, 출원일, 상태가 인식됐는지 본다. 빠진 열이 있으면 사용자에게 알리고, 헤더 이름을 알려 주면 `park/ingest.py`의 `HEADER_SYNONYMS`에 추가하자고 제안한다.
- `--as-of`는 파일을 내려받은 날(=권리 상태를 관측한 날)이다. 모르면 비워 둔다. 보고서에 "권리 상태 조회일 미상"으로 표시된다. `park map --as-of`(미공개 구간의 기준일)와는 다른 값이다.
- PARK가 만든 candidates.csv를 다시 반입하면 `status_as_of`와 `source`가 그대로 유지된다. `--as-of`를 주면 그 값으로 덮어쓴다.
- 반입 기록은 `SEARCH_LOG.md`에 자동으로 붙는다. 그 파일을 반입할 때 쓴 **검색식, DB, 기간**은 도구가 모르므로 사용자에게 물어서 직접 적는다.

## 경로 B: KIPRIS Plus API

1. `park quota` — 남은 호출 수 확인.
2. `QUERIES.md`의 검색식마다 **건수만 먼저** 본다: `park search --word "<식>" --count-only --out <DIR>` (호출 1회, candidates.csv는 그대로).
3. 건수와 필요한 호출 수(건수 ÷ 100)를 표로 보여 주고, 총 호출 수가 남은 한도의 30%를 넘으면 범위를 좁힐지 사용자와 정한다.
4. 수집: `park search --word "<식>" --max <N> --out <DIR> --budget <호출 상한>`.
   같은 검색은 캐시에서 읽으므로 다시 실행해도 호출이 늘지 않는다. `--budget`은 실제 네트워크 호출만 센다.
   캐시에서 읽은 문헌의 `status_as_of`는 처음 받은 날짜로 남는다. 상태가 오래됐으면 사용자에게 알린다.
5. 오류가 나면 메시지(resultCode)를 그대로 보여 준다. 문법 오류로 보이면 `kipris-query-syntax.md`의 ⚠️ 항목부터 의심한다.

## 공통: 재현율 점검과 보고

- `QUERIES.md`나 `BRIEF.md`에 적힌 알려진 핵심특허의 출원번호가 `candidates.csv`에 있는지 Grep으로 확인한다. 빠졌으면 원인을 추정하고 검색식 수정을 제안한다.
- 알려진 핵심특허가 하나도 없으면 점검을 건너뛰지 말고 "재현율 점검 불가 (알려진 핵심특허 없음)"라고 보고한다. 이 경우 선별 단계의 꼬리 표본과 노이즈 재검토가 재현율의 유일한 근거가 된다.
- `SEARCH_LOG.md` 맨 위의 데이터베이스·국가·기간·검색 시각을 채운다.
- 보고: 검색식별 전체 건수와 수집 건수, 중복 제거 후 후보 수, 사용한 호출 수, 재현율 점검 결과.
