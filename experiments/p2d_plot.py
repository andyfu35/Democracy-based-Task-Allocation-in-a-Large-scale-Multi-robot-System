"""P2D publication-only SVG: four native methods + offline Full-Info reference."""
from __future__ import annotations
import math
from xml.sax.saxutils import escape

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.p2d_plot"
METHODS = ("voting", "cbaa", "cbba", "centralized")
LABELS = ("Proposed Method", "CBAA", "CBBA", "Centralized Method")
COLORS = ("#176CB4", "#CE771D", "#189450", "#8652B7")


def validate_p2d_plot_source(summary, losses):
    expected={(p,method) for p in losses for method in METHODS}
    actual=[(int(r["loss_percent"]),r["method"]) for r in summary]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ProtocolError(Diagnostic(
            OWNER,"validate_p2d_plot_source","contract",
            "P2D_INCOMPLETE_FOUR_METHOD_PLOT",
            expected=len(expected), actual={"rows":len(actual),"unique":len(set(actual))},
        ))
    for row in summary:
        completed=int(row["native_complete"])
        quality_n=int(row["quality_sample_count"])
        trials=int(row["trials"])
        if not (trials==100 and 0<=quality_n<=completed<=100):
            raise ProtocolError(Diagnostic(
                OWNER,"validate_p2d_plot_source","contract",
                "P2D_INVALID_SUCCESS_DENOMINATOR",
                expected="trials=100 and 0<=quality_n<=complete<=100",
                actual=row,
            ))
        if (quality_n == 0 and
                row.get("mean_cost_over_full_info_greedy") not in ("",None)):
            raise ProtocolError(Diagnostic(
                OWNER,"validate_p2d_plot_source","contract",
                "P2D_NO_SUCCESS_HAS_FAKE_QUALITY",
                expected="empty when quality_sample_count=0",
                actual=row.get("mean_cost_over_full_info_greedy"),
            ))


def _panel(summary, losses, field, title, subtitle, x, y, *,
           scale=1.0, minimum=None, maximum=None, log_y=False,
           baseline=None, is_quality=False):
    width,height=615,375
    left=x+88; right=x+591; top=y+55; bottom=y+326
    cache={}
    numbers=[]
    for row in summary:
        value=row.get(field)
        if value in ("",None):
            continue
        try:
            measured=float(value)*scale
        except (TypeError,ValueError):
            measured=float("nan")
        if not math.isfinite(measured) or (log_y and measured<=0):
            raise ProtocolError(Diagnostic(
                OWNER,"_panel","data","P2D_NONFINITE_PLOT_VALUE",
                expected="positive finite" if log_y else "finite",
                actual={"method":row["method"],"loss":row["loss_percent"],
                        "field":field,"value":value},
            ))
        numbers.append(measured)
        cache[(int(row["loss_percent"]),row["method"])]=measured
    lo=(min(numbers)*0.8 if numbers else 0.01) if minimum is None else minimum
    hi=(max(numbers)*1.13 if numbers else 1.01) if maximum is None else maximum
    hi=max(hi,lo+1e-6)
    if log_y:
        lo=max(lo,1e-9)
        log_low,log_high=math.log10(lo),math.log10(hi)
        fy=lambda value:bottom-(math.log10(value)-log_low)/(log_high-log_low)*(bottom-top)
    else:
        fy=lambda value:bottom-(value-lo)/(hi-lo)*(bottom-top)
    fx=lambda loss:left+loss/90*(right-left)
    result=[f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#FBFCFE" stroke="#CFD8E3" rx="9"/>',
            f'<text x="{x+16}" y="{y+28}" font-size="19" font-weight="bold">{escape(title)}</text>']
    for i in range(5):
        fraction=i/4
        v=(10**(math.log10(lo)+(math.log10(hi)-math.log10(lo))*fraction)
           if log_y else lo+(hi-lo)*fraction)
        yy=bottom-(bottom-top)*fraction
        result.append(f'<line x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#E1E7EF"/>')
        result.append(f'<text x="{left-7}" y="{yy+4:.1f}" text-anchor="end" fill="#576779" font-size="12">{v:.2g}</text>')
    for loss in range(0,91,10):
        xx=fx(loss)
        result.append(f'<text x="{xx:.1f}" y="{bottom+21}" text-anchor="middle" font-size="11" fill="#425468">{loss}%</text>')
    result.append(f'<text x="{x+17}" y="{y+360}" font-size="12" fill="#52687F">{escape(subtitle)}</text>')
    if baseline is not None and lo<=baseline<=hi:
        yy=fy(baseline)
        result.append(f'<line x1="{left}" x2="{right}" y1="{yy:.2f}" y2="{yy:.2f}" stroke="#000000" stroke-width="2" stroke-dasharray="9 6"/>')
        result.append(f'<text x="{right-3}" y="{max(top+13,yy-7):.1f}" text-anchor="end" fill="#000000" font-size="12">Full-Info Baseline</text>')
    for index,method in enumerate(METHODS):
        points=[]
        def flush():
            if len(points)>=2:
                result.append(f'<polyline fill="none" stroke="{COLORS[index]}" stroke-width="2.8" points="{" ".join(points)}"/>')
            points.clear()
        for loss in losses:
            key=(loss,method)
            if key not in cache:
                flush()
                if is_quality:
                    row=next((r for r in summary if int(r["loss_percent"])==loss
                              and r["method"]==method),None)
                    if row is not None and int(row["quality_sample_count"])==0:
                        xx=fx(loss)
                        result.append(f'<text x="{xx:.1f}" y="{top+15+index*15}" text-anchor="middle" fill="{COLORS[index]}" font-size="11">n=0</text>')
                continue
            value=cache[key]
            xx=fx(loss);yy=fy(value)
            points.append(f"{xx:.2f},{yy:.2f}")
            # concentric markers distinguish exact overlapping completion rates
            result.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="{2.8+0.6*index:.1f}" fill="{COLORS[index]}" stroke="#FFFFFF" stroke-width="0.8"/>')
        flush()
    return result


