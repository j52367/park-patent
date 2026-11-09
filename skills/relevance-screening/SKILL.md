---
name: relevance-screening
description: "Screen candidate patents into noise / valid (with technology code) using TECH_TREE.md, attaching a verbatim evidence quote to every judgement, then audit a random noise sample for false negatives. Use when the user says \"유효특허 선별\", \"노이즈 제거\", \"스크리닝\", \"관련 특허만 골라줘\", or as step 3 of park-pipeline."
argument-hint: "[analysis 폴더] [— batch-size:40] [— parallel:4]"
allowed-tools: Read, Write, Glob, Grep, Bash(park *), Bash(python -m park *), Agent
---

# 관련성 선별 (노이즈 / 유효)

대상: **$ARGUMENTS**

먼저 `../shared-references/principles.md`를 읽는다. 이 단계는 **관련성**만 본다. 중요도(핵심특허 여부)는 PARK 2단계의 별도 작업이다.

## 1. 정렬하고 배치 만들기

후보가 1,000건을 넘으면 먼저 정렬하고 상위부터 본다.

```bash
park rank <DIR> --terms "<대상 기술을 설명하는 핵심어들>"   # rank.csv
park batches <DIR> --size 40 --top 1000                      # 순위 상위 1,000건만
park audit-sample <DIR> --below-rank 1000 --n 80             # 컷 아래 무작위 표본 → screening/todo/tail_audit.md
```

- `screening/todo/batch_###.md`가 생긴다. 이미 판정한 문헌은 다시 나오지 않는다.
- 정렬은 문헌을 지우지 않고 순서만 정한다.
- `tail_audit.md`도 다른 배치와 똑같이 판정한다. 판정자 표시 뒤에 `:tail-audit`를 붙인다.
- 꼬리 표본의 유효 비율 × 컷 아래 문헌 수 = 컷 아래에 남은 유효 문헌 추정치. 이 값이 크면 `--top`을 늘려 다음 구간을 본다.
- 후보가 적으면(수백 건) 정렬 없이 `park batches <DIR>`로 전부 본다.

### 판정이 쌓이면: 학습 정렬 (권장)

유효와 노이즈 판정이 각각 20건 이상 모이면, 분류표 유사도 대신 **지금까지의 판정으로 학습한 정렬**을 쓴다. 실험에서 꼬리 표본 AP가 0.47에서 0.80으로 올랐다 (`docs/experiments/2026-11-09_ranking.md`).

```bash
park rank <DIR> --learn                                   # rank.csv + rank_eval.json (교차검증 성능)
park batches <DIR> --next 600 --prefix r3                 # 아직 안 본 문헌 중 상위 600건
park audit-sample <DIR> --below-rank <출력된 최저 순위> --n 100 --round 3
```

- 이 순환(판정 → 학습 → 재정렬 → 상위 선별 → 꼬리 표본)을 꼬리 표본의 유효 비율이 충분히 낮아질 때까지 되풀이한다.
- 학습 점수는 순서를 정할 때만 쓴다. 확률값은 보정되지 않아 남은 양을 부풀린다. 남은 양은 꼬리 표본으로만 추정한다.

### 다음 구간과 분류표 변경

- **다음 구간:** 꼬리 표본에서 유효가 많이 나오면 `park batches <DIR> --top 2000 --prefix r2`로 이미 본 문헌을 뺀 다음 구간을 만든다. 라운드마다 접두어를 바꾼다. 같은 접두어는 앞 결과를 덮어쓰지 않도록 막혀 있다.
- **새 꼬리 표본:** `park audit-sample <DIR> --below-rank 2000 --n 100 --round 2`를 실행한다. 추정에는 가장 최근 라운드 표본만 쓴다.
- **분류표를 좁혔을 때:** 정의가 바뀐 칸에서 유효였던 문헌만 다시 본다 (`park batches <DIR> --recheck-codes C1,W1 --prefix recheck`). 좁히면 노이즈가 유효로 바뀔 일은 없으므로 나머지는 그대로 둔다. 바꾸기 전 분류표는 `TECH_TREE.v1.md`처럼 남긴다.
- 병합할 때는 **나중에 쓴 결과 파일이 이긴다** (파일 이름 순서와 무관). 꼬리 표본에 뽑힌 문헌은 다시 판정해도 표본 표시가 유지된다.

## 2. 배치마다 판정

`TECH_TREE.md`의 **정의·포함·제외**를 기준으로 각 문헌을 판정해 `screening/done/batch_###.jsonl`에 한 줄에 하나씩 쓴다.

