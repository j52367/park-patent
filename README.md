# PARK — Patent Analysis Research Kit

**한국 특허 동향 분석을 위한 Claude Code 스킬 + 결정적 도구 모음** · [English](#english)

> ⚠️ 0단계(뼈대) 단계입니다. 동작하는 것과 아직 아닌 것은 [진행 상황](#진행-상황)을 보세요.

과제 설명을 주면 **기술 분류 → 검색식 → KIPRIS 검색(또는 엑셀 반입) → 노이즈 제거 → 특허맵 → 보고서**를 만듭니다.
캠퍼스 특허 유니버시아드(CPU), 특허동향조사, 스타트업·연구실의 "이 기술 특허 상황이 어때?"에 답하는 용도입니다.

## 왜 PARK인가

LLM에게 특허 분석을 시키면 그럴듯한 문서가 나오지만, 숫자를 지어내거나 근거 없이 단정하기 쉽습니다. PARK는 이것을 구조로 막습니다.

| 문제 | PARK의 장치 |
|---|---|
| LLM이 건수·비율을 지어냄 | 숫자는 `park` 도구만 계산합니다. 보고서 문장은 `{{meta.n_counted}}` 같은 자리표시자를 쓰고, 직접 쓴 숫자는 `park check`가 잡아냅니다 |
| 근거 없는 판정 | 선별 판정마다 원문 인용을 달고, `park check`가 그 인용이 원문에 **실제로 있는지** 확인합니다 |
| 유효특허를 노이즈로 버림 | 노이즈 무작위 표본을 새 검토자가 다시 보고 거짓음성률을 추정합니다 (`park audit-sample`) |
| 최근 연도 "감소" 오독 | 출원 후 18개월 미공개 구간을 차트에 빗금으로 표시하고 해석에서 뺍니다 |
| 검색 범위를 넘는 결론 | 보고서에 검색 범위를 항상 싣고, KR만 검색했으면 "KR 공개특허 동향"으로 한정합니다 |
| 같은 회사가 여러 이름으로 쪼개짐 | 출원인 이름을 정규화하고, 자동으로 합친 목록(`applicant_merges.csv`)을 사람이 검토합니다 |

## 빠른 시작 (API 키 없이)

```bash
git clone https://github.com/j52367/park-patent.git && cd park-patent
pip install -e ".[dev,excel]"
park demo
```

`analysis/demo/REPORT.html`이 생깁니다 (합성 데이터, 가상 기업).

## Claude Code에서 쓰기

```bash
park install-skills --project <내 분석 프로젝트 폴더>   # 또는 --user (모든 프로젝트)
```

Claude Code에서:

```
/park-pipeline 전기차 배터리 열관리 기술의 국내 특허 동향을 분석해줘 — project:bms-thermal
```

| 스킬 | 하는 일 |
|---|---|
| `/park-pipeline` | 아래 단계를 순서대로 실행, 단계마다 사용자 확인 |
| `/tech-scoping` | 기술 분류표(정의·포함·제외)와 검색식 |
| `/kipris-search` | KIPRIS Plus 검색(캐시·호출 수 관리) 또는 엑셀/CSV 반입 |
| `/relevance-screening` | 노이즈/유효 선별 + 원문 인용 + 노이즈 재검토 |
| `/patent-map` | 출원 동향·출원인·IPC·기술분류 매트릭스·성장 단계 |
| `/park-report` | 해석 작성(숫자는 자리표시자) + REPORT.html |
| `/key-patent-review` | 2단계: 청구항 원문으로 핵심·주목·일반 판정 |
| `/ip-strategy` | 2단계: 특허 기반 SWOT와 전략 제안 |
| `/claim-chart-kr` | 2단계: 청구항 대비표 (신규성·진보성) |

## KIPRIS Plus API

[KIPRIS Plus](https://plus.kipris.or.kr)에서 키를 받아 `.env`에 넣습니다 (`.env.example` 참고).
무료 한도는 **월 1,000회 호출**이므로, PARK는 모든 응답을 `.park/` 캐시에 저장하고 `park quota`로 사용량을 보여 줍니다.
키가 없으면 KIPRIS 웹에서 내려받은 엑셀을 `park ingest`로 쓰면 됩니다.

## `park` 명령

| 명령 | 설명 |
|---|---|
| `park init <dir>` | 분석 폴더와 템플릿 |
| `park ingest <files> --out <dir>` | CSV/엑셀 반입 (한글 헤더 자동 인식) |
| `park search --word "<식>" --out <dir>` | KIPRIS 검색 (`--count-only`로 건수만) |
| `park quota` | 이번 달 API 호출 수 |
| `park rank` | 분류표와의 유사도로 후보 정렬. `--learn`이면 지금까지의 판정으로 학습해 정렬 (CPU) |
| `park batches` / `merge-screening` / `audit-sample` | 선별 작업 단위, 다시 판정, 꼬리 표본 |
| `park shortlist` / `enrich` | 2단계 대상 압축, 청구항·피인용·법적상태 수집 (문헌당 호출 2회) |
| `park review-batches` / `merge-review` | 핵심특허 판정 배치, 청구항 인용 검증 |
| `park swot` | 초점 출원인 대 경쟁 출원인 집계와 SWOT 후보 |
| `park chart` / `merge-chart` | 청구항 대비표: 구성요소 분할, 선행문헌 선정, 인용 검증 |
| `park map <dir>` | 집계(`map/stats.json`)와 SVG 차트 |
| `park check <dir>` | 인용 검증, 분류 코드 검증, 보고서 숫자 검사 |
| `park report <dir>` | REPORT.html |
| `park demo` | 합성 데이터로 전체 흐름 |

## 진행 상황

- [x] 0단계: CLI, CSV/엑셀 반입, KIPRIS 클라이언트(캐시·쿼터), 특허맵, 근거 검증, 보고서, 합성 데모, MVP 스킬 6종
- [x] 여러 국가 데이터 반입 (WIPS 등 상용 DB 엑셀): 국가별 건수, 국가 × 연도, 국가 × 기술 분류, 출원인 국적
- [x] 실제 CPU 과제 데이터(5개국, 사람 판정) 재현: 사람이 만든 국가 × 기술 표와 합계 일치
- [x] KIPRIS Plus 실제 검색: 검색식 문법 확인 ([메모](skills/shared-references/kipris-query-syntax.md)), 한 번에 500건
- [x] 1단계 실제 주제로 실행 (KR 후보 약 7천 건): 사전 정렬 → 상위 구간 선별 → 꼬리 표본으로 남은 유효 건수 추정 → 보고서
- [x] 선택 백엔드: Codex CLI 병렬 선별 (`scripts/codex-screen.sh`)
- [x] 정렬 실험: 판정 학습 정렬(CPU)이 다국어 임베딩보다 낫다 → `park rank --learn` ([기록](docs/experiments/2026-11-09_ranking.md))
- [x] 2단계: 압축 목록 → 청구항·피인용 수집 → 청구항 원문 기반 핵심특허 판정(인용 검증) → 특허 기반 SWOT, 보고서에 핵심특허 표와 SWOT 절
- [x] 청구항 대비표: 신규성·진보성 (구성요소 분할 → 기준일 이전 문헌·심사관 인용 → 문헌 × 구성요소 판정, 인용 검증)
- [ ] 침해·회피설계 대비표, 명세서 본문 대조, 해외 특허(KIPRIS 해외특허 API)
- [ ] 1단계: 실제 과제 1건 완주, 사전 정렬(BM25/임베딩)
- [ ] 2단계: 핵심특허 전문 검토, 청구항 대비(신규성·진보성·침해), 무효 공방, 전략, 해외 문헌
- [ ] 3단계: 한국어 특허 검색 모델, KR 무효 근거 벤치마크

설계는 [docs/DESIGN.md](docs/DESIGN.md)에 있습니다.

## 다른 프로젝트와의 관계

- [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (MIT): Markdown 스킬 + 다른 모델의 교차 검토 구조를 참고했습니다. ARIS의 특허 기능은 *출원서 작성*(CN/US/EP)이고, PARK는 *한국 특허 분석*이라 겹치지 않습니다.
- [claude-for-legal](https://github.com/anthropics/claude-for-legal) (Apache-2.0): 미국 IP 실무용 플러그인. FTO·침해 선별 설계를 2단계에서 참고할 예정입니다.
- [PatentAgentBench](https://github.com/patsnap/PatentAgentBench) (MIT): 평가에 사용할 예정입니다.

## 라이선스와 면책

코드와 스킬은 Apache-2.0입니다. 합성 데모 데이터는 가상이며 실제 특허가 아닙니다. KIPRIS에서 받은 데이터는 KIPRIS Plus 이용약관을 따르며, 이 저장소에는 넣지 않습니다.
모든 산출물은 **검토 의견 초안이며 법률 의견이 아닙니다** ([DISCLAIMER.md](DISCLAIMER.md)).

---

## English

PARK turns a technology brief into a Korean patent landscape report: tech classification → KIPRIS search or spreadsheet import → noise screening → patent map → HTML report.
LLM skills make the judgements; a deterministic CLI does every count. Every screening decision carries a verbatim quote that `park check` verifies against the source text, report prose may only state numbers through `{{stats}}` placeholders, a random sample of "noise" is re-screened to estimate false negatives, and the last 18 months (not yet published) are shaded rather than read as a decline.

```bash
pip install -e ".[dev,excel]" && park demo   # no API key needed; writes analysis/demo/REPORT.html
park install-skills --user                   # install the Claude Code skills
```

Status: Phase 0 (scaffold). Outputs are drafts for professional review, not legal advice. License: Apache-2.0.
