"""Synthetic demo project — runs with no API key and no licensed data.

Everything here is fictional: applicants, numbers, titles and abstracts are generated from
templates with a fixed seed. Do not cite it as real patent data.
Domain: 배터리 관리 시스템(BMS).
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from .schema import CANDIDATE_COLUMNS, SCREENING_COLUMNS, conform

AS_OF = "2025-06-30"

TECH_TREE_MD = """# 기술 분류표 — 배터리 관리 시스템(BMS) (합성 데모)

| 코드 | 대분류 | 중분류 | 정의 | 포함 | 제외 |
|---|---|---|---|---|---|
| `A1` | 상태 추정 | SOC/SOH 추정 | 배터리 충전 상태·건강 상태를 추정하는 기술 | 칼만 필터, 등가회로 모델, 학습 기반 추정 | 단순 전압 표시 |
| `A2` | 셀 제어 | 셀 밸런싱 | 셀 간 전압·용량 편차를 줄이는 기술 | 수동/능동 밸런싱 회로와 제어 | 셀 제조 공정 |
| `A3` | 열 관리 | 냉각·가열 제어 | 배터리 팩 온도를 관리하는 기술 | 냉각 유로 제어, 저온 예열 | 차량 실내 공조 |
| `A4` | 안전 | 고장 진단·열폭주 대응 | 이상 징후 진단, 열폭주 예측·차단 | 절연 저항 진단, 가스 센서 기반 경보 | 소화 설비 일반 |
"""

SEARCH_LOG_MD = """# 검색 기록 (합성 데모)

- **데이터베이스**: 합성 데이터 (실제 KIPRIS 아님)
- **국가**: KR (가상)
- **기간**: 출원일 2015-01-01 ~ 2025-03-31
- **검색식**: `(배터리 + 이차전지) * (관리 + 추정 + 밸런싱 + 냉각 + 진단)` (예시)
- **검색 시각**: 2025-06-30 (가상)
- **결과**: 후보 문헌 수는 candidates.csv 참조
"""

REPORT_NOTES_MD = """## 핵심 요약

- 집계 대상은 선별을 거친 유효특허 {{meta.n_counted}}건이며, 출원인은 {{meta.n_applicants}}곳입니다.
- 출원 1위는 {{applicants_top.0.name}}({{applicants_top.0.count}}건, {{applicants_top.0.share|pct}})입니다.
- {{meta.unpublished_cutoff}} 이후 출원은 아직 공개되지 않은 것이 많아, 최근 연도의 감소는 실제 감소가 아닐 수 있습니다.

