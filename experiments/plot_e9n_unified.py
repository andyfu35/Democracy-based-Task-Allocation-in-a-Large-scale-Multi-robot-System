"""E9N presentation owner: one five-algorithm figure for the capacity-one N=T cohort.

Historical E9I/J/L are frozen original 100-seed per-N aggregates; new
Voting Multi-task / CBBA are native freshly executed E9N capacity-one trials.
Publication does not imply equal termination proofs or identical radio stacks.
"""
from __future__ import annotations

import csv
import html
import math
from pathlib import Path

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from experiments.plot_e9m_unified_comparison import validate_legacy_source

OWNER = "experiments.plot_e9n_unified"
COLORS = {"voting_e9i": "#087D85", "cbaa_e9j": "#547EAE",
          "auction_e9l": "#CF7247", "voting_cap1_e9n": "#8446B4",
          "cbba_cap1_e9n": "#298846"}
LABELS = {"voting_e9i": "Voting (E9I)", "cbaa_e9j": "CBAA (E9J)",
          "auction_e9l": "Price Auction (E9L)",
          "voting_cap1_e9n": "Voting Multi-task C1 (E9N)",
          "cbba_cap1_e9n": "Original CBBA C1 (E9N)"}
SIZES = tuple(range(5, 101, 5))


def require_e9n_plot_grid(rows: list[dict]) -> dict[tuple[int, str], dict]:
    """The plotted new algorithms must have complete full N grid, not selected wins."""
    index = {}
    for row in rows:
        try:
            n, method = int(row["robots"]), row["method"]
            if n not in SIZES or method not in ("voting_multitask", "cbba"):
                raise ValueError("unexpected N or method")
            key = (n, method)
            if key in index:
                raise ValueError("duplicate N/method")
            if int(row["total_seeds"]) != 100:
                raise ValueError("not 100 seeds")
            for field in ("mean_all_seed_stop_ms", "mean_all_seed_sender_bytes",
                          "completion_rate"):
                val = float(row[field])
                if not math.isfinite(val) or val < 0:
                    raise ValueError(f"invalid {field}")
            if not 0 <= float(row["completion_rate"]) <= 1:
                raise ValueError("completion outside 0..1")
            index[key] = row
        except (KeyError, ValueError, TypeError) as exc:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="require_e9n_plot_grid", category="contract",
                code="E9N_INVALID_PLOT_ROW", expected="unique N/method 100seed numeric summary",
                actual=row, details=str(exc))) from exc
    expected = {(n, method) for n in SIZES for method in ("voting_multitask", "cbba")}
    if set(index) != expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="require_e9n_plot_grid", category="contract",
            code="E9N_INCOMPLETE_PLOT_GRID", expected=len(expected), actual=len(index),
            details=str(sorted(expected-set(index))[:6])))
    return index


def compose_five_method_rows(legacy: list[dict], new: list[dict]) -> list[dict]:
    """One row per N and method; explicit source and missing-success semantics."""
    indexed = require_e9n_plot_grid(new)
    if [int(row["N"]) for row in legacy] != list(SIZES):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="compose_five_method_rows", category="contract",
            code="E9N_LEGACY_GRID_MISMATCH", expected=SIZES,
            actual=[row.get("N") for row in legacy]))
    rows = []
    for old in legacy:
        n = int(old["N"])
        for method, time_col, byte_col in (
            ("voting_e9i", "voting_time_all_s", "voting_sender_B_all"),
            ("cbaa_e9j", "cbaa_original_time_all_s", "cbaa_original_sender_B_all"),
            ("auction_e9l", "e9l_censored_all_stop_s", "e9l_sender_B_all")):
            rows.append({"robots": n, "tasks": n, "capacity": 1,
                         "method": method, "method_label": LABELS[method],
                         "mean_stop_s": float(old[time_col]),
                         "mean_sender_bytes": float(old[byte_col]),
                         "success_rate": float(old["e9l_successes"]) / 100.0
                             if method == "auction_e9l" else "",
                         "source": "frozen_E9I_J_L_100seeds_per_N",
                         "status": "historically_verified_derived_aggregates"})
        for method, raw_name in (("voting_cap1_e9n", "voting_multitask"),
                                 ("cbba_cap1_e9n", "cbba")):
            data = indexed[(n, raw_name)]
            rows.append({"robots": n, "tasks": n, "capacity": 1,
                         "method": method, "method_label": LABELS[method],
                         "mean_stop_s": float(data["mean_all_seed_stop_ms"]) / 1000,
                         "mean_sender_bytes": float(data["mean_all_seed_sender_bytes"]),
                         "success_rate": float(data["completion_rate"]),
                         "source": "new_E9N_native_100seeds_per_N",
                         "status": "executed_source_pending_independent_audit"})
    return rows


