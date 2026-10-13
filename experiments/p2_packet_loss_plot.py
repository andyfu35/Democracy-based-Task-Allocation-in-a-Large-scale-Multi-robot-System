"""P2 reporting only: plot verified four-method packet-loss summary evidence."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.p2_packet_loss_plot"
METHODS = ("voting", "cbaa", "cbba", "price_auction")
LABELS = ("Voting (Global Greedy)", "CBAA", "CBBA", "Price Auction")
COLORS = ("#186FAF", "#B57B22", "#CA5549", "#815AB3")


def validate_plot_source(summary: list[dict], losses: tuple[int, ...]) -> None:
    expected = {(p, m) for p in losses for m in METHODS}
    received = [(int(r["loss_percent"]), r["method"]) for r in summary]
    if len(received) != len(expected) or set(received) != expected:
        raise ProtocolError(Diagnostic(
            OWNER, "validate_plot_source", "contract", "P2_INCOMPLETE_FOUR_METHOD_PLOT",
            expected=len(expected), actual={"row_count": len(received),
                                           "unique": len(set(received))}))
    for r in summary:
        complete = int(r["native_complete"])
        trials = int(r["trials"])
        common = int(r["same_four_success_seeds"])
        if not (trials == 100 and 0 <= common <= complete <= trials):
            raise ProtocolError(Diagnostic(
                OWNER, "validate_plot_source", "contract", "P2_INVALID_PLOT_DENOMINATOR",
                expected="100 trials, 0<=paired<=native_complete<=100", actual=r))
    for loss in losses:
        groups = [int(r["same_four_success_seeds"]) for r in summary
                  if int(r["loss_percent"]) == loss]
        if len(set(groups)) != 1:
            raise ProtocolError(Diagnostic(
                OWNER, "validate_plot_source", "contract", "P2_MISMATCHED_QUALITY_COHORT",
                expected="one common paired seed count per loss", actual={"loss": loss, "counts": groups}))


def panel(rows: list[dict], losses: tuple[int, ...], field: str,
          title: str, unit: str, x: int, y: int,
          *, scale: float = 1.0, floor: float = 0.0,
          cap: float | None = None) -> list[str]:
    width, height = 610, 365
    left, right, top, bottom = x + 84, x + 582, y + 51, y + 310
    numbers = [float(r[field]) * scale for r in rows
               if r.get(field) not in ("", None)]
    maximum = cap if cap is not None else (max(numbers) * 1.08 if numbers else floor + 1)
    maximum = max(maximum, floor + 0.01)
    out = [f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#FAFCFE" stroke="#CBD5DF" rx="10"/>',
           f'<text x="{x+19}" y="{y+29}" font-size="20" font-weight="bold">{escape(title)}</text>']
    for tick in range(5):
        val = floor + (maximum - floor) * tick / 4
        yy = bottom - (bottom - top) * tick / 4
        out.append(f'<line x1="{left}" x2="{right}" y1="{yy:.2f}" y2="{yy:.2f}" stroke="#E1E8EF"/>')
        out.append(f'<text x="{left-8}" y="{yy+4:.2f}" text-anchor="end" font-size="12" fill="#536273">{val:.2f}</text>')
    for pct in range(0, 91, 10):
        xx = left + (right - left) * pct / 90
        out.append(f'<text x="{xx:.1f}" y="{bottom+23}" text-anchor="middle" font-size="12">{pct}%</text>')
    out.append(f'<text x="{x+18}" y="{y+349}" font-size="12" fill="#596D80">{escape(unit)}</text>')
    for idx, method in enumerate(METHODS):
        group = {int(r["loss_percent"]): r for r in rows if r["method"] == method}
        segment: list[str] = []

        def flush() -> None:
            if len(segment) >= 2:
                dashes = (f' stroke-dasharray="6 18" stroke-dashoffset="{idx*6}"'
                          if field == "completion_rate" and idx else "")
                out.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{COLORS[idx]}" stroke-width="2.8"{dashes}/>')
            segment.clear()

        for pct in losses:
            raw = group[pct].get(field)
            if raw in ("", None):
                flush()
                continue
            value = float(raw) * scale
            if not math.isfinite(value):
                raise ProtocolError(Diagnostic(
                    OWNER, "panel", "data", "P2_NONFINITE_PLOT_VALUE",
                    expected="finite number", actual={"loss": pct, "method": method, "field": field}))
            xx = left + (right - left) * pct / 90
            yy = bottom - (value - floor) / (maximum - floor) * (bottom - top)
            yy = min(max(yy, top), bottom)
            segment.append(f"{xx:.2f},{yy:.2f}")
            if field == "completion_rate":
                out.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="{9-2*idx}" fill="none" stroke="{COLORS[idx]}" stroke-width="1.9"/>')
            else:
                out.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="2.9" fill="{COLORS[idx]}"/>')
        flush()
    return out


def render_p2_figure(summary: list[dict], losses: tuple[int, ...]) -> str:
    validate_plot_source(summary, losses)
    xml = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1350 1020" role="img" aria-label="P2 batched Greedy Voting versus three native baselines across 10 packet-loss levels">',
           '<rect width="1350" height="1020" fill="#FFFFFF"/>',
           '<g font-family="Arial,Helvetica,sans-serif" fill="#25394A">',
           '<text x="44" y="43" font-size="30" font-weight="bold">B. Packet-loss robustness — Global Greedy Voting vs native baselines</text>',
           '<text x="44" y="73" font-size="16">100 robots = 100 tasks, capacity 1, 100 paired seeds, 0–90% PL in 10% steps</text>']
    for idx, (label, color) in enumerate(zip(LABELS, COLORS)):
        xx = 48 + idx * 316
        xml.append(f'<line x1="{xx}" x2="{xx+29}" y1="105" y2="105" stroke="{color}" stroke-width="4"/>')
        xml.append(f'<text x="{xx+38}" y="110" font-size="15">{escape(label)}</text>')
    xml.extend(panel(summary, losses, "completion_rate", "A. Native full completion (%)",
                     "Overlaps: dashed overlays + concentric markers; 100 seeds", 40, 133,
                     scale=100.0, cap=100.0))
    xml.extend(panel(summary, losses, "mean_all_seed_native_stop_ms", "B. Modeled native stop (s)",
                     "Only plotted if all 100 time records exist", 699, 133, scale=0.001))
    xml.extend(panel(summary, losses, "mean_all_seed_sender_bytes", "C. Attempted sender payload (kB)",
                     "Decimal kB; includes dropped sends; no imputed Bytes", 40, 519, scale=0.001))
    xml.extend(panel(summary, losses, "mean_same_four_success_hungarian_ratio",
                     "D. Euclidean cost / Hungarian optimum", "Only matched four-way native-success seeds; ratio >= 1",
                     699, 519, floor=1.0))
    xml.extend([
        '<text x="43" y="928" font-size="15" font-weight="bold">Scientific limits and evidence rules</text>',
        '<text x="43" y="952" font-size="14">Voting uses batched Vote/Score and paid Commit; baselines retain native traffic and stop.</text>',
        '<text x="43" y="974" font-size="14">Voting pays reliable Score/Commit; other methods lack equivalent paid global finalization. Times are NOT identical guarantees.</text>',
        '<text x="43" y="996" font-size="14">Rady sampled latency plus assumed 144 Mbps is a simulated proxy, not measured multi-robot Wi-Fi.</text>',
        '</g></svg>'])
    return "\n".join(xml) + "\n"