def render_p2d_figure(summary, losses):
    validate_p2d_plot_source(summary, losses)
    rows=list(summary)
    xml=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1370 1020" role="img" aria-label="P2D native four-method packet-loss comparison with ideal full-information Greedy reference">',
         '<rect width="1370" height="1020" fill="#FFFFFF"/>',
         '<text x="44" y="42" font-size="29" font-weight="bold">P2D. Packet-loss robustness: Proposed vs Centralized Method</text>',
         '<text x="44" y="68" font-size="16" fill="#526174">100 robots × 100 tasks · capacity 1 · 100 matched seeds per loss level · 0–90% receiver loss</text>']
    for index,(name,color) in enumerate(zip(LABELS,COLORS)):
        xx=45+index*248
        xml.extend([f'<line x1="{xx}" x2="{xx+30}" y1="99" y2="99" stroke="{color}" stroke-width="3"/>',
                    f'<text x="{xx+37}" y="104" font-size="14" fill="#303B46">{name}</text>'])
    xml.extend(['<line x1="1040" x2="1073" y1="99" y2="99" stroke="#000000" stroke-width="2" stroke-dasharray="9 6"/>',
                '<text x="1080" y="104" font-size="14">Full-Info Baseline</text>'])
    xml.extend(_panel(rows,losses,"completion_rate","A. Native full completion (%)",
                      "100 trials each; ideal full-info 100%",40,128,
                      minimum=0.0,maximum=1.05,baseline=1.0))
    xml.extend(_panel(rows,losses,"mean_all_seed_native_stop_ms",
                      "B. Modeled native stop (s)",
                      "All seeds, failed/guarded stops included; log Y",710,128,
                      scale=0.001,log_y=True))
    xml.extend(_panel(rows,losses,"mean_all_seed_sender_bytes",
                      "C. Attempted sender payload (kB)",
                      "All emitted SENDs incl. lost Cost; log Y",40,521,
                      scale=0.001,log_y=True))
    xml.extend(_panel(rows,losses,"mean_cost_over_full_info_greedy",
                      "D. Assignment cost / full-info Greedy",
                      "quality conditional on native success; Full-Info = 1",
                      710,521,minimum=0.85,baseline=1.0,is_quality=True))
    xml.extend([
        '<text x="43" y="932" font-size="16" font-weight="bold">Interpretation and limitations</text>',
        '<text x="43" y="956" font-size="14">Full-Info Greedy is an offline reference; it is not a fifth transmitting algorithm or a global optimum.</text>',
        '<text x="43" y="979" font-size="14">Centralized sends remote Cost once with no retries; TASK/assignment/Commit use reliable control assumptions.</text>',
        '<text x="43" y="1000" font-size="14">Modeled stop times are not identical terminal guarantees; Rady delay + hypothetical 144Mbps proxy, not field Wi-Fi.</text>',
        '</svg>'])
    return "\n".join(xml)+"\n"
