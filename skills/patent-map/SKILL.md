---
name: patent-map
description: "Compute patent-map statistics and SVG charts (yearly trend with unpublished-window shading, top applicants, IPC, technology × year, applicant × technology, growth stage) from candidates/screening with deterministic rules. Use when the user says \"특허맵\", \"출원 동향\", \"출원인 분석\", \"patent map\", or as step 4 of park-pipeline."
argument-hint: "[analysis 폴더] [— as-of:YYYY-MM-DD]"
allowed-tools: Read, Write, Glob, Bash(park *), Bash(python -m park *)
---

# 특허맵

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다. 이 스킬에서 숫자를 만드는 것은 도구다. 나는 결과를 읽고 확인한다.

## 1. 출원인 이름 점검 (집계 전에)

같은 출원인이 여러 이름으로 나뉘면 순위가 틀어진다. 도구가 띄어쓰기·법인 표기("주식회사", "(주)", "Inc." 등) 차이는 자동으로 합친다.

**먼저 `applicant_merges.csv`를 본다.** 자동으로 합친 이름 목록이다. 법인 표기를 떼고 나니 이름이 같아진 *다른 회사*가 섞일 수 있다 (실제 예: "(주)디티에스"와 미국 "디티에스, 인코포레이티드"). 잘못 합쳐진 것은 `aliases.csv`에 `match=exact`로 떼어 낸다.

`aliases.csv` 형식 (열: `alias,canonical,match`):

| alias | canonical | match | 용도 |
|---|---|---|---|
| Samsung Electronics Co., Ltd. | 삼성전자주식회사 | key | 합치기 (같은 키의 모든 표기) |
| 디티에스, 인코포레이티드 | DTS, Inc. (미국) | exact | 떼어 내기 (이 표기만) |

추가로 합칠 경우:
- 영문/한글 병기 (예: "Samsung Electronics Co., Ltd." ↔ "삼성전자주식회사")
- 계열사를 묶을지 말지 — **분석 목적에 따라 다르므로 사용자에게 묻는다**
- 대학 산학협력단 표기 차이

`aliases.csv`를 만들었다면 반입·검색을 다시 실행하거나 (`--aliases aliases.csv`) 사용자에게 알린다.

## 2. 집계

```bash
park map <DIR> --as-of <기준일>
```

- 기준일: 데이터를 수집한 날. 비우면 candidates.csv의 `status_as_of` 최댓값을 쓴다.
- `screening.csv` 파일이 있으면 유효특허만 센다 (판정이 0건이면 0건). 파일이 없으면 전체 후보를 센다. 어느 쪽인지는 `meta.basis`에 표시된다.
- 다시 실행하면 이전 차트는 지워지고 현재 통계로 다시 그린다.
- `country` 열이 2개국 이상이면 국가별 건수, 국가 × 연도, 국가 × 기술 분류 차트가 추가된다. 출원인 막대에는 출원인 국적이 붙는다.
- 결과: `map/stats.json`, `map/*.svg`.

## 3. 확인

`map/stats.json`을 읽고 이상한 점을 찾는다.
- `n_undated`가 크면 출원일이 비어 있는 문헌이 많다는 뜻이다. 반입 열 인식을 의심한다.
- 상위 출원인에 같은 회사가 두 번 보이면 1단계로 돌아간다.
- `unpublished_cutoff` 이후 연도는 빗금으로 표시된다. 해석할 때 감소로 읽지 않는다.

집계 규칙을 바꾸고 싶다는 요청(패밀리 단위, 공동출원 분할 집계)은 아직 지원하지 않는다고 알리고 기록해 둔다.
