---
name: tech-scoping
description: "Break a technology/task description into a Korean patent technology classification table (대·중·소분류 with include/exclude rules) and KIPRIS search queries (keywords, synonyms, IPC). Use when the user says \"기술 분류\", \"기술분류표\", \"검색식 만들어줘\", \"검색 키워드\", \"tech tree\", or as step 1 of park-pipeline."
argument-hint: "[과제 설명 또는 analysis 폴더]"
allowed-tools: Read, Write, Edit, Glob, Bash(park *), Bash(python -m park *), WebSearch
---

# 기술 분류표와 검색식 만들기

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`와 `../shared-references/kipris-query-syntax.md`를 읽는다.

## 1. 과제 이해

`BRIEF.md`(있으면)와 사용자가 준 자료를 읽고 다음을 정리한다.
- 핵심 기술이 해결하는 문제 1–2문장
- 기술을 이루는 요소(구성)와 그 대안 기술
- 분석 목적. 목적에 따라 분류 기준이 달라진다: 동향 파악이면 기술 요소별, 경쟁 분석이면 응용 분야별, 회피 설계면 구성요소별.

모르는 용어나 최신 기술 흐름은 WebSearch로 확인할 수 있다. 확인한 출처는 `QUERIES.md`에 남긴다.

## 2. TECH_TREE.md

형식 (첫 칸 코드는 반드시 백틱):

```markdown
| 코드 | 대분류 | 중분류 | 정의 | 포함 | 제외 |
|---|---|---|---|---|---|
| `A1` | 상태 추정 | SOC/SOH 추정 | ... | ... | ... |
```

규칙:
- 중분류는 4–10개 정도. 한 문헌이 어느 칸에 들어갈지 **정의·포함·제외**만 보고 판단할 수 있어야 한다. 선별 단계의 판정 기준이 이 표다.
- 칸끼리 겹치면 우선순위를 적는다 (예: "A1과 A4에 모두 해당하면 청구항 1의 목적 기준").
- "기타" 칸은 만들지 않는다. 애매한 문헌은 선별에서 `undecided`로 남긴다.

## 3. QUERIES.md

중분류마다 다음을 적는다.

| 항목 | 내용 |
|---|---|
| 핵심어 | 한글 표기 변형, 영문, 약어 (예: 이차전지, 2차전지, 리튬이온전지, secondary battery) |
| 함께 쓰이는 말 | 문제·목적·효과 표현 |
| IPC 후보 | 서브클래스·메인그룹과 그 이유. 보조 조건으로만 사용 |
| 검색식 | KIPRIS 문법. 미검증 문법을 썼다면 표시 |

마지막에 **실행 계획**을 적는다: 실행할 검색식 목록, 예상 건수(모르면 "건수 확인 필요"), 예상 호출 수.
아는 핵심특허가 있다면 재현율 점검용으로 출원번호를 적는다.

## 4. 확인 받기

분류표와 검색식을 보여 주고 사용자 확인을 받는다. 고친 내용은 파일에 반영한다.
