---
name: ip-strategy
description: "Phase 2: patent-based SWOT and portfolio strategy for a focal applicant against chosen competitors — counts by technology code, growth, key patents and forward citations from park swot, then SWOT.md with numbers only via {{swot...}} placeholders. Use when the user says \"SWOT\", \"특허 전략\", \"포트폴리오 강화\", \"경쟁사 비교\", \"출원 전략\" or after key-patent-review."
argument-hint: "[analysis 폴더] [— focal:<출원인>] [— vs:<경쟁 출원인들>]"
allowed-tools: Read, Write, Edit, Glob, Bash(park *), Bash(python -m park *)
---

# 특허 기반 SWOT·전략

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다. 특허 데이터로 말할 수 있는 것과 없는 것을 구분하는 것이 이 스킬의 핵심이다.

## 1. 집계

```bash
park swot <DIR> --focal "<초점 출원인>" --vs "<경쟁1>,<경쟁2>,<경쟁3>,<경쟁4>"
```

- 출원인 이름은 보고서에 나온 표시명 그대로 쓴다.
- 경쟁 출원인은 출원 건수 상위와 핵심특허 보유를 보고 고른 뒤 사용자에게 확인받는다.
- 결과:
  - `swot_stats.json`: 기술분류별 성장(최근 구간 대 이전 구간), 출원인별 분류 분포, 등록 비율, 핵심·주목 특허 수, 평균 피인용
  - `map/swot_matrix.svg`
- `hints`의 S·W·O·T 후보는 **규칙으로 뽑은 후보**다. 그대로 옮기지 말고 핵심특허 판정과 함께 검토한다.

## 2. SWOT.md 쓰기

구성:

1. **강점(S):** 초점 출원인의 비중이 높은 분류, 핵심특허를 가진 분류
2. **약점(W):** 성장하는 분류인데 출원이 거의 없는 곳, 등록 비율이 낮은 분류
3. **기회(O):** 성장하는데 아직 지배적 출원인이 없는 분류 (최상위 출원인 비중이 낮음)
4. **위협(T):** 경쟁 출원인이 건수나 핵심특허에서 크게 앞선 분류
5. **전략 제안:** 3–5개. 항목마다 근거(위 S·W·O·T)와 실행 형태(출원 방향, 공동연구, 회피설계 검토, 라이선스 검토 등)를 적는다.

규칙:

- **숫자는 `{{swot...}}` 자리표시자로만 쓴다.** 예:
  - `{{swot.applicants.0.n}}`, `{{swot.applicants.0.alive_rate|pct}}`
  - `{{swot.codes.3.growth}}`, `{{swot.hints.S.0.focal}}`
  - 인덱스는 `swot_stats.json`의 배열 순서다. 직접 쓴 숫자는 `park report --strict`가 막는다.
- O·T는 **특허 측면의 기회·위협**만 쓴다. 시장 규모, 매출, 정책 같은 사업 정보는 사용자가 준 자료가 있을 때만 쓰고, 그 출처를 적는다. 없으면 "사업 정보 없음"으로 둔다.
- "공백기술", "침해 위험 없음" 같은 단정은 쓰지 않는다. 검색 범위(KR) 밖은 모른다.
- 평균 피인용은 압축 목록에 든 문헌만으로 계산한 값이다. 이 점을 함께 적는다.

## 3. 보고서

```bash
park report <DIR> --strict
```

보고서에 "SWOT · 특허 전략" 절이 붙는다. 출원인 × 기술분류 매트릭스가 함께 실린다.
