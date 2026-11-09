---
name: claim-chart-kr
description: "Phase 2: Korean claim chart for one claim — split into elements, find the closest earlier KR documents (similarity + examiner-cited), chart element by element (개시/일부/미개시) with verbatim quotes, and draft novelty / inventive-step arguments. Use when the user says \"청구항 대비\", \"클레임 차트\", \"claim chart\", \"신규성 검토\", \"진보성 검토\", \"선행기술 대비\"."
argument-hint: "[analysis 폴더] [— target:<출원번호>] [— claim:1]"
allowed-tools: Read, Write, Edit, Glob, Bash(park *), Bash(python -m park *), Agent
---

# 청구항 대비표 (신규성·진보성)

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다.

## 모드

| 모드 | 비교 | 지원 |
|---|---|---|
| 신규성 | 대상 청구항 대 **단일** 선행문헌. 구성요소가 모두 개시됐는지 본다 | ✅ |
| 진보성 | 주 선행문헌과 보조 문헌의 **결합**. 결합 동기를 문헌 근거로 적는다 | ✅ (초안) |
| 침해·회피설계 | 제품 대 청구항 | ❌ 제품 설명이 필요하다. 사용자가 주면 같은 표 형식으로 수동 작성 |

## 1. 준비

명세서 본문 없이 요약과 청구항만 대조하면, 본문과 도면에만 있는 구성을 놓친다. 가능하면 `--fulltext`를 쓴다.

```bash
park chart <DIR> --target <출원번호> --claim 1 --k 8 --examiner --fetch-claims --fulltext --include <사용자가 아는 출원번호들>
```

- `--fulltext`: 선행문헌의 공보 PDF(등록공보를 먼저, 없으면 공개공보)를 받아 명세서 본문을 단락 단위로 뽑는다(`description/`). 그다음 구성요소마다 관련 단락을 골라 판정 자료에 넣는다.
  - 형상·배치처럼 청구항에 없고 본문에만 있는 구성을 잡기 위해서다.
  - 비용은 문헌당 호출 1–2회와 PDF 1건이다. PyMuPDF가 필요하다 (`pip install 'park-patent[fulltext]'`).
- `--include`: 유사도와 상관없이 반드시 대비할 문헌.

- `charts/<출원번호>_c1/`에 다음이 생긴다.
  - `ELEMENTS.md`: 구성요소 분할 (E0 = 청구항 끝의 대상 이름)
  - `prior_art.csv`: 기준일 이전 문헌 중 유사도 상위 k건, 그리고 심사관이 인용한 KR 문헌
  - `todo.md`: 판정자에게 줄 자료
- 기준일은 우선권일이고, 없으면 출원일이다.
- **구성요소 분할을 사용자에게 보여 주고 확인받는다.** 분할이 틀리면 대비표 전체가 틀린다. 고칠 때는 `elements.json`을 고친 뒤 다시 실행한다.
- `--examiner`: 심사관 인용 KR 공개번호를 출원번호로 찾아 함께 넣는다 (번호당 검색 1회).
- 유사도 검색만으로는 부족하다. 실제 사례에서 심사관 인용 문헌의 유사도 순위가 18위와 1,465위였다. 심사관 인용과 사용자가 아는 문헌을 반드시 함께 넣는다.

## 2. 판정

`todo.md`를 읽고 `done.jsonl`에 쓴다. 형식과 규칙은 `codex-prompt.md`에 있다.
- 문헌 × 구성요소마다 개시 / 일부 / 미개시와 원문 인용을 단다.
- 문헌마다 요약과 신규성("부정 가능" 또는 "유지")을 적는다.
- 진보성 결합을 0–3개 제안하고, 결합 동기와 약점을 함께 적는다.
- 확신이 없으면 '개시'가 아니라 '일부'로 둔다.
- Codex로 돌릴 때: 차트 폴더에서 `codex exec ... "$(cat skills/claim-chart-kr/codex-prompt.md)"`

## 3. 검증과 보고

```bash
park merge-chart <DIR> --target <출원번호> --claim 1
park report <DIR> --strict
```

- 인용문은 지정한 청구항, 요약, 또는 명세서 단락(`[NNNN]`) 원문과 대조한다. 단락은 PDF 여백의 번호 위치가 부정확해서 앞뒤 한 단락까지 허용한다.
- 보고서의 "청구항 대비" 절에 문헌 × 구성요소 표(● 개시, ◐ 일부, ○ 미개시), 문헌별 요약, 결합 논리가 실린다.
- 결론은 "검토 의견 초안"이다. 검색 범위(KR 공개특허) 밖 문헌은 반영되지 않았음을 함께 알린다.
