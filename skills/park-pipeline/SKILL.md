---
name: park-pipeline
description: "Korean patent landscape analysis end to end — tech scoping, KIPRIS search or CSV import, relevance screening, patent map, HTML report — with evidence-backed judgements and user checkpoints. Use when the user says \"특허 동향 분석\", \"특허 분석해줘\", \"선행기술조사\", \"유효특허 분석\", \"특허맵\", \"CPU 과제\", \"patent landscape\", or gives a technology and asks what the Korean patent situation is."
argument-hint: "[과제 설명 또는 BRIEF 파일 경로] [— project:<이름>]"
allowed-tools: Bash(park *), Bash(python -m park *), Read, Write, Edit, Glob, Grep, Skill, Agent
---

# PARK 파이프라인: 과제 설명 → 특허 동향 보고서

과제: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다. 이 스킬은 아래 단계를 순서대로 부르는 오케스트레이터다.

```
① /tech-scoping ──► [확인 ①: 분류표·검색식]
② /kipris-search (또는 CSV 반입) ──► [확인 ②: 후보 건수·재현율 점검]
③ /relevance-screening ──► [확인 ③: 선별 결과·노이즈 재검토]
④ /patent-map
⑤ /park-report ──► REPORT.html
```

## 상수

- `PROJECT` — `$ARGUMENTS`의 `project:` 값, 없으면 과제명을 영문 소문자-하이픈으로 줄여 만든다.
- `DIR = analysis/<PROJECT>`
- `AUTO_PROCEED = false` — 사용자가 "자동으로", "묻지 말고"라고 하지 않는 한 확인 단계에서 멈춘다.

## 0단계: 준비

1. `park init <DIR>`
2. `<DIR>/BRIEF.md`에 적는다: 과제 설명 원문, 분석 목적(동향 파악 / 경쟁사 분석 / 출원 전략 등), 대상 국가(MVP는 KR), 기간, 사용자가 이미 알고 있는 핵심특허·경쟁사, 데이터 경로(API / CSV 파일).
3. 데이터 경로를 정한다.
   - 사용자가 CSV·엑셀을 줬다 → ②에서 `park ingest`
   - KIPRIS API 키가 있다(`.env`) → `park quota`로 남은 호출 수를 확인
   - 둘 다 없다 → 사용자에게 KIPRIS 웹에서 검색 결과를 내려받는 방법을 안내하거나, `park demo`로 흐름만 보여 준다.

## ① 기술 분류와 검색식

`/tech-scoping` 실행. 결과 `TECH_TREE.md`, `QUERIES.md`를 사용자에게 보여 주고 **확인 ①**을 받는다.

## ② 후보 수집

`/kipris-search` 실행 (CSV면 그 스킬의 반입 절차를 따른다). 후보 건수, 사용한 호출 수, 알려진 핵심특허가 포함됐는지를 보고하고 **확인 ②**를 받는다.

## ③ 관련성 선별

`/relevance-screening` 실행. 노이즈/유효 건수, 기술 분류별 건수, `park check` 결과, 노이즈 재검토로 얻은 노이즈 누락률과 추정 거짓음성률을 보고하고 **확인 ③**을 받는다.

## ④ 특허맵

`/patent-map` 실행.

## ⑤ 보고서

`/park-report` 실행. 끝나면 `REPORT.html` 경로와 함께 다음을 짧게 알린다.
- 검색 범위(DB·국가·기간)와 그 범위가 뜻하는 한계
- 근거 등급: 이번 분석은 요약 기반이므로 판정이 모두 provisional이라는 점
- 다음 단계로 할 수 있는 것: 핵심특허 전문 검토, 청구항 대비, 해외 문헌 추가 (PARK 2단계)

## 중간에 끊겼을 때

산출물 파일이 곧 진행 상태다. 있는 파일을 보고 다음 단계부터 이어서 한다.
`candidates.csv`가 있으면 ②는 끝난 것이다. `screening/todo`에 남은 배치가 있으면 ③을 이어서 한다.
