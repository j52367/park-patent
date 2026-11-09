"""Build a self-contained REPORT.html from an analysis directory.

Inputs (all optional except candidates.csv and map/stats.json):
  SEARCH_LOG.md    search scope and queries (shown verbatim — the report must state its scope)
  TECH_TREE.md     technology classification
  REPORT_NOTES.md  narrative written by the park-report skill; numbers come from {{placeholders}}
  map/*.svg        charts from `park map`
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import escape
from pathlib import Path

from . import __version__

THEME_CSS = """
:root{--bg:#fbfaf7;--panel:#ffffff;--ink:#1d1d1b;--muted:#6b6a65;--grid:#e6e3dc;--rule:#d9d5cc;
--c1:#2f5d8a;--c2:#3f7f6b;--c3:#2f5d8a;--on-c3:#ffffff;--warn-bg:#fff6e0;--warn-ink:#6b4b00}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;
--muted:#a4a29a;--grid:#34332f;--rule:#3d3c37;--c1:#7fb0de;--c2:#7cc3a8;--c3:#7fb0de;--on-c3:#10202e;--warn-bg:#3a2f12;--warn-ink:#f3d99a}}
:root[data-theme="dark"]{--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--muted:#a4a29a;--grid:#34332f;--rule:#3d3c37;
--c1:#7fb0de;--c2:#7cc3a8;--c3:#7fb0de;--on-c3:#10202e;--warn-bg:#3a2f12;--warn-ink:#f3d99a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 "Pretendard","Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 16px 80px}
h1{font-size:28px;line-height:1.3;margin:0 0 4px}h2{font-size:20px;margin:40px 0 10px;padding-top:12px;border-top:1px solid var(--rule)}
h3{font-size:16px;margin:24px 0 8px}.sub{color:var(--muted);margin:0 0 24px}
.notice{background:var(--warn-bg);color:var(--warn-ink);border-radius:8px;padding:12px 14px;font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.kpi{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:10px 12px}
.kpi b{display:block;font-size:22px}.kpi span{color:var(--muted);font-size:13px}
figure{margin:12px 0 20px;background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:12px;overflow-x:auto}
figcaption{color:var(--muted);font-size:13px;margin-top:6px}
svg.chart{width:100%;height:auto;display:block}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 16px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--rule);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}
code{background:var(--panel);border:1px solid var(--rule);border-radius:4px;padding:0 4px;font-size:13px}
pre{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:12px;overflow-x:auto;font-size:13px}
footer{margin-top:48px;color:var(--muted);font-size:13px}
"""


# ---------------- placeholders ----------------
_PH = re.compile(r"\{\{\s*([\w.\-]+)(?:\s*\|\s*(\w+))?\s*\}\}")


def _lookup(stats: dict, path: str):
    cur = stats
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


def fill_placeholders(text: str, stats: dict) -> tuple[str, list[str]]:
    """{{meta.n_counted}}, {{applicants_top.0.name}}, {{applicants_top.0.share|pct}} → values from stats.json."""
    missing: list[str] = []

    def sub(m):
        path, fmt = m.group(1), m.group(2)
        try:
            v = _lookup(stats, path)
        except (KeyError, IndexError, ValueError, TypeError):
            missing.append(path)
            return f"⟦{path}?⟧"
        if fmt == "pct":
            return f"{float(v) * 100:.1f}%"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)

    return _PH.sub(sub, text), missing


# ---------------- tiny Markdown → HTML (headings, lists, tables, code, bold, links) ----------------
def _inline(s: str) -> str:
    s = escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_html(md: str, shift: int = 1) -> str:
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            lvl = min(len(m.group(1)) + shift, 6)
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
            if body:
                html = "<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in body[0]) + "</tr></thead><tbody>"
                for r in body[1:]:
                    html += "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                out.append(html + "</tbody></table>")
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(t)}</li>" for t in items) + f"</{tag}>")
            continue
        if line.strip():
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|\s*([-*]|\d+\.)\s)", lines[i]):
                para.append(lines[i])
                i += 1
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            continue
        i += 1
    return "\n".join(out)


# ---------------- report ----------------
def _status_note(meta: dict) -> str:
    lo, hi = meta.get("status_as_of_min", ""), meta.get("status_as_of_max", "")
    unknown = meta.get("n_status_as_of_unknown", 0)
    if not lo:
        return "권리 상태 조회일 미상 — 현재 상태와 다를 수 있습니다. 권리 상태를 판단에 쓰려면 다시 조회하세요."
    when = lo if lo == hi else f"{lo} ~ {hi}"
    tail = f" (조회일 미상 {unknown:,}건 포함)" if unknown else ""
    return f"권리 상태 조회일: {when}{tail}. 이후 바뀌었을 수 있습니다."

def _figure(svg_path: Path, caption: str) -> str:
    if not svg_path.exists():
        return ""
    return f"<figure>{svg_path.read_text(encoding='utf-8')}<figcaption>{escape(caption)}</figcaption></figure>"


def _legend(stats: dict) -> str:
    labels = stats.get("tech_labels") or {}
    return " · ".join(f"{k}={v}" for k, v in labels.items())


def build(analysis_dir: str | Path, title: str | None = None) -> tuple[Path, list[str]]:
    d = Path(analysis_dir)
    stats_path = d / "map" / "stats.json"
    if not stats_path.exists():
        raise FileNotFoundError(f"{stats_path} missing — run `park map {d}` first")
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    meta = stats["meta"]
    problems: list[str] = []
    title = title or f"{d.name} 특허 동향 분석"

    def read(name):
        p = d / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    notes = read("REPORT_NOTES.md")
    notes_html = ""
    if notes:
        filled, missing = fill_placeholders(notes, stats)
        problems += [f"REPORT_NOTES.md: unknown placeholder {{{{{m}}}}}" for m in missing]
        from .checks import lint_numbers
        problems += [f"REPORT_NOTES.md {h}" for h in lint_numbers(notes)]
        notes_html = md_to_html(filled)

    basis_label = "유효특허(선별 완료)" if meta["basis"] == "valid" else "전체 후보 (아직 선별 전)"
    coverage_html = ""
    if meta.get("n_unscreened"):
        coverage_html = (f"<p class=\"notice\"><b>선별 범위:</b> 후보 {meta['n_candidates']:,}건 중 "
                         f"{meta.get('n_screened', 0):,}건을 선별했고 {meta['n_unscreened']:,}건은 선별하지 않았습니다. "
                         "아래 수치는 선별한 문헌만 셉니다.")
        if meta.get("tail_sample"):
            coverage_html += (f" 미선별 구간에서 무작위로 {meta['tail_sample']}건을 뽑아 본 결과 {meta['tail_valid']}건이 유효였으므로, "
                              f"미선별 문헌 중 유효특허는 약 {meta['tail_est_valid']:,}건"
                              f"(95% 신뢰구간 {meta['tail_est_low']:,}–{meta['tail_est_high']:,}건)으로 추정됩니다. "
                              + (f"즉 이 보고서는 전체 유효특허의 약 {meta['est_recall'] * 100:.0f}%"
                                 f"({meta['est_recall_low'] * 100:.0f}–{meta['est_recall_high'] * 100:.0f}%)를 담고 있습니다. "
                                 if "est_recall" in meta else "")
                              + "추세·순위 해석에 이 누락을 감안하세요.")
        coverage_html += "</p>"
    kpis = [
        (f"{meta['n_counted']:,}", f"집계 대상 건수 · {basis_label}"),
        (f"{meta['n_candidates']:,}", "검색된 후보 건수"),
        (f"{meta['n_applicants']:,}", "출원인 수 (정규화 후)"),
        (f"{meta['application_date_min'][:4]}–{meta['application_date_max'][:4]}" if meta['application_date_min'] else "–",
     "출원연도 범위"),
    ]
    top_rows = "".join(
        f"<tr><td class='num'>{i + 1}</td><td>{escape(a['name'])}{(' (' + escape(a['nationality']) + ')') if a.get('nationality') else ''}</td><td class='num'>{a['count']:,}</td>"
        f"<td class='num'>{a['share'] * 100:.1f}%</td></tr>"
        for i, a in enumerate(stats["applicants_top"])
    )
    status_rows = "".join(f"<tr><td>{escape(s['status'])}</td><td class='num'>{s['count']:,}</td></tr>" for s in stats["status"])
    m = d / "map"
    search_log = read("SEARCH_LOG.md")
    tech_tree = read("TECH_TREE.md")

    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{THEME_CSS}</style></head><body><main>
<h1>{escape(title)}</h1>
<p class="sub">기준일 {escape(meta['as_of'])} · PARK v{__version__}로 생성 · 생성일 {date.today().isoformat()}</p>
<p class="notice"><b>검토 의견 초안이며 법률 의견이 아닙니다.</b> 이 보고서는 아래 '검색 범위'에 적힌 데이터베이스·기간·검색식 안의 문헌만 다룹니다.
범위 밖 문헌(해외 특허, 논문, 제품 공개 등)은 반영되지 않았으므로 신규성·진보성이나 공백기술을 단정하는 근거로 쓸 수 없습니다.
출원 후 약 18개월 안의 출원({escape(meta['unpublished_cutoff'])} 이후)은 아직 공개되지 않은 것이 많아 실제보다 적게 집계됩니다.</p>
{coverage_html}
<div class="kpis">{"".join(f'<div class="kpi"><b>{escape(v)}</b><span>{escape(k)}</span></div>' for v, k in kpis)}</div>
{('<h2>분석 요약</h2>' + notes_html) if notes_html else ''}
<h2>출원 동향</h2>
{_figure(m / 'yearly.svg', '연도별 출원 건수 (출원일 기준). 빗금 막대는 미공개 구간이 포함된 연도.')}
{('<h2>국가별 동향</h2>' + _figure(m / 'country.svg', '국가(공보 발행국)별 건수') + _figure(m / 'country_by_year.svg', '국가 × 출원연도. 최근 18개월은 미공개 출원이 많아 덜 집계됨') + _figure(m / 'country_by_tech.svg', '국가 × 기술 분류. ' + _legend(stats))) if (m / 'country.svg').exists() else ''}
<h2>주요 출원인</h2>
{_figure(m / 'applicants.svg', f"상위 출원인 (공동출원은 출원인마다 1건씩 집계)")}
<table><thead><tr><th>순위</th><th>출원인</th><th>건수</th><th>비중</th></tr></thead><tbody>{top_rows}</tbody></table>
{('<h2>기술 분류</h2>' + _figure(m / 'tech_by_year.svg', '기술 분류 × 출원연도. ' + _legend(stats)) + _figure(m / 'applicant_by_tech.svg', '주요 출원인 × 기술 분류. ' + _legend(stats))) if (m / 'tech_by_year.svg').exists() else ''}
<h2>IPC 분포</h2>
{_figure(m / 'ipc.svg', '첫 번째 IPC 서브클래스 기준')}
<h2>기술 성장 단계 (참고)</h2>
{_figure(m / 'growth.svg', '구간별 출원인 수와 출원 건수. 속이 빈 점은 미공개 구간 포함. 성장 단계를 단정하는 지표가 아님.')}
<h2>권리 상태</h2>
<table><thead><tr><th>상태</th><th>건수</th></tr></thead><tbody>{status_rows}</tbody></table>
<p class="sub">{escape(_status_note(meta))}</p>
<h2>검색 범위</h2>
{md_to_html(search_log, shift=2) if search_log else '<p class="notice">SEARCH_LOG.md가 없습니다. 검색 범위를 알 수 없는 보고서는 결론에 쓰지 마세요.</p>'}
{('<h2>기술 분류표</h2>' + md_to_html(tech_tree, shift=2)) if tech_tree else ''}
<footer>집계 규칙: 출원번호 기준 중복 제거 · 출원인 이름 정규화 · {escape(meta['counting'])}.
모든 수치는 map/stats.json에서 나왔습니다. PARK (Patent Analysis Research Kit) · Apache-2.0</footer>
</main></body></html>"""
    out = d / "REPORT.html"
    out.write_text(html, encoding="utf-8")
    return out, problems
