---
name: park-report
description: "Write the interpretation (REPORT_NOTES.md, numbers only via {{stats}} placeholders) and build a self-contained REPORT.html with charts, scope statement and disclaimer. Use when the user says \"보고서\", \"리포트 만들어줘\", \"분석 결과 정리\", \"발표 자료\", or as step 5 of park-pipeline."
argument-hint: "[analysis 폴더] [— title:<제목>]"
allowed-tools: Read, Write, Edit, Glob, Bash(park *), Bash(python -m park *)
---

# 보고서

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다.

## 1. 재료 읽기

`BRIEF.md`, `TECH_TREE.md`, `SEARCH_LOG.md`, `SCREENING.md`, `map/stats.json`을 읽는다.

## 2. REPORT_NOTES.md 쓰기

구성 (각 절 3–6문장 또는 글머리표):

1. **핵심 요약** — 분석 목적에 대한 답을 먼저.
2. **출원 동향** — 증가·정체 구간과 그 시기. 미공개 구간은 해석에서 뺀다.
3. **주요 출원인** — 상위 출원인의 비중, 국내 기업·대학·연구소·해외 출원인의 구성.
4. **기술 분류별 특징** — 어느 분류가 커지는지, 출원인별로 집중하는 분류.
5. **한계** — 검색 범위, 근거 등급(provisional), 노이즈 재검토 결과.
6. **다음 단계 제안** — 핵심특허 전문 검토, 청구항 대비, 해외 문헌 추가 등.

**숫자 규칙:** 건수·비율·순위는 직접 쓰지 않고 자리표시자로 쓴다. 렌더링할 때 `map/stats.json`의 값으로 바뀐다.

| 쓰고 싶은 것 | 자리표시자 |
|---|---|
| 집계 대상 건수 | `{{meta.n_counted}}건` |
| 1위 출원인 이름·건수·비중 | `{{applicants_top.0.name}}`, `{{applicants_top.0.count}}건`, `{{applicants_top.0.share\|pct}}` |
| 특정 연도 건수 | `{{yearly.<인덱스>.count}}건` (인덱스는 stats.json의 yearly 배열 순서) |
| 미공개 기준일 | `{{meta.unpublished_cutoff}}` |

(표 안이라 `\|`로 적었다. 실제로는 `{{applicants_top.0.share|pct}}`처럼 쓴다.)

연도(2019년)처럼 세는 값이 아닌 숫자는 그냥 써도 된다.
"공백기술", "신규성 있음", "회피 가능" 같은 단정은 쓰지 않는다 (원칙 4).

## 3. 빌드와 검사

```bash
park check <DIR>
park report <DIR> --title "<제목>" --strict
```

`problem:`이 나오면 고친다: 알 수 없는 자리표시자는 stats.json의 경로를 확인하고, 직접 쓴 숫자는 자리표시자로 바꾼다.

## 4. 전달

`REPORT.html` 경로와 핵심 요약 3줄, 한계 1줄을 사용자에게 알린다.
