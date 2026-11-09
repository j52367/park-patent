---
name: key-patent-review
description: "Phase 2: pick key patents from the valid set — shortlist, fetch claims/forward citations/legal status from KIPRIS, then judge importance (핵심/주목/일반) on the independent claims with verbatim claim quotes ('confirmed' evidence). Use when the user says \"핵심특허\", \"주요특허 선정\", \"청구항 검토\", \"key patents\", or after park-report when a deeper analysis is wanted."
argument-hint: "[analysis 폴더] [— focal:<출원인>] [— n:300]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(park *), Bash(python -m park *), Agent
---

# 핵심특허 선정

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다. 관련성(유효/노이즈)은 이미 정해져 있다. 이 단계는 **중요도**만 본다.

## 1. 압축 목록

```bash
park shortlist <DIR> --n 300 --per-code 12 --focal "<초점 출원인>"
```

- 선정 순서:
  1. 초점 출원인(분석을 의뢰한 기관이나 기업)의 유효특허 전부
  2. 기술분류마다 점수 상위 몇 건
  3. 나머지는 점수 = 권리상태 가중치 × 관련도 점수 순
- 이유는 `reason` 열에 남는다.
- 호출 예산에 맞춰 `--n`을 정한다. 문헌 1건당 상세 조회와 피인용 조회로 호출이 2번 든다.

## 2. 청구항·피인용 수집

```bash
park quota
park enrich <DIR> --budget <호출 상한>
```

- 결과:
  - `details/<출원번호>.json`: 청구항, 우선권, 심사관 인용문헌, 법적상태 이력, 패밀리, R&D 과제
  - `fulltext/<출원번호>.txt`: 청구항 전문
  - `enrich.csv`: 피인용 수, 청구항 수, 독립항 수, 패밀리 수
- 이미 받은 문헌은 다시 받지 않는다. 예산이 모자라면 다음 달에 이어서 받는다.

## 3. 판정 기준 (IMPORTANCE.md)

분석 폴더에 `IMPORTANCE.md`를 만들고 사용자 확인을 받는다. 기본 틀은 다음과 같다.

| 등급 | 기준 |
|---|---|
| 핵심 | 독립항이 분류표 한 칸의 **핵심 원리 자체**를 적은 수의 구성요소로 넓게 청구하고, 다음 중 하나 이상이 있다: 피인용 상위 25%, 해외 패밀리 있음, 그 칸에서 이른 시기의 기반 출원 |
| 주목 | 기술적으로 의미 있거나 전략적으로 중요하지만 청구항이 좁거나 신호가 약하다. 초점 출원인과 주요 경쟁사의 주력 라인이 여기에 많다 |
| 일반 | 특정 응용·구조의 점진적 개량. 구성요소가 많아 회피가 쉽다 |

청구항의 넓이는 독립항 구성요소의 수와 한정어의 구체성으로 본다. 피인용 수는 오래된 문헌일수록 많으므로 출원 연도를 함께 본다.

## 4. 판정

```bash
park review-batches <DIR> --size 15        # review/todo/key_###.md
```

배치마다 `review/done/key_###.jsonl`에 한 줄씩 쓴다.

```json
{"application_no": "...", "importance": "핵심|주목|일반", "evidence_level": "confirmed", "evidence_location": "청구항 1", "evidence_quote": "<독립항에서 그대로 복사한 구절>", "key_features": "<청구항이 실제로 보호하는 것 한 줄>", "rationale": "<등급 근거: 넓이 + 신호>", "reviewed_by": "<모델명>"}
```

- 근거 인용은 **해당 번호의 청구항에서** 그대로 복사한다. `park merge-review`가 그 청구항 원문과 대조한다.
- 피인용 같은 신호는 배치에 적힌 값만 쓴다. 지어내지 않는다.
- 병렬 판정: Claude 서브에이전트, 또는 `scripts/codex-screen.sh`와 같은 방식으로 `codex-prompt.md`를 쓴다.

```bash
park merge-review <DIR>     # key_review.csv + 인용 검증
```

## 5. 보고

- 등급별 건수와 핵심특허 목록(출원번호, 명칭, 출원인, key_features)을 보여 준다.
- 경계에 있는 사례 몇 건은 사용자에게 확인받는다.
- 다음 단계는 `/ip-strategy` (SWOT·전략)다.
