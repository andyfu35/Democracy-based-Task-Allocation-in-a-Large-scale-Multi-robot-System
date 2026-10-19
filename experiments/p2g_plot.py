"""P2G source-verified separate large 2x2 SVG figures, no fake cost failures."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.p2g_plot"
FAMILIES = {
    "one_attempt": ("sequential_once", "centralized_one_shot"),
    "repeatable": ("proposed_multi", "cbaa", "cbba", "centralized_retry"),
}
NAMES = {
    "sequential_once": "Proposed: Sequential (one attempt/task)",
    "centralized_one_shot": "Centralized: One Shot",
    "proposed_multi": "Proposed: Batch Global Greedy (multi-round)",
    "cbaa": "Native CBAA",
    "cbba": "Native CBBA",
    "centralized_retry": "Centralized: retry missing Cost + Global Greedy",
}
COLORS = {
    "sequential_once": "#187BB8",
    "centralized_one_shot": "#D27B2B",
    "proposed_multi": "#187BB8",
    "cbaa": "#CE771D",
    "cbba": "#1B9564",
    "centralized_retry": "#8C55A7",
}
PANEL_SPECS = (
    ("completion_rate_percent", "A. Full allocation success", "100 tasks committed / 100 tasks · %", False, True),
    ("cost_increase_percent", "B. Cost increase vs. global Greedy", "Successful complete trials only · signed %", False, True),
    ("mean_stop_s", "C. Communication stop time", "All seeds · modeled seconds (Rady / 144Mbps)", True, False),
    ("mean_sender_kb", "D. Attempted communication payload", "All seeds · kB; sender SEND includes lost frames", True, False),
)


def fail(function, category, code, expected=None, actual=None):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual,
    ))


def validate_p2g_plot_source(rows, losses, family):
    """One exact method/loss cell per family, with strict native success denominator."""
    if family not in FAMILIES:
        fail("validate_p2g_plot_source", "data", "P2G_UNKNOWN_FIGURE_FAMILY",
             tuple(FAMILIES), family)
    expected={(loss,mode) for loss in losses for mode in FAMILIES[family]}
    actual=[(int(r["loss_percent"]),r["method"]) for r in rows]
    if len(actual)!=len(expected) or set(actual)!=expected:
        fail("validate_p2g_plot_source", "contract", "P2G_INCOMPLETE_FIGURE_GRID",
             expected,actual)
    for r in rows:
        try:
            n=int(r["trials"])
            completed=int(r["native_complete"])
            quality_n=int(r["quality_sample_count"])
        except (ValueError,TypeError,KeyError) as e:
            fail("validate_p2g_plot_source", "data", "P2G_INVALID_COUNTS", "integer counts", str(e))
        if not 1<=n<=100 or not 0<=quality_n<=completed<=n:
            fail("validate_p2g_plot_source", "contract", "P2G_INVALID_FIGURE_DENOMINATOR",
                 "1<=n<=100, 0<=quality_n<=complete<=n",r)
        if (quality_n==0) != (r["cost_increase_percent"] in ("",None)):
            fail("validate_p2g_plot_source","contract","P2G_FAKE_OR_MISSING_QUALITY",
                 "blank cost iff quality_n==0",r)
        for field,_,_,positive,_ in PANEL_SPECS:
            value=r.get(field)
            if value in ("",None):
                if field=="cost_increase_percent" and quality_n==0:
                    continue
                fail("validate_p2g_plot_source","contract","P2G_MISSING_FIGURE_METRIC",field,r)
            try:
                num=float(value)
            except (TypeError,ValueError):
                num=float("nan")
            if not math.isfinite(num) or (positive and num<=0):
                fail("validate_p2g_plot_source","data","P2G_INVALID_FIGURE_METRIC",
                     "finite positive" if positive else "finite",{"field":field,"value":value})


def _p2g_panel(rows, losses, methods, field, heading, caption, positive, reference, x, y):
    """One diagnostic-safe SVG panel; break lines at missing successful-cost points."""
    w,h=840,463
    left=x+88; right=x+w-33; top=y+77; bottom=y+h-76
    relevant=[float(r[field]) for r in rows if r[field] not in ("",None)]
    if reference:
        relevant.append(100.0 if field=="completion_rate_percent" else 0.0)
    if field=="completion_rate_percent":
        lo,hi=0.0,105.0
    elif positive:
        lo=max(min(relevant)*0.6,0.001)
        hi=max(relevant)*1.4
    else:
        lo=min(relevant)-max(0.5,(max(relevant)-min(relevant))*.12)
        hi=max(relevant)+max(0.5,(max(relevant)-min(relevant))*.12)
    if hi<=lo:hi=lo+1.0
    if positive:
        delta=math.log10(hi)-math.log10(lo)
        py=lambda v:bottom-(math.log10(v)-math.log10(lo))/delta*(bottom-top)
    else:
        py=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    px=lambda loss:left+(loss-min(losses))/max(1,max(losses)-min(losses))*(right-left)
    xml=[
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#FAFCFF" stroke="#CFDBE5"/>',
        f'<text x="{x+26}" y="{y+35}" font-size="23" font-weight="bold" fill="#172B43">{escape(heading)}</text>',
        f'<text x="{x+26}" y="{y+62}" font-size="15" fill="#526174">{escape(caption)}</text>',
    ]
    for tick in range(5):
        fraction=tick/4
        v=(10**(math.log10(lo)+(math.log10(hi)-math.log10(lo))*fraction)
           if positive else lo+(hi-lo)*fraction)
        yy=bottom-fraction*(bottom-top)
        xml.append(f'<line x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#DFE6EF"/>')
        xml.append(f'<text x="{left-12}" y="{yy+5:.1f}" text-anchor="end" font-size="13" fill="#536276">{v:.3g}</text>')
    if reference:
        ref=100.0 if field=="completion_rate_percent" else 0.0
        yy=py(ref)
        xml.append(f'<line x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#000" stroke-width="1.8" stroke-dasharray="8 6"/>')
    for loss in losses:
        xx=px(loss)
        xml.append(f'<text x="{xx:.1f}" y="{bottom+26}" font-size="13" text-anchor="middle" fill="#526174">{loss}%</text>')
    xml.append(f'<text x="{(left+right)/2:.1f}" y="{bottom+51}" font-size="14" text-anchor="middle" fill="#43536A">Packet loss</text>')
    indexed={(int(r["loss_percent"]),r["method"]):r for r in rows}
    for method in methods:
        color=COLORS[method]
        points=[]
        def flush():
            if len(points)>1:
                xml.append(f'<polyline points="{" ".join(points)}" stroke="{color}" stroke-width="3.4" fill="none"/>')
            points.clear()
        for loss in losses:
            r=indexed[(loss,method)]
            value=r[field]
            if value in ("",None):
                flush()
                continue
            xv=px(loss);yv=py(float(value))
            points.append(f"{xv:.2f},{yv:.2f}")
            n=int(r["quality_sample_count"])
            xml.append(
                f'<circle cx="{xv:.2f}" cy="{yv:.2f}" r="4.5" fill="{color}" stroke="white" stroke-width="1">'
                f'<title>{escape(NAMES[method])} PL{loss}: {float(value):.4f}'
                + (f' (cost successful n={n})' if field=="cost_increase_percent" else '') +
                '</title></circle>'
            )
        flush()
    return xml


def render_p2g_figure(rows, losses, family) -> str:
    """Produce one 1800x1240 large four-panel research figure."""
    validate_p2g_plot_source(rows,losses,family)
    methods=FAMILIES[family]
    title=("P2G Figure 1 · Single attempt per task: sequential Voting vs Centralized"
           if family=="one_attempt" else
           "P2G Figure 2 · Repeatable native communication under packet loss")
    subtitle=("Sequential Global Greedy: at most one Vote round per task; Centralized: one Cost attempt per robot"
              if family=="one_attempt" else
              "Proposed re-votes pending tasks; Centralized retries missing Costs; CBAA/CBBA keep native iterative rules")
    xml=[
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 1240" role="img" aria-label="'+escape(title)+'">',
        '<rect width="1800" height="1240" fill="white"/>',
        f'<text x="38" y="46" font-size="30" font-weight="bold" fill="#132B42">{escape(title)}</text>',
        f'<text x="38" y="78" font-size="17" fill="#526174">{escape(subtitle)}</text>',
    ]
    for i,method in enumerate(methods):
        xx=45+(i%2)*855;yy=106+(i//2)*27
        xml.extend([
            f'<line x1="{xx}" y1="{yy}" x2="{xx+30}" y2="{yy}" stroke="{COLORS[method]}" stroke-width="5"/>',
            f'<text x="{xx+42}" y="{yy+6}" font-size="15">{escape(NAMES[method])}</text>',
        ])
    offset=160 if len(methods)>2 else 139
    for i,(field,heading,caption,positive,reference) in enumerate(PANEL_SPECS):
        xx=34+(i%2)*884
        yy=offset+(i//2)*488
        xml.extend(_p2g_panel(
            rows,losses,methods,field,heading,caption,positive,reference,xx,yy
        ))
    xml.extend([
        '<text x="46" y="1146" font-size="16" fill="#314A64">Cost line points exist only for fully successful, one-to-one feasible seeds; a missing point means n=0, never zero cost.</text>',
        '<text x="46" y="1176" font-size="16" fill="#314A64">Bytes include attempted sender application SENDs even if lost; all-seed stop times include incomplete or guard-stopped runs.</text>',
        '<text x="46" y="1206" font-size="16" fill="#314A64">Simulated Rady + assumed 144Mbps; native CBAA/CBBA convergence differs from paid centralized/Proposed Commit.</text>',
        '</svg>',
    ])
    return "\n".join(xml)+"\n"
