You are reviewing Korean patents for importance (phase 2 of PARK). Work only inside the analysis directory you were started in. Do not use the network.

Read first:
1. IMPORTANCE.md — the grading standard (핵심 / 주목 / 일반). It is the ONLY standard.
2. TECH_TREE.md — what each technology code means.
3. The batch files assigned to you below (review/todo/key_###.md). Each document shows its independent claims and deterministic signals (forward citations and their percentile, claim count, status, family size, filing date).

For EVERY document (### <application_no>) write one JSON object per line to review/done/<batch-name>.jsonl (e.g. review/done/key_003.jsonl):
{"application_no": "...", "importance": "핵심|주목|일반", "evidence_level": "confirmed", "evidence_location": "청구항 <n>", "evidence_quote": "...", "key_features": "<한국어 한 줄: 이 청구항이 실제로 보호하는 것>", "rationale": "<한국어 한두 문장: 청구항의 넓이와 신호를 근거로>", "reviewed_by": "codex:gpt-6.1-sol"}

Rules:
- Judge breadth from the independent claims: few essential elements and general wording = broad; many specific limitations = narrow.
- Use only the signals printed in the batch. Older filings naturally collect more citations — weigh the filing year.
- evidence_quote: copy 10–120 characters VERBATIM from the claim named in evidence_location (the claim number is the number at the start of that claim). No paraphrase, no joining of separate parts. Quotes are machine-checked.
- If a document has no claims, use importance "일반", evidence_location "", evidence_quote "", and say so in rationale.
- Valid JSON only, one line per document. Do not edit any other file.

When done, print one line per batch: "<batch>: 핵심 N, 주목 N, 일반 N".
