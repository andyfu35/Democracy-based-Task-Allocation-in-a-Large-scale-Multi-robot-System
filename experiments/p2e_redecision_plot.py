"""P2E SVG: paired Proposed first-epoch redecision ablation, six measures."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER="experiments.p2e_redecision_plot"
MODES=("single_round","multi_round")
LABELS=("Proposed (Single-Round)","Proposed (Multi-Round)")
COLORS=("#B65F23","#155EAB")


def validate_p2e_figure_source(summary, losses):
    expected={(loss,mode) for loss in losses for mode in MODES}
    actual=[(int(r["loss_percent"]),r["mode"]) for r in summary]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_p2e_figure_source",
            category="contract",code="P2E_FIGURE_INCOMPLETE_GRID",
            expected=len(expected),actual={"rows":len(actual),"unique":len(set(actual))},
        ))
    for row in summary:
        n=int(row["trials"]); complete=int(row["native_complete"])
        valid_quality=int(row["quality_sample_count"])
        if (not 1<=n<=100 or not 0<=valid_quality<=complete<=n
                or (valid_quality==0
                    and row["mean_success_quality"] not in ("",None))):
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="validate_p2e_figure_source",
                category="contract",code="P2E_FIGURE_INVALID_DENOMINATOR",
                expected="1..100 trials, quality only for native-complete seeds",
                actual=row,
            ))


def _ablation_panel(summary, losses, field, title, note, x, y, *,
                    scale=1.0, lower=None, upper=None, logarithmic=False,
                    baseline=None, quality=False):
    w=504;h=355
    left=x+77;right=x+w-19;top=y+56;bottom=y+h-52
    rows={(int(r["loss_percent"]),r["mode"]):r for r in summary}
    values=[]
    for row in summary:
        value=row.get(field)
        if value in ("",None):
            continue
        try:
            numeric=float(value)*scale
        except (ValueError,TypeError):
            numeric=float("nan")
        if not math.isfinite(numeric) or (logarithmic and numeric<=0):
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="_ablation_panel",
                category="data",code="P2E_INVALID_PLOT_VALUE",
                expected="finite positive value" if logarithmic else "finite value",
                actual={"field":field,"value":value,"mode":row["mode"]},
            ))
        values.append(numeric)
    lo=(min(values)*0.8 if values else .01) if lower is None else lower
    hi=(max(values)*1.15 if values else 1.2) if upper is None else upper
    if baseline is not None:
        lo=min(lo,baseline*0.92)
        hi=max(hi,baseline*1.08)
    hi=max(hi,lo+1e-6)
    if logarithmic:
        lo=max(lo,1e-9)
        domain=math.log10(hi)-math.log10(lo)
        py=lambda v:bottom-(math.log10(v)-math.log10(lo))/domain*(bottom-top)
    else:
        py=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    px=lambda loss:left+loss/90*(right-left)
    xml=[
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" stroke="#C7D4E0" fill="#FBFDFF"/>',
        f'<text x="{x+17}" y="{y+29}" font-weight="bold" font-size="17">{escape(title)}</text>',
    ]
    for tick in range(5):
        fraction=tick/4
        value=(10**(math.log10(lo)+(math.log10(hi)-math.log10(lo))*fraction)
               if logarithmic else lo+(hi-lo)*fraction)
        yy=bottom-(bottom-top)*fraction
        xml.extend([
            f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="#E3EAF1"/>',
            f'<text x="{left-7}" y="{yy+4:.1f}" font-size="11" text-anchor="end" fill="#48586A">{value:.2g}</text>',
        ])
    for loss in range(0,91,10):
        xml.append(f'<text x="{px(loss):.1f}" y="{bottom+19}" font-size="10" text-anchor="middle">{loss}%</text>')
    if baseline is not None:
        yref=py(baseline)
        xml.append(f'<line x1="{left}" x2="{right}" y1="{yref:.1f}" y2="{yref:.1f}" stroke="#000000" stroke-dasharray="8 5" stroke-width="1.9"/>')
    for index,mode in enumerate(MODES):
        points=[]
        def flush():
            if len(points)>=2:
                xml.append(f'<polyline fill="none" stroke="{COLORS[index]}" stroke-width="3" points="{" ".join(points)}"/>')
            points.clear()
        for loss in losses:
            row=rows[(loss,mode)]
            if row.get(field) in ("",None):
                flush()
                if quality and int(row["quality_sample_count"])==0:
                    xml.append(f'<text x="{px(loss):.1f}" y="{top+16+index*15}" fill="{COLORS[index]}" font-size="11" text-anchor="middle">n=0</text>')
                continue
            value=float(row[field])*scale
            xx=px(loss);yy=py(value)
            points.append(f"{xx:.1f},{yy:.1f}")
            xml.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="{3+index:.1f}" fill="{COLORS[index]}" stroke="#fff"/>')
        flush()
    xml.append(f'<text x="{x+15}" y="{y+h-12}" font-size="11" fill="#526174">{escape(note)}</text>')
    return xml


def render_p2e_figure(summary, losses) -> str:
    """Render immutable 2x3 paired ablation panels; n=0 quality always blank."""
    validate_p2e_figure_source(summary,losses)
    xml=[
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1630 910" role="img" aria-label="P2E Proposed single versus multiple decision epochs">',
        '<rect width="1630" height="910" fill="#FFFFFF"/>',
        '<text x="34" y="39" font-size="29" font-weight="bold">P2E · Proposed Method: redecision ablation</text>',
        '<text x="34" y="68" font-size="16" fill="#526174">Same Cost once · same physical first epoch · only max_rounds differs (1 vs 300) · 100R / 100T</text>',
        '<line x1="34" y1="92" x2="65" y2="92" stroke="#B65F23" stroke-width="4"/>',
        '<text x="73" y="97" font-size="15">Proposed (Single-Round)</text>',
        '<line x1="340" y1="92" x2="371" y2="92" stroke="#155EAB" stroke-width="4"/>',
        '<text x="379" y="97" font-size="15">Proposed (Multi-Round)</text>',
        '<line x1="658" y1="92" x2="690" y2="92" stroke="#000000" stroke-dasharray="8 5" stroke-width="2"/>',
        '<text x="698" y="97" font-size="15">Offline full-information reference</text>',
    ]
    cases=[
        ("completion_rate","A. Native full completion","100% offline reference",0,0.0,1.05,False,1.0,False),
        ("mean_task_coverage","B. Task coverage","Committed / 100 tasks (including failures)",1,0.0,1.05,False,None,False),
        ("mean_all_seed_sender_bytes","C. Attempted sender payload (kB)","Includes all lost Cost and Vote SENDs",2,None,None,True,None,False),
        ("mean_all_seed_native_stop_ms","D. Modeled native stop (s)","All seeds; failure stops included",3,None,None,True,None,False),
        ("mean_rounds_executed","E. Native decision epochs","Max one vs max 300 epochs",4,0.0,None,False,None,False),
        ("mean_success_quality","F. Cost / full-info Greedy","quality conditional on native success",5,0.85,None,False,1.0,True),
    ]
    for field,title,note,index,lower,upper,logarithmic,reference,quality in cases:
        x=26+(index%3)*538
        y=123+(index//3)*366
        scale=(.001 if field in ("mean_all_seed_sender_bytes",
                               "mean_all_seed_native_stop_ms") else 1.0)
        xml.extend(_ablation_panel(
            summary,losses,field,title,note,x,y,
            scale=scale,lower=lower,upper=upper,
            logarithmic=logarithmic,baseline=reference,quality=quality,
        ))
    xml.extend([
        '<text x="34" y="870" font-size="14" fill="#445365">All 2,000 formal cells are newly executed on paired scenes; native SEND bytes count even when the receiver drops the packet.</text>',
        '<text x="34" y="892" font-size="14" fill="#445365">Same-seed first-epoch SHA gate · Cost sent once · no Cost/Vote packet retransmission · reliable TASK/Score/Commit modeled.</text>',
        '</svg>',
    ])
    return "\n".join(xml)+"\n"
