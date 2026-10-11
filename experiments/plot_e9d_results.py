"""Reproducible vector figures from completed E9D/E9E experiment evidence.

This module does NOT simulate or change any robot algorithm. It verifies exact
original per-seed/summary/manifest SHA256 agreement BEFORE displaying data;
SVG line points correspond ONLY to independently sampled p values.
It writes image files into a separate figure directory and NEVER edits README.
Once the user supplies the verified 100-seed archive, the resulting SVGs can
be copied to docs/figures and explicitly published in README via a later change.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from experiments.run_e9d_natural_loss import (
    EXPECTED_METHODS, summarize_e9d_loss_results,
)

OWNER = "experiments.plot_e9d_results"

BLUE = "#2164B5"
ORANGE = "#D07B21"
GREEN = "#19806B"
PURPLE = "#8058B0"
GRAY = "#667586"
FRAME_W, FRAME_H = 1200, 710
X_LEFT, X_RIGHT = 110, 1140
Y_TOP, Y_BOTTOM = 173, 590


def load_e9d_plot_evidence(root: Path):
    """Dependency owner: load complete raw, summary, manifest without guessing."""
    paths = [root / n for n in (
        "per_seed_loss_method.csv", "summary_by_loss.csv", "manifest.json"
    )]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_e9d_plot_evidence",
            category="dependency", code="E9E_PLOT_EVIDENCE_MISSING",
            expected=[str(p) for p in paths], actual=missing,
            details="Do not plot a partial or missing formal run",
        ))
    try:
        with paths[0].open(encoding="utf-8", newline="") as handle:
            raw = list(csv.DictReader(handle))
        with paths[1].open(encoding="utf-8", newline="") as handle:
            summary = list(csv.DictReader(handle))
        manifest = json.loads(paths[2].read_text(encoding="utf-8"))
    except (OSError, csv.Error, ValueError, UnicodeError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_e9d_plot_evidence",
            category="data", code="E9E_PLOT_EVIDENCE_UNREADABLE",
            expected="well-formed E9D CSV and manifest JSON",
            actual=str(exc),
        )) from exc
    return paths, raw, summary, manifest


def verify_e9d_plot_provenance(*, paths, raw, summary, manifest) -> None:
    """Contract owner: hashes, exact seed/p/method coverage and summary parity."""
    expected_methods = set(EXPECTED_METHODS)
    try:
        digests = manifest["sha256"]
        seed_count = int(manifest["seeds"])
        first_seed = int(manifest["first_seed"])
        probs = [float(p) for p in manifest["loss_probabilities"]]
        intended = int(manifest["expected_rows"])
        source = str(manifest["source_git_sha"])
        if (not source or seed_count < 1 or not probs or
            probs != sorted(set(probs)) or
            intended != 2 * len(probs) * seed_count or
            int(manifest["raw_rows"]) != intended or len(raw) != intended):
            raise ValueError("manifest dimensions, SHA, or raw count inconsistent")
        for p in paths[:2]:
            observed = hashlib.sha256(p.read_bytes()).hexdigest()
            if observed != digests[p.name]:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="verify_e9d_plot_provenance",
                    category="contract", code="E9E_PLOT_SHA256_MISMATCH",
                    expected=digests[p.name], actual=observed,
                    details=str(p),
                ))
        coverage = Counter(
            (int(row["seed"]), float(row["loss_probability"]), row["method"])
            for row in raw
        )
        expected_keys = {
            (seed, loss, method)
            for seed in range(first_seed, first_seed + seed_count)
            for loss in probs
            for method in expected_methods
        }
        if set(coverage) != expected_keys or any(n != 1 for n in coverage.values()):
            raise ValueError("missing/duplicate/unrequested raw seed-loss-method cells")
        if (any(int(row["robots"]) != int(manifest["robots"])
                or int(row["tasks"]) != int(manifest["tasks"]) for row in raw)):
            raise ValueError("raw robots/tasks do not match manifest")
        derived = summarize_e9d_loss_results(raw)
        stored = {
            (float(row["loss_probability"]), row["method"]): row
            for row in summary
        }
        if len(stored) != len(derived) or len(summary) != len(derived):
            raise ValueError("summary row count or duplicate p/method differs from raw")
        numeric = (
            "seeds", "full_protocol_result_count", "full_protocol_result_rate",
            "mean_tasks_confirmed", "mean_total_sender_bytes",
            "min_total_sender_bytes", "max_total_sender_bytes",
            "mean_rounds_executed", "guard_hit_count",
        )
        for row in derived:
            actual = stored.get((row["loss_probability"], row["method"]))
            if actual is None or actual["primary_semantics"] != row["primary_semantics"]:
                raise ValueError("summary method/p/semantics not derived from raw")
            for key in numeric:
                if not math.isclose(float(actual[key]), float(row[key]),
                                    abs_tol=1e-6, rel_tol=1e-10):
                    raise ValueError("summary differs from raw for "+key)
            for key in ("cbaa_full_observer_agreement_count",
                        "cbaa_all_locally_certified_count"):
                if str(actual[key]) != str(row[key]):
                    raise ValueError("summary CBAA diagnostic differs from raw")
    except ProtocolError:
        raise
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="verify_e9d_plot_provenance",
            category="contract", code="E9E_PLOT_RAW_SUMMARY_CONTRACT",
            expected="verified SHA256, complete paired cells and summary derived from raw",
            actual=str(exc),
        )) from exc


def prepare_e9d_figure_root(figures: Path) -> None:
    """Figure state owner: never overwrite existing figures or historical raw."""
    if figures.exists() and (not figures.is_dir() or any(figures.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9d_figure_root",
            category="state", code="E9E_PLOT_OUTPUT_NOT_EMPTY",
            expected="new or empty figure directory", actual=str(figures),
        ))


def wilson_interval(positive: int, total: int) -> tuple[float, float]:
    """Pointwise 95% binomial Wilson interval for finite independent seeds."""
    z = 1.959963984540054
    p = positive / total
    denom = 1 + z*z/total
    midpoint = (p + z*z/(2*total))/denom
    half = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denom
    return max(0.0, midpoint-half), min(1.0, midpoint+half)


def build_e9d_plot_series(summary: list[dict[str, str]]) -> dict:
    """Pure report data projection: sampled values only, never interpolation."""
    rows = sorted(summary, key=lambda r: (float(r["loss_probability"]),r["method"]))
    series = {method: {} for method in EXPECTED_METHODS}
    for row in rows:
        p = float(row["loss_probability"])
        series[row["method"]][p] = {
            "seeds": int(row["seeds"]),
            "success": float(row["full_protocol_result_rate"]),
            "success_count": int(row["full_protocol_result_count"]),
            "bytes_mb": float(row["mean_total_sender_bytes"])/1_000_000,
            "mean_tasks": float(row["mean_tasks_confirmed"]),
            "mean_rounds": float(row["mean_rounds_executed"]),
            "guard_rate": int(row["guard_hit_count"])/int(row["seeds"]),
            "observer_rate": (
                int(row["cbaa_full_observer_agreement_count"])/int(row["seeds"])
                if row["method"] == EXPECTED_METHODS[1] else None
            ),
        }
    return series


def render_e9d_svg_chart(
    *,
    title: str, subtitle: str,
    traces: list[dict], y_label: str, footnote: str,
    y_min: float, y_max: float, ticks: tuple[float, ...],
    x_min: float = 0.0, x_max: float = 1.0,
    y_log: bool = False,
) -> str:
    """One source-based SVG line chart, continuous X coordinates and true markers."""
    def clean(text):
        return html.escape(str(text), quote=True)

    def unit_y(value):
        return math.log10(value) if y_log else value

    def cx(p):
        return X_LEFT + (p-x_min)/(x_max-x_min)*(X_RIGHT-X_LEFT)

    y_low, y_high = unit_y(y_min), unit_y(y_max)

    def cy(value):
        return Y_BOTTOM - (unit_y(value)-y_low)/(y_high-y_low)*(Y_BOTTOM-Y_TOP)

    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="710" viewBox="0 0 1200 710" role="img">',
        f'<title>{clean(title)}</title>',
        f'<desc>{clean(subtitle)}. {clean(footnote)}</desc>',
        '<rect x="0" y="0" width="1200" height="710" fill="#ffffff"/>',
        f'<text x="80" y="52" font-family="Arial,sans-serif" font-size="27" font-weight="700" fill="#1b2838">{clean(title)}</text>',
        f'<text x="80" y="81" font-family="Arial,sans-serif" font-size="15" fill="#4e5d6d">{clean(subtitle)}</text>',
    ]
    for i, trace in enumerate(traces):
        lx = 85 + i * 360
        color = trace["color"]
        svg.extend((
            f'<line x1="{lx}" y1="118" x2="{lx+29}" y2="118" stroke="{color}" stroke-width="4"/>',
            f'<circle cx="{lx+14}" cy="118" r="4" fill="{color}"/>',
            f'<text x="{lx+38}" y="123" font-family="Arial,sans-serif" font-size="15" fill="#253548">{clean(trace["label"])}</text>',
        ))
    for value in ticks:
        if value < y_min or value > y_max:
            continue
        y=cy(value)
        label=("%.3g" % value) if y_log else ("%.3g" % (value * 100) if y_max<=1.001 else "%.3g" % value)
        svg.append(f'<line x1="{X_LEFT}" y1="{y:.2f}" x2="{X_RIGHT}" y2="{y:.2f}" stroke="#e3e8ef" stroke-width="1"/>')
        svg.append(f'<text x="{X_LEFT-12}" y="{y+5:.2f}" text-anchor="end" font-family="Arial,sans-serif" font-size="13" fill="#5f6c7b">{clean(label)}</text>')
    step = .05 if x_max-x_min<=.3 else .1
    tick = math.ceil((x_min - 1e-8)/step)*step
    while tick <= x_max + 1e-8:
        x = cx(tick)
        svg.append(f'<line x1="{x:.2f}" y1="{Y_TOP}" x2="{x:.2f}" y2="{Y_BOTTOM}" stroke="#f0f3f6" stroke-width="1"/>')
        svg.append(f'<text x="{x:.2f}" y="{Y_BOTTOM+27}" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" fill="#5f6c7b">{tick*100:.0f}%</text>')
        tick += step
    svg.extend((
        f'<line x1="{X_LEFT}" y1="{Y_BOTTOM}" x2="{X_RIGHT}" y2="{Y_BOTTOM}" stroke="#9ca9b8" stroke-width="1.5"/>',
        f'<line x1="{X_LEFT}" y1="{Y_TOP}" x2="{X_LEFT}" y2="{Y_BOTTOM}" stroke="#9ca9b8" stroke-width="1.5"/>',
        f'<text x="80" y="151" font-family="Arial,sans-serif" font-size="14" font-weight="600" fill="#415467">{clean(y_label)}</text>',
        f'<text x="{(X_LEFT+X_RIGHT)/2:.0f}" y="{Y_BOTTOM+61}" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="#344558">Packet loss probability</text>',
    ))
    for trace in traces:
        selected=[
            (p, value, lo, hi) for p,value,lo,hi in trace["points"]
            if x_min<=p<=x_max and (not y_log or value>0)
        ]
        if len(selected)<1:
            continue
        color=trace["color"]
        if (not y_log and len(selected)>=2
            and all(lo is not None and hi is not None for _,_,lo,hi in selected)):
            polygons=([(cx(p),cy(max(y_min,lo))) for p,_,lo,hi in selected] +
                      [(cx(p),cy(min(y_max,hi))) for p,_,lo,hi in reversed(selected)])
            points=" ".join(f"{x:.2f},{y:.2f}" for x,y in polygons)
            svg.append(f'<polygon points="{points}" fill="{color}" opacity="0.11"/>')
        polyline=" ".join(f"{cx(p):.2f},{cy(value):.2f}" for p,value,_,_ in selected)
        svg.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')
        for p,value,_,_ in selected:
            svg.append(f'<circle cx="{cx(p):.2f}" cy="{cy(value):.2f}" r="3.2" fill="{color}" stroke="#ffffff" stroke-width=".8"/>')
    svg.append(f'<text x="80" y="683" font-family="Arial,sans-serif" font-size="13" fill="#68778a">{clean(footnote)}</text>')
    svg.append("</svg>")
    return "\n".join(svg)+"\n"


def e9d_chart_traces(series: dict, *, field: str, with_wilson: bool=False,
                     cbaa_only: bool=False) -> list[dict]:
    """Trace projection owner; CBAA observer is never relabelled as Commit."""
    info=(
        (EXPECTED_METHODS[0],"Democracy: actual Commit",BLUE),
        (EXPECTED_METHODS[1],"CBAA: local certificate",ORANGE),
    )
    if cbaa_only:
        info=(info[1],)
    output=[]
    for method,label,color in info:
        points=[]
        for p,data in sorted(series[method].items()):
            ci=(wilson_interval(data["success_count"],data["seeds"])
                if with_wilson else (None,None))
            points.append((p,data[field],*ci))
        output.append(dict(label=label,color=color,points=points))
    return output


def e9d_log_ticks(values: list[float]) -> tuple[float,float,tuple[float,...]]:
    """Positive MB log scale includes smallest and largest sampled mean."""
    positive=[x for x in values if x>0]
    if not positive:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="e9d_log_ticks",category="data",
            code="E9E_NO_POSITIVE_BYTES",
            expected="all original methods physically emit at least one TASK packet",
            actual=values,
        ))
    minimum=min(positive)/1.3
    maximum=max(positive)*1.3
    lo=math.floor(math.log10(minimum))
    hi=math.ceil(math.log10(maximum))
    ticks=sorted({
        mult*10**exponent for exponent in range(lo,hi+1)
        for mult in (1,2,5)
        if minimum<=mult*10**exponent<=maximum
    })
    return minimum,maximum,tuple(ticks)


def compose_e9d_figures(series: dict, *, seed_count: int) -> dict[str,str]:
    """Six independently meaningful figures: full curve, zooms, bytes, stops."""
    primary=e9d_chart_traces(series,field="success",with_wilson=True)
    common_note=(f"{seed_count} paired seeds; pointwise Wilson 95% CI; "
                 "CBAA local stop is optimistic, not a distributed Commit")
    plots={
        "e9d_full_success.svg": render_e9d_svg_chart(
            title="Complete protocol outcome vs packet loss",
            subtitle="Democracy genuine Commit vs CBAA per-robot local-receipt certificate",
            traces=primary,y_label="Complete rate (%)",
            footnote=common_note,y_min=0.0,y_max=1.0,
            ticks=(0.0,0.25,0.50,0.75,1.0),
        ),
    }
    probs={p for method in series.values() for p in method}
    if sum(.40<=p<=.65 for p in probs)>=2:
        plots["e9d_democracy_transition.svg"]=render_e9d_svg_chart(
            title="High-resolution transition: 40-65% packet loss",
            subtitle="Only measured probability points, not simulated interpolation",
            traces=primary,y_label="Complete rate (%)",
            footnote=common_note,y_min=0.0,y_max=1.0,
            ticks=(0.0,0.25,0.50,0.75,1.0),
            x_min=.40,x_max=.65,
        )
    cbaa=series[EXPECTED_METHODS[1]]
    observer=[
        (p,v["observer_rate"],None,None)
        for p,v in sorted(cbaa.items())
    ]
    certified=[
        (p,v["success"],None,None)
        for p,v in sorted(cbaa.items())
    ]
    cbaa_diagnostic=[
        dict(label="CBAA: observer agreement",color=GREEN,points=observer),
        dict(label="CBAA: local certificate",color=ORANGE,points=certified),
    ]
    plots["e9d_cbaa_agreement_vs_stop.svg"]=render_e9d_svg_chart(
        title="CBAA agreement is not the same as safe local stopping",
        subtitle="Independent observable and received-peer local certificate diagnostics",
        traces=cbaa_diagnostic,
        y_label="Fraction of paired seeds (%)",
        footnote=f"{seed_count} seeds; no paid decentralized global stop ACK; guard censoring is separate",
        y_min=0.0,y_max=1.0,ticks=(0.0,0.25,0.5,0.75,1.0),
    )
    if sum(.85<=p<=.99 for p in probs)>=2:
        plots["e9d_cbaa_high_loss_zoom.svg"]=render_e9d_svg_chart(
            title="CBAA stopping evidence: 85-99% packet loss",
            subtitle="Separates full observer agreement from local readiness",
            traces=cbaa_diagnostic,y_label="Fraction of seeds (%)",
            footnote="Guard-limited cases are censored; failure to certify != task disagreement",
            y_min=0.0,y_max=1.0,ticks=(0.0,0.25,0.5,0.75,1.0),
            x_min=.85,x_max=.99,
        )
    byte_traces=e9d_chart_traces(series,field="bytes_mb")
    all_bytes=[v["bytes_mb"] for method in series.values() for v in method.values()]
    lo,hi,ticks=e9d_log_ticks(all_bytes)
    plots["e9d_sender_payload.svg"]=render_e9d_svg_chart(
        title="Actual emitted sender-application payload",
        subtitle="Logarithmic MB scale; includes failed or guard-limited attempts",
        traces=byte_traces,y_label="Mean sender Bytes (MB, log scale)",
        footnote="1 MB = 1,000,000 Bytes; not MAC/PHY/ACK airtime; incomplete runs kept",
        y_min=lo,y_max=hi,ticks=ticks,y_log=True,
    )
    guard_traces=e9d_chart_traces(series,field="guard_rate")
    plots["e9d_guard_censoring.svg"]=render_e9d_svg_chart(
        title="Fraction stopped by experimental safety guard",
        subtitle="CBAA iteration guard 160 and Democracy attempt guard 300 by default",
        traces=guard_traces,y_label="Guard-hit rate (%)",
        footnote="A guard stop is censored, NOT proof of a mathematical loss limit",
        y_min=0.0,y_max=1.0,ticks=(0.0,0.25,0.5,0.75,1.0),
    )
    return plots


def write_e9d_figure_evidence(
    *, figure_dir: Path, figures: dict[str,str], manifest: dict,
    raw_path: Path, summary_path: Path,
) -> Path:
    """Figure evidence owner: render reproducible vector files with hashes."""
    figure_dir.mkdir(parents=True,exist_ok=True)
    for name,svg in figures.items():
        (figure_dir/name).write_text(svg,encoding="utf-8")
    trace={
        "source_git_sha": manifest["source_git_sha"],
        "source_raw": str(raw_path),
        "source_summary": str(summary_path),
        "source_raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "source_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "robots": manifest["robots"],"tasks": manifest["tasks"],
        "seeds": manifest["seeds"],"first_seed": manifest["first_seed"],
        "loss_probabilities": manifest["loss_probabilities"],
        "figure_time_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_scope": (
            "original Democracy full Commit versus optimistic CBAA local evidence; "
            "CBAA observer agreement separate; application sender payload only"
        ),
        "figure_sha256": {
            name: hashlib.sha256((figure_dir/name).read_bytes()).hexdigest()
            for name in figures
        },
    }
    output=figure_dir/"figure_manifest.json"
    output.write_text(json.dumps(trace,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return output


def plot_e9d_results(*, run_root: Path, figure_dir: Path | None=None) -> Path:
    """One read-only summary chart orchestration, no README or raw rewrites."""
    paths,raw,summary,manifest=load_e9d_plot_evidence(run_root)
    verify_e9d_plot_provenance(paths=paths,raw=raw,summary=summary,manifest=manifest)
    output=figure_dir if figure_dir is not None else run_root/"figures"
    prepare_e9d_figure_root(output)
    series=build_e9d_plot_series(summary)
    charts=compose_e9d_figures(series,seed_count=int(manifest["seeds"]))
    record=write_e9d_figure_evidence(
        figure_dir=output,figures=charts,manifest=manifest,
        raw_path=paths[0],summary_path=paths[1],
    )
    print("E9E_PLOT_VERIFIED_SOURCE_SHA="+str(manifest["source_git_sha"]))
    print("E9E_PLOT_SEEDS="+str(manifest["seeds"]))
    print("E9E_PLOT_PROBABILITY_POINTS="+str(len(manifest["loss_probabilities"])))
    for name in sorted(charts):
        print("E9E_FIGURE="+str(output/name))
    print("E9E_FIGURE_MANIFEST="+str(record))
    print("E9E_README_STATUS=PENDING_USER_VERIFIED_FORMAL_DATA_AND_REVIEW")
    return record


def main() -> None:
    parser=argparse.ArgumentParser(
        description="Verify complete E9D/E9E raw and draw native SVG curves for README"
    )
    parser.add_argument("--run-root",type=Path,required=True)
    parser.add_argument("--figure-dir",type=Path,default=None)
    args=parser.parse_args()
    plot_e9d_results(run_root=args.run_root,figure_dir=args.figure_dir)


if __name__=="__main__":
    main()
