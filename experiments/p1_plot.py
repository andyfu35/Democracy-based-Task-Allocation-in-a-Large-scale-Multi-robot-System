"""Pure P1 five-native-method comparison SVG: never changes experimental values."""
from __future__ import annotations

from xml.sax.saxutils import escape

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.p1_plot"
METHODS = ("voting", "cbaa", "price_auction", "voting_multitask", "cbba")
COLORS = ("#2576B5", "#B46A21", "#9064AA", "#159583", "#D74E47")
LABELS = ("Voting", "Original CBAA", "Price Auction", "Voting Multi-task", "Original CBBA")


def validate_plot_source(summary: list[dict], quality: list[dict]) -> None:
    expected={(n,m) for n in (25,50,100) for m in METHODS}
    for rows, name in ((summary,"summary"),(quality,"quality")):
        seen={(int(r["robots"]),r["method"]) for r in rows}
        if seen!=expected or len(rows)!=len(expected):
            raise ProtocolError(Diagnostic(
                OWNER,"validate_plot_source","contract","P1_FIGURE_SOURCE_GRID_INCOMPLETE",
                expected={"source":name,"keys":15},
                actual={"rows":len(rows),"keys":len(seen)}))


def _panel(rows: list[dict], key: str, title: str,
           x: int, y: int, max_height: int, fmt_unit: str) -> list[str]:
    """Only scale numeric confirmed values; gaps are visibly missing evidence."""
    left, right = x+72, x+585
    top, bot = y+50, y+max_height-54
    numbers=[float(r[key]) for r in rows if r.get(key) not in ("",None)]
    maximum=max(numbers)*1.1 if numbers else 1
    maximum=max(maximum,1e-9)
    out=[f'<text x="{x+3}" y="{y+24}" font-size="19" font-weight="bold">{escape(title)}</text>']
    for step in range(5):
        yy=bot-(bot-top)*step/4
        val=maximum*step/4
        label=f"{val:.2f}" if maximum<100 else f"{val:.0f}"
        out.append(f'<line x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#E0E6EB"/>')
        out.append(f'<text x="{left-11}" y="{yy+5:.1f}" text-anchor="end" font-size="13" fill="#586779">{label}</text>')
    for n in (25,50,100):
        xx=left+(n-25)/(100-25)*(right-left)
        out.append(f'<text x="{xx:.1f}" y="{bot+23}" font-size="14" text-anchor="middle">{n}</text>')
    out.append(f'<text x="{(left+right)/2:.1f}" y="{bot+45}" font-size="14" text-anchor="middle">Robots = Tasks; capacity one</text>')
    for i, method in enumerate(METHODS):
        vals=[next(r for r in rows if int(r["robots"])==n and r["method"]==method) for n in (25,50,100)]
        pts=[]
        for n,r in zip((25,50,100),vals):
            v=r.get(key)
            if v in ("",None):
                if len(pts)>1:
                    out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COLORS[i]}" stroke-width="3"/>')
                pts=[]
                continue
            xx=left+(n-25)/(100-25)*(right-left)
            yy=bot-float(v)/maximum*(bot-top)
            pts.append(f'{xx:.1f},{yy:.1f}')
            out.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="3.4" fill="{COLORS[i]}"/>')
        if len(pts)>1:
            out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COLORS[i]}" stroke-width="3"/>')
    out.append(f'<text x="{x+5}" y="{y+max_height-5}" fill="#66768A" font-size="12">{escape(fmt_unit)}</text>')
    return out


def render_p1_figure(summary: list[dict], quality: list[dict]) -> str:
    validate_plot_source(summary,quality)
    time=[dict(r,mean_all_seed_native_stop_ms=(float(r["mean_all_seed_native_stop_ms"])/1000 if r["mean_all_seed_native_stop_ms"]!="" else "")) for r in summary]
    first=[dict(r,mean_first_feasible_ms_when_seen=(float(r["mean_first_feasible_ms_when_seen"])/1000 if r["mean_first_feasible_ms_when_seen"]!="" else "")) for r in summary]
    payload=[dict(r,mean_all_seed_sender_bytes=(float(r["mean_all_seed_sender_bytes"])/1000 if r["mean_all_seed_sender_bytes"]!="" else "")) for r in summary]
    xml=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 1050" role="img" aria-label="P1 same geometry five native algorithms. Four-panel source verified figure">',
         '<rect width="1440" height="1050" fill="white"/>',
         '<g font-family="Arial,Helvetica,sans-serif" fill="#203445">',
         '<text x="50" y="48" font-size="30" font-weight="bold">D. Matched original five-algorithm evaluation</text>',
         '<text x="50" y="80" font-size="17">N = 25 / 50 / 100 · tasks = robots · capacity 1 · packet loss 30% · 100 paired seeds per N</text>']
    for idx,(color,label) in enumerate(zip(COLORS,LABELS)):
        x=50+idx*273
        xml.append(f'<line x1="{x}" y1="111" x2="{x+28}" y2="111" stroke="{color}" stroke-width="4"/>')
        xml.append(f'<text x="{x+35}" y="116" font-size="14">{escape(label)}</text>')
    xml.extend(_panel(time,"mean_all_seed_native_stop_ms","A. Native protocol modeled stop (s)",55,158,340,"Native endpoints differ; all-seed only when all timing records exist"))
    xml.extend(_panel(first,"mean_first_feasible_ms_when_seen","B. First globally feasible (s)",770,158,340,"Read-only evaluation; only feasible-observed trials have time"))
    xml.extend(_panel(payload,"mean_all_seed_sender_bytes","C. Attempted sender payload (decimal kB)",55,520,340,"Native application Bytes including dropped attempts"))
    xml.extend(_panel(quality,"mean_hungarian_ratio","D. Euclidean cost / Hungarian optimum",770,520,340,"ONLY same five-way natively successful paired seeds"))
    xml.append('<text x="52" y="902" font-size="16" font-weight="bold">Critical endpoint distinction</text>')
    xml.append('<text x="52" y="930" font-size="15">Voting pays reliable Score/Commit; CBAA/CBBA/Auction have local/observer stopping without equivalent paid finalization.</text>')
    xml.append('<text x="52" y="955" font-size="15">External first feasibility is read-only and MUST NOT terminate an algorithm. Incomplete or unobservable events remain missing, not imputed.</text>')
    xml.append('<text x="52" y="980" font-size="15">Rady application delay plus assumed 144 Mbps medium is a model, not measured 802.11 or deployed multi-robot wireless time.</text>')
    xml.append('</g></svg>\n')
    return "\n".join(xml)