이 문단은 데모용 예시입니다. 실제 분석에서는 park-report 스킬이 stats.json을 읽고 이 파일을 작성합니다.
"""

_APPLICANTS = [
    (["가람에너지 주식회사", "가람에너지(주)", "주식회사 가람에너지"], 30),
    (["누리모빌리티 주식회사"], 18),
    (["다온전지 주식회사", "다온전지(주)"], 15),
    (["한빛대학교 산학협력단"], 10),
    (["Example Power Corp.", "Example Power Corporation"], 8),
    (["미르테크 주식회사"], 6),
    (["한국가상기술연구원"], 6),
    (["소담배터리 주식회사"], 4),
    (["Fictive Cells GmbH"], 3),
]

_TEMPLATES = {
    "A1": (["배터리 {x} 추정 방법 및 장치", "{x} 추정을 위한 배터리 관리 시스템"],
           ["SOC", "SOH", "잔존 수명", "충전 상태"],
           "본 발명은 배터리의 {x}을(를) 추정하는 방법에 관한 것이다. 셀 전압과 전류를 측정하여 {m}에 입력하고 {x}을(를) 산출한다. 이를 통해 추정 오차를 줄일 수 있다.",
           ["확장 칼만 필터", "등가회로 모델", "순환 신경망", "가우시안 프로세스"]),
    "A2": (["배터리 셀 밸런싱 {x}", "{x}를 이용한 셀 밸런싱 장치"],
           ["회로", "제어 방법", "스위칭 장치"],
           "본 발명은 배터리 팩의 셀 간 전압 편차를 줄이는 셀 밸런싱 {x}에 관한 것이다. {m}을(를) 이용하여 에너지를 높은 셀에서 낮은 셀로 이동시킨다.",
           ["인덕터", "플라이백 컨버터", "스위치드 커패시터"]),
    "A3": (["배터리 팩 {x} 시스템", "{x}를 포함하는 전기차 배터리 열관리 장치"],
           ["냉각", "예열", "온도 제어"],
           "본 발명은 배터리 팩의 온도를 관리하는 {x} 시스템에 관한 것이다. {m}을(를) 통해 셀 온도 편차를 줄인다.",
           ["냉각수 유량 제어", "히트 파이프", "PTC 히터"]),
    "A4": (["배터리 {x} 진단 방법", "배터리 {x} 예측 및 차단 장치"],
           ["열폭주", "절연 고장", "내부 단락"],
           "본 발명은 배터리의 {x}을(를) 조기에 진단하는 방법에 관한 것이다. {m}의 신호를 분석하여 이상 징후가 감지되면 경보를 출력하고 전류를 차단한다.",
           ["가스 센서", "절연 저항 측정부", "전압 미분 분석부"]),
    "NOISE": (["{x} 결제 시스템", "{x} 예약 서비스 제공 방법"],
              ["전기차 충전 요금", "충전소"],
              "본 발명은 {x} 결제를 처리하는 서버에 관한 것이다. 사용자 단말로부터 {m} 정보를 수신하여 요금을 정산한다.",
              ["회원 인증", "위치"]),
}

# relative weight of each tech by year index (0 = 2015) — A1 grows fastest
_GROWTH = {"A1": 1.35, "A2": 1.05, "A3": 1.2, "A4": 1.3, "NOISE": 1.0}


def _yearly_counts(rng: random.Random) -> dict[int, int]:
    counts = {}
    for i, y in enumerate(range(2015, 2025)):
        counts[y] = int(18 * (1.28 ** i) + rng.randint(-3, 3))
    counts[2023] = int(counts[2023] * 0.8)   # publication lag
    counts[2024] = int(counts[2024] * 0.25)
    return counts


def generate(seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    names_pool, weights = zip(*_APPLICANTS)
    rows, screen = [], []
    serial = 0
    for year, n in _yearly_counts(rng).items():
        tech_w = {t: g ** (year - 2015) for t, g in _GROWTH.items()}
        techs, tw = zip(*tech_w.items())
        for _ in range(n):
            serial += 1
            tech = rng.choices(techs, tw)[0]
            titles, xs, abstract_t, ms = _TEMPLATES[tech]
            x, mth = rng.choice(xs), rng.choice(ms)
            spellings = rng.choices(names_pool, weights)[0]
            applicants = [rng.choice(spellings)]
            if rng.random() < 0.12:
                co = rng.choice(names_pool)[0]
                if co not in applicants:
                    applicants.append(co)
            month, day = rng.randint(1, 12), rng.randint(1, 28)
            app_no = f"10{year}{serial:07d}"
            granted = year <= 2021 and rng.random() < 0.7
            status = "등록" if granted else rng.choice(["공개", "공개", "거절", "취하"] if year <= 2022 else ["공개"])
            abstract = abstract_t.format(x=x, m=mth)
            rows.append({
                "application_no": app_no,
                "title": rng.choice(titles).format(x=x),
                "abstract": abstract,
                "applicants_raw": "|".join(applicants),
                "ipc": {"A1": "G01R 31/367|H01M 10/48", "A2": "H02J 7/00|H01M 10/44", "A3": "H01M 10/613|H01M 10/625",
                        "A4": "G01R 31/52|H01M 10/48", "NOISE": "G06Q 20/14|G06Q 50/06"}[tech],
                "application_date": f"{year}-{month:02d}-{day:02d}",
                "publication_date": "",
                "registration_date": f"{year + 2}-{month:02d}-{day:02d}" if granted else "",
                "status": status,
                "status_as_of": AS_OF,
                "source": "synthetic",
            })
            first_sentence = abstract.split(". ")[0] + "."
            screen.append({
                "application_no": app_no,
                "relevance": "noise" if tech == "NOISE" else "valid",
                "tech_code": "" if tech == "NOISE" else tech,
                "evidence_level": "provisional",
                "evidence_location": "요약",
                "evidence_quote": first_sentence,
                "rationale": "합성 데이터의 정답 라벨",
                "screened_by": "synthetic-ground-truth",
            })
    from .normalize import norm_ipc
    cand = pd.DataFrame(rows)
    cand["ipc_main"] = cand["ipc"].map(lambda v: norm_ipc(v)[1])
    return conform(cand, CANDIDATE_COLUMNS), conform(pd.DataFrame(screen), SCREENING_COLUMNS)


def write_project(out_dir: str | Path) -> Path:
    from .ingest import finalize
    from .schema import write_csv

    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    cand, screen = generate()
    cand = finalize([cand])
    write_csv(cand, d / "candidates.csv")
    write_csv(screen, d / "screening.csv")
    (d / "TECH_TREE.md").write_text(TECH_TREE_MD, encoding="utf-8")
    (d / "SEARCH_LOG.md").write_text(SEARCH_LOG_MD, encoding="utf-8")
    (d / "REPORT_NOTES.md").write_text(REPORT_NOTES_MD, encoding="utf-8")
    return d
