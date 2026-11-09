You are preparing a Korean patent claim chart (novelty / inventive step) for PARK. Work only inside the chart directory you were started in. Do not use the network. Do not edit any file except done.jsonl.

Read todo.md: the target claim, its elements (E0 = preamble subject, E1… = elements), its reference date, and the earlier documents with their abstracts and claims.

Write done.jsonl with one JSON object per line:

1. For EVERY (document, element) pair:
{"prior_art": "<application_no>", "element": "E1", "status": "개시|일부|미개시", "location": "청구항 <n>|요약", "quote": "<verbatim text>", "note": "<한국어 한 문장: 대응 관계와 차이>"}
   - 개시 = the document discloses the element as claimed (same structure/function, possibly different words).
   - 일부 = a related feature exists but differs in an essential point (state the difference in note).
   - 미개시 = nothing corresponding; leave quote "" and location "".
   - quote: copy 6–150 characters VERBATIM from the cited claim (location "청구항 n", n = the number at the start of that claim), the abstract (location "요약"), or a description paragraph (location "[NNNN]", the paragraph number shown in 명세서 발췌). No paraphrase. Machine-checked (paragraph quotes are checked against that paragraph and its neighbours).
   - Prefer the description when it shows the element more clearly than the claims (structure, shape, arrangement are often only in the description).

2. One summary per document:
{"prior_art": "<application_no>", "summary": "<한국어 2문장: 공통점과 핵심 차이>", "novelty": "부정 가능|유지"}
   - "부정 가능" only if EVERY element is 개시 in this single document.

3. Inventive-step combinations (0–3 lines), only when a combination covers every element:
{"combination": ["<primary application_no>", "<secondary application_no>"], "covers": {"E1": "<no>", "E2": "<no>", ...}, "motivation": "<한국어: 결합 동기 — 같은 기술분야·같은 과제·명시적 시사 등, 문헌에 근거해서>", "weakness": "<한국어: 이 결합 논리의 약점>"}

Be conservative: when unsure between 개시 and 일부, choose 일부 and explain. This is a draft for a patent attorney, not a legal opinion.
