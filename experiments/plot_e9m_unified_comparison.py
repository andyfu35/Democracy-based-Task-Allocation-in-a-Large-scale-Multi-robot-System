"""Make one evidence-gated, two-workload E9I/J/L + E9M comparison figure.

Do NOT rank values across N=T capacity1 and T=4R capacity4 as paired methods.
Requires corrected E9M 100-seed original raw, summary and manifest. Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import html
import json
import math
from pathlib import Path
import subprocess
from typing import Any

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.plot_e9m_unified_comparison"
LEGACY_BLOB_SHA = "950ea0c2bd28dff280181fcc2f8b58d6db27633a"
VOTE_FIX_COMMIT = "638081b9c040cde5a796a4de83fc3b025fe10b48"
LEGACY_METHODS = (
    ("Voting E9I", "voting_time_all_s", "voting_sender_B_all", "#087d85"),
    ("Original CBAA E9J", "cbaa_original_time_all_s", "cbaa_original_sender_B_all", "#4d7fae"),
    ("Price Auction E9L", "e9l_censored_all_stop_s", "e9l_sender_B_all", "#cf7247"),
)
NEW_METHODS = (("voting_multitask", "Voting Multi-task", "#087d85"),
               ("cbba", "Original CBBA", "#8c5bb9"))
METRIC_COLUMNS = (
    "seed", "method", "success", "rounds", "guard_censored", "covered_tasks",
    "missing_tasks", "duplicate_tasks", "capacity_violations", "sender_bytes",
    "sender_sends", "receiver_attempts", "receiver_delivered", "receiver_dropped",
    "allocation_ms", "total_distance_m", "makespan_s", "discounted_reward",
    "per_phase_ledger", "routes_json",
)


def fail(function: str, category: str, code: str, expected: Any = None,
         actual: Any = None, details: str | None = None) -> None:
    raise ProtocolError(Diagnostic(OWNER, function, category, code,
                                   expected=expected, actual=actual, details=details))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha(path: Path) -> str:
    blob = path.read_bytes()
    return hashlib.sha1(f"blob {len(blob)}\0".encode("ascii") + blob).hexdigest()


def validate_legacy_source(path: Path, *, expected_blob: str = LEGACY_BLOB_SHA
                           ) -> list[dict[str, float]]:
    """Accept only the published 20-size official 3-original-algorithm source."""
    if not path.is_file() or git_blob_sha(path) != expected_blob:
        fail("validate_legacy_source", "dependency", "E9M_LEGACY_SOURCE_IDENTITY",
             expected_blob, git_blob_sha(path) if path.is_file() else "missing")
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"N", "e9l_successes", *[a for _, a, _, _ in LEGACY_METHODS],
                    *[b for _, _, b, _ in LEGACY_METHODS]}
        if not required.issubset(reader.fieldnames or []):
            fail("validate_legacy_source", "data", "E9M_LEGACY_COLUMNS",
                 sorted(required), reader.fieldnames)
        result: list[dict[str, float]] = []
        for row in reader:
            try:
                values = {name: float(row[name]) for name in required}
            except (ValueError, TypeError, KeyError) as exc:
                fail("validate_legacy_source", "data", "E9M_LEGACY_ROW_INVALID",
                     details=str(exc))
            if any(not math.isfinite(v) or v < 0 for v in values.values()):
                fail("validate_legacy_source", "data", "E9M_LEGACY_NONFINITE", actual=row)
            result.append(values)
    if [int(row["N"]) for row in result] != list(range(5, 101, 5)) or any(
        row["N"] != int(row["N"]) or row["e9l_successes"] > 100
        for row in result
    ):
        fail("validate_legacy_source", "contract", "E9M_LEGACY_GRID_INVALID",
             expected="N=5..100 step5, 100 seeds each", actual=[r["N"] for r in result])
    return result


def verify_corrected_git_source(sha: str, *, repo_root: Path) -> None:
    """Reject f347e26 and non-descendants of the audited Vote unicast fix."""
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        fail("verify_corrected_git_source", "data", "E9M_INVALID_SOURCE_GIT_SHA",
             expected="full lowercase 40-character Git SHA", actual=sha)
    try:
        check = subprocess.run(
            ["git", "merge-base", "--is-ancestor", VOTE_FIX_COMMIT, sha],
            cwd=repo_root, check=False, capture_output=True, text=True)
    except OSError as exc:
        fail("verify_corrected_git_source", "dependency", "E9M_GIT_UNAVAILABLE",
             details=str(exc))
    if check.returncode != 0:
        fail("verify_corrected_git_source", "contract", "E9M_UNCORRECTED_VOTE_SOURCE",
             expected=f"source descendant of {VOTE_FIX_COMMIT}", actual=sha,
             details=(check.stderr.strip() or "source predates unicast correction"))


def _read_formal_rows(csv_path: Path) -> list[dict[str, Any]]:
    """Validate exact raw schema, numeric ranges and local SEND/receipt accounting."""
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not set(METRIC_COLUMNS).issubset(reader.fieldnames or []):
            fail("validate_e9m_formal_source", "data", "E9M_RAW_COLUMNS_MISSING",
                 expected=METRIC_COLUMNS, actual=reader.fieldnames)
        out: list[dict[str, Any]] = []
        for idx, row in enumerate(reader):
            try:
                seed = int(row["seed"])
                method = row["method"]
                if method not in {m for m, _, _ in NEW_METHODS}:
                    raise ValueError("unknown method")
                ints = {k: int(row[k]) for k in (
                    "success", "rounds", "guard_censored", "covered_tasks",
                    "missing_tasks", "duplicate_tasks", "capacity_violations",
                    "sender_bytes", "sender_sends", "receiver_attempts",
                    "receiver_delivered", "receiver_dropped")}
                floats = {k: float(row[k]) for k in (
                    "allocation_ms", "total_distance_m", "makespan_s", "discounted_reward")}
                ledger = json.loads(row["per_phase_ledger"])
                routes = json.loads(row["routes_json"])
                if (seed < 0 or ints["success"] not in (0, 1)
                    or ints["guard_censored"] not in (0, 1)
                    or any(v < 0 for v in ints.values())
                    or any(not math.isfinite(v) or v < 0 for v in floats.values())):
                    raise ValueError("invalid numeric range")
                if not isinstance(ledger, dict) or not isinstance(routes, list) or len(routes) != 25:
                    raise ValueError("invalid ledger/routes JSON shape")
                if ints["receiver_attempts"] != ints["receiver_delivered"] + ints["receiver_dropped"]:
                    raise ValueError("receipt attempts mismatch")
                for field in ("sender_sends", "sender_bytes", "receiver_attempts",
                              "receiver_delivered", "receiver_dropped"):
                    if sum(int(stage[field]) for stage in ledger.values()) != ints[field]:
                        raise ValueError(f"phase ledger mismatch: {field}")
                if ints["success"]:
                    if (ints["covered_tasks"] != 100 or ints["missing_tasks"] != 0
                        or ints["duplicate_tasks"] != 0 or ints["capacity_violations"] != 0
                        or sum(len(route) for route in routes) != 100
                        or any(not isinstance(route, list) or len(route) > 4 for route in routes)
                        or sorted(task for route in routes for task in route) != list(range(100))):
                        raise ValueError("successful route violates coverage/capacity")
                out.append({"seed": seed, "method": method, **ints, **floats})
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                fail("validate_e9m_formal_source", "contract", "E9M_INVALID_ORIGINAL_RAW_ROW",
                     expected="physical-ledger consistent row / 25 routes / cap4",
                     actual=f"row={idx+2}", details=str(exc))
    return out


def validate_e9m_formal_source(root: Path, *, repo_root: Path) -> tuple[list[dict], dict]:
    """Verify full 100 paired seeds, unchanged original file SHA and corrected Git."""
    raw, summary, manifest_file = (root / "per_seed_e9m.csv",
                                   root / "summary_e9m.csv", root / "manifest.json")
    if any(not path.is_file() for path in (raw, summary, manifest_file)):
        fail("validate_e9m_formal_source", "dependency", "E9M_FORMAL_FILES_MISSING",
             expected="per_seed_e9m.csv, summary_e9m.csv, manifest.json", actual=str(root))
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        cfg = manifest["configuration"]
        if (manifest["study"] != "E9M" or cfg["robots"] != 25 or cfg["tasks"] != 100
            or cfg["capacity"] != 4 or float(cfg["loss"]) != 0.30
            or cfg["seeds"] != list(range(100))
            or set(cfg["methods"]) != {m for m, _, _ in NEW_METHODS}
            or len(cfg["methods"]) != 2):
            raise ValueError("configuration differs from preregistered E9M cell")
        for path in (raw, summary):
            expected = manifest["sha256"][path.name]
            actual = file_sha256(path)
            if expected != actual:
                fail("validate_e9m_formal_source", "contract", "E9M_EVIDENCE_SHA_MISMATCH",
                     expected, actual, details=path.name)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        fail("validate_e9m_formal_source", "contract", "E9M_MANIFEST_INVALID",
             expected="verified 25R100T cap4 p30 seed0..99 manifest", details=str(exc))
    verify_corrected_git_source(manifest["git_sha"], repo_root=repo_root)
    rows = _read_formal_rows(raw)
    expected_pairs = {(seed, method) for seed in range(100) for method, _, _ in NEW_METHODS}
    pairs = [(r["seed"], r["method"]) for r in rows]
    if len(rows) != 200 or set(pairs) != expected_pairs or len(pairs) != len(set(pairs)):
        fail("validate_e9m_formal_source", "contract", "E9M_INCOMPLETE_PAIRED_100SEED",
             expected="exactly 200 distinct rows for 100 paired seeds", actual=len(rows))
    return rows, manifest


def summarize_formal_e9m(rows: list[dict]) -> dict[str, dict]:
    """All-seed duration/Bytes, actual completion and conditional route quality."""
    result: dict[str, dict] = {}
    for method, _, _ in NEW_METHODS:
        values = [row for row in rows if row["method"] == method]
        completed = [row for row in values if row["success"] == 1]
        def mean(key: str, group: list[dict] = values) -> float | None:
            return sum(float(r[key]) for r in group) / len(group) if group else None
        result[method] = {
            "total": len(values), "completed": len(completed),
            "completion_pct": 100.0 * len(completed) / len(values),
            "mean_all_seed_stop_s": mean("allocation_ms") / 1000.0,
            "mean_sender_B": mean("sender_bytes"),
            "mean_success_route_m": mean("total_distance_m", completed),
            "mean_success_makespan_s": mean("makespan_s", completed),
            "mean_success_discounted_reward": mean("discounted_reward", completed),
            "guard_failures": sum(r["guard_censored"] for r in values),
        }
    return result


def _escape(value: str) -> str:
    return html.escape(str(value), quote=True)


@dataclass
class SvgComposer:
    contents: list[str]

    def text(self, x: float, y: float, s: str, *, size: int = 13,
             color: str = "#263746", anchor: str = "start", weight: str = "normal") -> None:
        self.contents.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" '
                             f'font-size="{size}" text-anchor="{anchor}" '
                             f'font-weight="{weight}">{_escape(s)}</text>')

    def rect(self, x: float, y: float, w: float, h: float, color: str, radius: int = 0) -> None:
        self.contents.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                             f'height="{h:.1f}" rx="{radius}" fill="{color}"/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, *, color: str = "#dfe5e9",
             width: int = 1) -> None:
        self.contents.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                             f'y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"/>')


def _line_panel(svg: SvgComposer, box: tuple[float, float, float, float],
                legacy: list[dict], series: list[tuple[str, str, str]],
                *, title: str, unit: str, divisor: float = 1.0,
                max_hint: float | None = None) -> None:
    x, y, w, h = box
    svg.rect(x, y, w, h, "#ffffff", 10)
    svg.text(x + 15, y + 28, title, size=17, weight="bold")
    left, top, right, bottom = x+54, y+55, x+w-22, y+h-50
    values = [[row[column] / divisor for row in legacy] for _, column, _ in series]
    ymax = max((max(group) for group in values), default=1.0)
    ymax = max(1.0, ymax * 1.13, max_hint or 0.0)
    for i in range(5):
        val = ymax * i / 4
        py = bottom - (bottom-top) * i/4
        svg.line(left,py,right,py)
        svg.text(left-7, py+4, f"{val:.0f}", size=11, color="#637789", anchor="end")
    for tick in (5,25,50,75,100):
        px = left+(right-left)*(tick-5)/95
        svg.text(px,bottom+22,str(tick),size=11,color="#637789",anchor="middle")
    svg.line(left,top,left,bottom,color="#8797a6")
    svg.line(left,bottom,right,bottom,color="#8797a6")
    for label, column, color in series:
        points=[]
        for row in legacy:
            px=left+(right-left)*(row["N"]-5)/95
            py=bottom-(bottom-top)*(row[column]/divisor)/ymax
            points.append(f"{px:.1f},{py:.1f}")
        svg.contents.append(f'<polyline points="{" ".join(points)}" fill="none" '
                            f'stroke="{color}" stroke-width="3" stroke-linecap="round"/>')
    svg.text((left+right)/2,y+h-16,"Robots = Tasks (N)",size=11,anchor="middle",color="#637789")
    svg.text(left,y+h-4,unit,size=10,color="#637789")


def _bar_panel(svg: SvgComposer, box: tuple[float, float, float, float],
               summary: dict[str, dict], field: str, *, title: str,
               fmt: str, divisor: float = 1.0, percent: bool = False) -> None:
    x,y,w,h=box
    svg.rect(x,y,w,h,"#ffffff",10)
    svg.text(x+15,y+28,title,size=17,weight="bold")
    left,top,right,bottom=x+54,y+55,x+w-25,y+h-55
    values=[summary[k][field]/divisor for k,_,_ in NEW_METHODS]
    ymax=100 if percent else max(1.0,max(values)*1.16)
    for i in range(5):
        val=ymax*i/4
        py=bottom-(bottom-top)*i/4
        svg.line(left,py,right,py)
        svg.text(left-6,py+4,f"{val:.0f}",size=11,color="#637789",anchor="end")
    svg.line(left,bottom,right,bottom,color="#8797a6")
    bar_width=72
    for j, (key,label,color) in enumerate(NEW_METHODS):
        pos=left+(right-left)*(j+0.5)/2
        val=values[j]
        ytop=bottom-(bottom-top)*val/ymax
        svg.rect(pos-bar_width/2,ytop,bar_width,bottom-ytop,color,5)
        svg.text(pos,ytop-8,format(val,fmt),size=12,weight="bold",anchor="middle")
        svg.text(pos,bottom+23, "Multi Voting" if j==0 else "CBBA",size=12,anchor="middle")
    svg.text(left,y+h-10,"100 paired seeds · 25 robots / 100 tasks / cap4",size=10,color="#637789")


def render_unified_svg(legacy: list[dict[str, float]], summary: dict[str, dict],
                       *, git_sha: str) -> str:
    """One figure, two distinctly labeled workloads; no cross-workload ranking."""
    svg=SvgComposer([])
    svg.contents.append('<svg xmlns="http://www.w3.org/2000/svg" width="1340" '
                        'height="1100" viewBox="0 0 1340 1100" role="img" '
                        'aria-label="Five task allocation algorithms, two noncomparable workloads: '
                        'old capacity-one scaling versus multi-task capacity-four">')
    svg.rect(0,0,1340,1100,"#f1f4f6")
    svg.text(47,48,"Task allocation algorithms | communication and modeled speed",size=27,weight="bold")
    svg.text(47,77,"Two experimental workloads; compare algorithms WITHIN each row only (30% receiver loss)",size=17,color="#5b7180")
    for i,(label,_,_,color) in enumerate(LEGACY_METHODS):
        x=52+ i*270
        svg.rect(x,99,17,11,color,2)
        svg.text(x+24,110,label,size=14)
    svg.rect(896,99,17,11,"#8c5bb9",2)
    svg.text(920,110,"Original CBBA E9M",size=14)
    svg.rect(38,132,1264,414,"#e8f0f3",12)
    svg.text(52,162,"A. ORIGINAL SINGLE-TASK CAPACITY · N robots = N tasks · E9I / E9J / E9L",size=18,weight="bold")
    svg.text(52,183,"Historical verified 20-point series · each N has 100 seeds · E9L 160-round censor included",size=13,color="#607482")
    series_time=[(label,key,color) for label,key,_,color in LEGACY_METHODS]
    series_bytes=[(label,key,color) for label,_,key,color in LEGACY_METHODS]
    boxes=[(52,200,391,325),(458,200,391,325),(864,200,391,325)]
    _line_panel(svg,boxes[0],legacy,series_time,title="Modeled allocation / stop time",unit="All-seed mean, seconds")
    _line_panel(svg,boxes[1],legacy,series_bytes,title="Attempted sender payload",unit="All-seed mean, decimal kB",divisor=1000.0)
    _line_panel(svg,boxes[2],legacy,[("E9L", "e9l_successes", "#cf7247")],
                title="E9L completed out of 100",unit="E9I/J per-N counts not in this source",max_hint=100)
    svg.rect(38,563,1264,414,"#e9edf5",12)
    svg.text(52,593,"B. MULTI-TASK CAPACITY · 25 robots / 100 tasks / cap4 · E9M",size=18,weight="bold")
    svg.text(52,614,"Corrected Vote unicast source · same 100 seeds for both methods · winner-only Vote receipt",size=13,color="#607482")
    new_boxes=[(52,632,391,324),(458,632,391,324),(864,632,391,324)]
    _bar_panel(svg,new_boxes[0],summary,"mean_all_seed_stop_s",title="Modeled allocation / stop time",fmt=".2f")
    _bar_panel(svg,new_boxes[1],summary,"mean_sender_B",title="Attempted sender payload (kB)",fmt=".1f",divisor=1000)
    _bar_panel(svg,new_boxes[2],summary,"completion_pct",title="Complete assignments (%)",fmt=".0f",percent=True)
    svg.text(44,1011,"IMPORTANT: Different scene size, task capacity, utility and protocol stopping guarantees: no pooled speed ranking.",size=16,weight="bold",color="#a04b40")
    svg.text(44,1038,"E9I Voting pays Commit. E9J CBAA / E9L Price Auction / E9M CBBA use differing observer/local completion checks.",size=13,color="#5b7180")
    svg.text(44,1061,f"E9M source {git_sha[:12]} · E9L official immutable plot source · Rady ROS + assumed 144 Mbps is not physical Wi-Fi.",size=12,color="#5b7180")
    svg.contents.append('</svg>')
    return '\n'.join(svg.contents)+'\n'


def write_unified_outputs(root: Path, legacy: list[dict], summary: dict[str, dict],
                         e9m_manifest: dict, legacy_path: Path, e9m_root: Path) -> tuple[Path, Path]:
    """Never overwrite prior graph evidence; save SVG, five-row CSV, manifest."""
    if root.exists():
        fail("write_unified_outputs", "state", "E9M_UNIFIED_OUTPUT_EXISTS",
             expected="fresh destination", actual=str(root))
    root.mkdir(parents=True)
    svg=root/"unified_method_time_bytes_success.svg"
    svg.write_text(render_unified_svg(legacy,summary,git_sha=e9m_manifest["git_sha"]),encoding="utf-8")
    source=root/"unified_method_comparison_source.csv"
    last=legacy[-1]
    fields=("cohort","algorithm","robots","tasks","capacity","loss","seeds",
            "completed","mean_all_seed_stop_s","mean_sender_kB",
            "mean_success_total_distance_m","mean_success_makespan_s",
            "endpoint","source_git_sha")
    rows=[]
    for label,time_key,bytes_key,_ in LEGACY_METHODS:
        rows.append({"cohort":"E9I/J/L legacy single-task", "algorithm":label,
                     "robots":100,"tasks":100,"capacity":1,"loss":0.3,"seeds":100,
                     "completed":int(last["e9l_successes"]) if "E9L" in label else 100,
                     "mean_all_seed_stop_s":last[time_key],
                     "mean_sender_kB":last[bytes_key]/1000,
                     "mean_success_total_distance_m":"", "mean_success_makespan_s":"",
                     "endpoint":"optimistic local/observer" if "Voting" not in label else "reliable Commit",
                     "source_git_sha":"0e1a091c547b7cc0d545e0707c51138dfa626d5c"})
    for key,label,_ in NEW_METHODS:
        stats=summary[key]
        rows.append({"cohort":"E9M multi-task capacity4","algorithm":label,
                     "robots":25,"tasks":100,"capacity":4,"loss":0.3,"seeds":100,
                     "completed":stats["completed"],
                     "mean_all_seed_stop_s":stats["mean_all_seed_stop_s"],
                     "mean_sender_kB":stats["mean_sender_B"]/1000,
                     "mean_success_total_distance_m":stats["mean_success_route_m"],
                     "mean_success_makespan_s":stats["mean_success_makespan_s"],
                     "endpoint":"optimistic observer/local" if key=="cbba" else "reliable Commit",
                     "source_git_sha":e9m_manifest["git_sha"]})
    with source.open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    record={"study":"E9M unified historical+multi-task DISPLAY ONLY",
            "comparison_contract":"two different cohorts; comparisons only within each row",
            "excluded_method":"E9K Paid CBAA",
            "legacy_plot_git_blob_sha":git_blob_sha(legacy_path),
            "e9m_git_sha":e9m_manifest["git_sha"],
            "e9m_raw_sha256":e9m_manifest["sha256"]["per_seed_e9m.csv"],
            "e9m_summary_sha256":e9m_manifest["sha256"]["summary_e9m.csv"],
            "e9m_input_root":str(e9m_root),
            "files_sha256":{p.name:file_sha256(p) for p in (svg,source)},
            "caution":"Legacy T=R,C1 objective differs from E9M T=4R,C4; no pooled ranking. Different termination guarantees."}
    (root/"unified_method_manifest.json").write_text(json.dumps(record,indent=2)+'\n',encoding="utf-8")
    return svg,source


def main(argv: list[str] | None = None) -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--e9m-root",type=Path,required=True,
                    help="Corrected 100-seed E9M directory with original CSV+SHA manifest")
    ap.add_argument("--output-root",type=Path,required=True,
                    help="NEW directory for the combined SVG and source evidence")
    ap.add_argument("--legacy-source",type=Path,
                    default=Path("docs/figures/e9l_price/formal/three_algorithm_plot_source_20point.csv"))
    args=ap.parse_args(argv)
    repo_root=Path(__file__).resolve().parents[1]
    legacy=validate_legacy_source(args.legacy_source)
    rows,manifest=validate_e9m_formal_source(args.e9m_root,repo_root=repo_root)
    summary=summarize_formal_e9m(rows)
    svg,csv_file=write_unified_outputs(args.output_root,legacy,summary,manifest,args.legacy_source,args.e9m_root)
    print(f"E9M_UNIFIED_PLOT={svg}")
    print(f"E9M_UNIFIED_CSV={csv_file}")
    print("E9M_COMPARISON_CONTRACT=WITHIN_COHORT_ONLY")


if __name__=="__main__":
    main()