```json
{"application_no": "1020190012345", "relevance": "valid", "tech_code": "A1", "evidence_level": "provisional", "evidence_location": "요약", "evidence_quote": "셀 전압과 전류를 측정하여 확장 칼만 필터에 입력하고", "rationale": "SOC 추정 방법 자체가 청구 대상", "screened_by": "<모델명>"}
```

판정 규칙:
- `relevance`: `valid` / `noise` / `undecided`. 정의만으로 결정이 안 되면 `undecided`. 억지로 고르지 않는다.
- `tech_code`: `valid`일 때 필수. TECH_TREE.md에 있는 코드만 쓴다.
- `evidence_location`: 인용을 가져온 곳. `요약`, `명칭`, `서지`, 그리고 candidates.csv에 `independent_claims`가 있으면 `독립청구항`. `청구항 1`, `[0023]` 같은 위치는 `fulltext/<출원번호>.txt`가 있을 때만 쓸 수 있다 (`park check`가 그 위치의 원문과 대조한다).
- `evidence_quote`: 판정 이유가 드러나는 구절(공백 제외 8자 이상)을 **원문에서 그대로 복사**한다. 노이즈 판정에도 근거를 단다 (예: 결제 서버에 관한 문헌이라는 구절).
- `evidence_level`: 요약만 봤으므로 `provisional`.
- 명칭에 키워드가 있다는 이유만으로 `valid`로 하지 않는다. 그 기술이 발명의 **목적이나 구성**인지 본다.

배치가 많으면 나눠서 병렬로 판정한다.
- **Claude 서브에이전트:** Agent 도구로 나눠 맡긴다 (예: 4개씩). 각 서브에이전트에는 TECH_TREE.md 전문, 이 판정 규칙, 맡은 배치 파일 경로만 넘긴다.
- **Codex CLI (선택):** `scripts/codex-screen.sh <DIR> 4`를 실행한다. 판정 규칙은 `codex-prompt.md`에 있고, 결과가 없는 배치만 골라 돌린다.
  - 사용량 한도에 걸리면 멈춘 뒤 나중에 다시 실행하면 이어서 한다.
  - 특허 본문이 OpenAI로 전송되므로, 기밀 입력은 사용자의 허락 없이 쓰지 않는다.
  - 실측 기준(gpt-6.1-sol, medium): 문헌 200건에 토큰 약 10만 개, 약 10분이 든다.

## 3. 병합과 검사

```bash
park merge-screening <DIR>
```

`park check`가 함께 돈다. ERROR가 있으면 해당 줄을 고쳐 다시 병합한다 (같은 출원번호는 나중 판정이 이긴다). 흔한 오류:
- `evidence_quote not found` — 인용을 다듬었거나 띄어쓰기 외의 글자가 다르다. 원문에서 다시 복사한다.
- `tech_code ... not defined` — 분류표에 없는 코드. 분류표를 고칠지 사용자에게 묻는다.

## 4. 노이즈 재검토 (거짓음성 점검)

```bash
park audit-sample <DIR> --n 30
```

`AUDIT_SAMPLE.md`의 문헌을 **앞선 판정을 보지 않은 새 검토자**가 다시 판정한다. 새 서브에이전트를 쓰고, 사용자가 허락했다면 Codex 같은 다른 모델을 쓴다.
두 지표를 구분한다 (`AUDIT_SAMPLE.md` 머리말에 실제 건수가 들어간 식이 있다).
- **노이즈 누락률** r = 유효로 뒤집힌 수 ÷ 표본 수 — 노이즈 더미 안에 유효특허가 얼마나 섞였나.
- **추정 거짓음성률** = (r × 노이즈 수) ÷ (유효 수 + r × 노이즈 수) — 유효특허 전체 중 놓친 비율. 노이즈가 유효보다 훨씬 많으면 r이 작아도 이 값은 클 수 있다.

추정 거짓음성률이 10%를 넘으면 원인(분류표 정의가 좁음, 판정 습관)을 찾아 노이즈 전체를 다시 보거나 분류표를 고칠지 사용자와 정한다. 표본이 작으면(30건 미만) 추정이 거칠다는 점도 함께 적는다. 결과는 `SCREENING.md`에 적는다.

## 5. SCREENING.md와 보고

`SCREENING.md`에 적는다: 판정 기준 요약, `park check` 통계, undecided 목록과 이유, 노이즈 재검토 결과, 분류표 변경 이력.
사용자에게 노이즈/유효/보류 건수, 노이즈 누락률, 추정 거짓음성률을 보고하고 확인을 받는다.
