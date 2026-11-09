"""Dependency-free SVG charts for the patent map.

Charts are plain SVG strings so they render Korean text with the browser's fonts and
follow the report's light/dark theme through CSS variables (--ink, --muted, --grid, --c1...).
"""

from __future__ import annotations

from html import escape

FONT = "font-family:inherit"


def _ticks(vmax: float, n: int = 4) -> list[float]:
    """Integer-friendly ticks from 0 whose last tick is >= vmax (counts are never fractional)."""
    vmax = max(vmax, 1)
    raw = vmax / n
    mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
    steps = (1, 2, 2.5, 5, 10) if mag >= 10 else (1, 2, 5, 10)  # 25, 250… but never 2.5
    step = next(s * mag for s in steps if s * mag >= raw)
    out, t = [0.0], 0.0
    while t < vmax:
        t += step
        out.append(t)
    return out


def _fmt(v: float) -> str:
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"


def bar_by_year(yearly: list[dict], title: str = "") -> str:
    """Vertical bars; years inside the unpublished window are hatched and labelled."""
    if not yearly:
        return ""
    w, h, ml, mr, mt, mb = 640, 300, 48, 12, 28, 40
    pw, ph = w - ml - mr, h - mt - mb
    vmax = max(r["count"] for r in yearly) or 1
    ticks = _ticks(vmax)
    top = ticks[-1] if ticks[-1] >= vmax else vmax
    n = len(yearly)
    bw = pw / n
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" class="chart">',
             '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
             'patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--c1)" opacity=".35"/>'
             '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--c1)" stroke-width="3"/></pattern></defs>']
    for t in ticks:
        y = mt + ph - ph * t / top
        parts.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--grid)"/>')
        parts.append(f'<text x="{ml - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)" style="{FONT}">{_fmt(t)}</text>')
    label_every = max(1, n // 12)
    for i, r in enumerate(yearly):
        x = ml + i * bw + bw * 0.15
        bh = ph * r["count"] / top
        y = mt + ph - bh
        fill = "url(#hatch)" if r["incomplete"] else "var(--c1)"
        tip = f'{r["year"]}: {r["count"]:,}건' + (" (미공개 구간 포함)" if r["incomplete"] else "")
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{bh:.1f}" fill="{fill}" rx="2"><title>{escape(tip)}</title></rect>')
        if n <= 15:
            parts.append(f'<text x="{x + bw * 0.35:.1f}" y="{y - 4:.1f}" text-anchor="middle" font-size="10" fill="var(--ink)" style="{FONT}">{r["count"]:,}</text>')
        if i % label_every == 0:
            parts.append(f'<text x="{x + bw * 0.35:.1f}" y="{h - mb + 16}" text-anchor="middle" font-size="11" fill="var(--muted)" style="{FONT}">{r["year"]}</text>')
    if any(r["incomplete"] for r in yearly):
        parts.append(f'<text x="{w - mr}" y="{mt - 10}" text-anchor="end" font-size="11" fill="var(--muted)" style="{FONT}">빗금: 출원 후 18개월 미공개 구간 포함 — 감소로 해석하지 말 것</text>')
    parts.append("</svg>")
    return "".join(parts)


def _text_width(s: str, size: int = 12) -> float:
    """Rough rendered width: Hangul/CJK ≈ 1 em, Latin ≈ 0.6 em."""
    return sum(size if ord(ch) > 0x1100 else size * 0.6 for ch in s)


def hbar(items: list[tuple[str, int]], title: str = "", max_label: int = 18) -> str:
    """Horizontal ranked bars (top applicants, IPC). The label column grows to fit (up to 300px)."""
    if not items:
        return ""
    labels = [lb if len(lb) <= max_label else lb[: max_label - 1] + "…" for lb, _ in items]
    row, mr, mt = 24, 56, 8
    ml = int(min(300, max(80, max(_text_width(lb) for lb in labels) + 16)))
    w = 640
    h = mt * 2 + row * len(items)
    pw = w - ml - mr
    vmax = max(v for _, v in items) or 1
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" class="chart">']
    for i, (label, v) in enumerate(items):
        y = mt + i * row
        bw = pw * v / vmax
        short = labels[i]
        parts.append(f'<text x="{ml - 8}" y="{y + 16}" text-anchor="end" font-size="12" fill="var(--ink)" style="{FONT}"><title>{escape(label)}</title>{escape(short)}</text>')
        parts.append(f'<rect x="{ml}" y="{y + 4}" width="{max(bw, 1):.1f}" height="{row - 8}" fill="var(--c2)" rx="2"/>')
        parts.append(f'<text x="{ml + bw + 6:.1f}" y="{y + 16}" font-size="11" fill="var(--muted)" style="{FONT}">{v:,}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heatmap(rows: list[str], cols: list[str], values: list[list[int]], title: str = "") -> str:
    """Matrix of counts (tech code × year, applicant × tech code)."""
    if not rows or not cols:
        return ""
    cell, mt = 34, 40
    ml = int(min(220, max(60, max(_text_width(r if len(r) <= 18 else r[:17] + "…") for r in rows) + 16)))
    w = ml + cell * len(cols) + 10
    h = mt + cell * len(rows) + 10
    vmax = max((v for r in values for v in r), default=0) or 1
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" class="chart" style="max-width:{w}px">']
    for j, c in enumerate(cols):
        x = ml + j * cell + cell / 2
        parts.append(f'<text x="{x:.1f}" y="{mt - 8}" text-anchor="middle" font-size="11" fill="var(--muted)" style="{FONT}">{escape(str(c))}</text>')
    for i, r in enumerate(rows):
        y = mt + i * cell
        short = r if len(r) <= 18 else r[:17] + "…"
        parts.append(f'<text x="{ml - 8}" y="{y + cell / 2 + 4:.1f}" text-anchor="end" font-size="12" fill="var(--ink)" style="{FONT}"><title>{escape(r)}</title>{escape(short)}</text>')
        for j, v in enumerate(values[i]):
            x = ml + j * cell
            op = 0.08 + 0.92 * (v / vmax) if v else 0
            parts.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" rx="3" fill="var(--c3)" fill-opacity="{op:.2f}" stroke="var(--grid)"><title>{escape(r)} × {escape(str(cols[j]))}: {v}</title></rect>')
            if v:
                color = "var(--on-c3)" if v / vmax > 0.55 else "var(--ink)"
                parts.append(f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 4:.1f}" text-anchor="middle" font-size="11" fill="{color}" style="{FONT}">{v}</text>')
    parts.append("</svg>")
    return "".join(parts)


def growth_path(points: list[dict], title: str = "") -> str:
    """Connected scatter: x = applicants, y = applications, one point per period."""
    if len(points) < 2:
        return ""
    w, h, ml, mr, mt, mb = 640, 320, 56, 24, 20, 44
    pw, ph = w - ml - mr, h - mt - mb
    xmax = max(p["applicants"] for p in points) or 1
    ymax = max(p["applications"] for p in points) or 1
    xt, yt = _ticks(xmax), _ticks(ymax)
    xtop, ytop = max(xt[-1], xmax), max(yt[-1], ymax)

    def X(v):
        return ml + pw * v / xtop

    def Y(v):
        return mt + ph - ph * v / ytop

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" class="chart">']
    for t in yt:
        parts.append(f'<line x1="{ml}" x2="{w - mr}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--grid)"/>')
        parts.append(f'<text x="{ml - 6}" y="{Y(t) + 4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)" style="{FONT}">{_fmt(t)}</text>')
    for t in xt:
        parts.append(f'<text x="{X(t):.1f}" y="{h - mb + 16}" text-anchor="middle" font-size="11" fill="var(--muted)" style="{FONT}">{_fmt(t)}</text>')
    parts.append(f'<text x="{ml + pw / 2}" y="{h - 6}" text-anchor="middle" font-size="11" fill="var(--muted)" style="{FONT}">출원인 수</text>')
    parts.append(f'<text x="14" y="{mt + ph / 2}" text-anchor="middle" font-size="11" fill="var(--muted)" transform="rotate(-90 14 {mt + ph / 2})" style="{FONT}">출원 건수</text>')
    d = " ".join(f'{"M" if i == 0 else "L"}{X(p["applicants"]):.1f},{Y(p["applications"]):.1f}' for i, p in enumerate(points))
    parts.append(f'<path d="{d}" fill="none" stroke="var(--c1)" stroke-width="2"/>')
    for p in points:
        x, y = X(p["applicants"]), Y(p["applications"])
        fill = "var(--bg)" if p["incomplete"] else "var(--c1)"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}" stroke="var(--c1)" stroke-width="2"><title>{escape(p["period"])}: 출원인 {p["applicants"]}, 출원 {p["applications"]}</title></circle>')
        parts.append(f'<text x="{x + 8:.1f}" y="{y - 8:.1f}" font-size="11" fill="var(--ink)" style="{FONT}">{escape(p["period"])}</text>')
    parts.append("</svg>")
    return "".join(parts)