def _render_panel(lines: list[str], rows: list[dict], *, top: int,
                  label: str, field: str, ceiling: float, unit: str,
                  show_missing: bool = False) -> None:
    """Render exactly one pure SVG numerical panel; no external plotting dependency."""
    left, right, height = 100.0, 1140.0, 224.0
    ybottom, ytop = top + height, float(top)
    lines.append(f'<text x="100" y="{top-17}" font-size="20" font-weight="bold" fill="#213547">{html.escape(label)}</text>')
    for j in range(5):
        v = ceiling*j/4
        y = ybottom - j*height/4
        lines.append(f'<line x1="{left}" x2="{right}" y1="{y:.2f}" y2="{y:.2f}" stroke="#E6ECF1"/>')
        lines.append(f'<text x="87" y="{y+5:.2f}" text-anchor="end" font-size="13" fill="#586B7D">{v:g}</text>')
    for n in (5, 25, 50, 75, 100):
        x = left+(n-5)*((right-left)/95)
        lines.append(f'<text x="{x:.1f}" y="{ybottom+19:.1f}" text-anchor="middle" font-size="13" fill="#586B7D">{n}</text>')
    lines.append(f'<text x="620" y="{ybottom+39:.1f}" text-anchor="middle" font-size="13" fill="#607084">Robots = Tasks (capacity 1), 30% loss</text>')
    for method in COLORS:
        chosen = [r for r in rows if r["method"] == method and r[field] != ""]
        if not chosen:
            continue
        pts = []
        for row in chosen:
            n, val = int(row["robots"]), float(row[field])
            v = val/1000 if unit == "kB" else val*(100 if unit == "%" else 1)
            x = left+(n-5)*((right-left)/95)
            y = ybottom-min(v/ceiling, 1.0)*height
            pts.append((x,y))
        if len(pts) > 1:
            dash = ' stroke-dasharray="7 5"' if method in ("voting_e9i","cbaa_e9j","auction_e9l") else ''
            xy = ' '.join(f'{x:.1f},{y:.1f}' for x,y in pts)
            lines.append(f'<polyline points="{xy}" fill="none" stroke="{COLORS[method]}" stroke-width="2.8"{dash}/>')
        for x,y in pts:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{COLORS[method]}"/>')
    if show_missing:
        lines.append(f'<text x="1136" y="{top+18}" text-anchor="end" font-size="12" fill="#697A89">E9I/J complete rates omitted: per-N counts absent in frozen plot source</text>')


def render_five_method_svg(rows: list[dict]) -> str:
    """Chart title and grouped lines intentionally describe model differences."""
    if len(rows) != 100:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="render_five_method_svg", category="contract",
            code="E9N_FIVE_WAY_ROWS_REQUIRED", expected=100, actual=len(rows)))
    max_time = max(float(r["mean_stop_s"]) for r in rows)
    max_kb = max(float(r["mean_sender_bytes"])/1000 for r in rows)
    ceiling_time = max(10, math.ceil(max_time/10)*10)
    ceiling_kb = max(50, math.ceil(max_kb/500)*500)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1240 1140" role="img" aria-label="Five algorithms, same capacity-one N equals T geometry, three native metrics">',
             '<rect width="1240" height="1140" fill="#fff"/>',
             '<g font-family="Arial,Helvetica,sans-serif">',
             '<text x="73" y="44" fill="#223648" font-size="27" font-weight="bold">Five-algorithm comparison | single task per robot</text>',
             '<text x="75" y="72" fill="#52697C" font-size="15">E9I/J/L frozen original 100seed means (dashed) + E9N newly executed 100seed means (solid)</text>']
    for i,(key, label) in enumerate(LABELS.items()):
        x = 72+(i%3)*386
        y = 108+(i//3)*27
        dash = ' stroke-dasharray="7 5"' if i < 3 else ''
        parts.append(f'<line x1="{x}" x2="{x+31}" y1="{y}" y2="{y}" stroke="{COLORS[key]}" stroke-width="3"{dash}/>')
        parts.append(f'<text x="{x+39}" y="{y+5}" fill="#324A5C" font-size="15">{html.escape(label)}</text>')
    _render_panel(parts, rows, top=220, label="A. Modeled allocation / stop time (seconds)",
                  field="mean_stop_s", ceiling=ceiling_time, unit="s")
    _render_panel(parts, rows, top=510, label="B. Attempted application sender Bytes (decimal kB)",
                  field="mean_sender_bytes", ceiling=ceiling_kb, unit="kB")
    _render_panel(parts, rows, top=800, label="C. Complete assignment under method-specific endpoint (%)",
                  field="success_rate", ceiling=100, unit="%",show_missing=True)
    parts.extend(['<text x="74" y="1105" font-size="12" fill="#596D7D">Not equal end guarantees: Voting paid Commit; CBAA / Auction / CBBA modeled optimistic local / observer stop.</text>',
                  '<text x="74" y="1124" font-size="12" fill="#596D7D">Rady ROS delay samples + assumed 144Mbps shared radio, not physical Wi-Fi; frozen vs new runs use different code commits.</text>',
                  '</g></svg>'])
    return '\n'.join(parts)+'\n'


def write_five_method_table(path: Path, rows: list[dict]) -> None:
    """Keep original means and cohort IDs visible outside SVG."""
    fields=("robots","tasks","capacity","method","method_label","mean_stop_s",
            "mean_sender_bytes","success_rate","source","status")
    with path.open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
