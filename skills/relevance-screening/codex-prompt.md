You are screening Korean patent documents for PARK (a patent landscape toolkit). Work only inside the analysis directory you were started in (current directory). Do not use the network.

Read first:
1. TECH_TREE.md — the technology classification (codes, with 정의/포함/제외 and priority rules). This is the ONLY judgement standard.
2. The batch files assigned to you below, in screening/todo/.

For EVERY document (### <application_no>) in each assigned batch, append one JSON object per line to screening/done/<batch-name>.jsonl (e.g. screening/done/batch_003.jsonl; for tail_audit.md use screening/done/tail_audit.jsonl, for noise_audit.md screening/done/noise_audit.jsonl). Keys:
{"application_no": "...", "relevance": "valid|noise|undecided", "tech_code": "<code or empty>", "evidence_level": "provisional", "evidence_location": "요약|명칭", "evidence_quote": "...", "rationale": "<한국어 한 문장>", "screened_by": "codex:gpt-6.1-sol<SUFFIX>"}

Rules:
- valid = the invention's PURPOSE or CLAIMED CONFIGURATION falls under a TECH_TREE row (정의/포함), and not under its 제외. A keyword appearing in passing is not enough.
- tech_code is required for valid and must be one of the codes in TECH_TREE.md. Apply the priority rules written under the table.
- noise = outside every row, or inside a row's 제외 column (typical noise: documents that only mention the keyword in passing, or apply the technology to an unrelated product).
- undecided = the definitions genuinely cannot decide it. Do not force a choice.
- evidence_quote: copy 8–80 characters VERBATIM from that document's 요약 (location "요약") or 명칭 (location "명칭"). Do not paraphrase, translate, fix typos, or join separate sentences. Quotes are machine-checked against the source text; whitespace differences are tolerated, nothing else is.
- Give a quote for noise judgements too (the phrase that shows what the invention is really about).
- Write valid JSON (double quotes, escape inner quotes). One line per document, no extra text in the .jsonl file.
- Do not edit any other file.

When done, print one line per batch: "<batch>: valid N, noise N, undecided N".
