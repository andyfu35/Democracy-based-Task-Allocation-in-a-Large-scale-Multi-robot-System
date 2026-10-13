"""E9N same-scene one-task-per-robot study: new CBBA + Voting alongside E9I/J/L.

E9I/J/L are frozen, separately source-attested 100seed per-N aggregates,
NEVER re-run or relabeled as executing native E9N. New CBBA and capacity-one
Voting Multi-task execute on byte-for-byte identical deterministic scenes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.multitask_scenario import generate_multitask_scene
from democracy_mrta.network import (ensure_rady_dataset, load_rady_latency_profile,
                                     validate_packet_loss_probability)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e9m_multitask import FIELDS as E9M_FIELDS, run_e9m_case
from experiments.plot_e9m_unified_comparison import (
    validate_legacy_source, verify_corrected_git_source)
from experiments.plot_e9n_unified import (
    SIZES, compose_five_method_rows, render_five_method_svg, write_five_method_table)

OWNER = "experiments.run_e9n_one_task"
METHODS = ("voting_multitask", "cbba")
ROW_FIELDS = ("robots", "tasks", "capacity", "scene_sha256") + E9M_FIELDS
DEFAULT_LEGACY = Path("docs/figures/e9l_price/formal/three_algorithm_plot_source_20point.csv")
DEFAULT_RADY = Path("data/e9m_rady_perama_range_testing.json")


def fail(function: str, category: str, code: str, *, expected=None, actual=None,
         details: str | None = None) -> None:
    raise ProtocolError(Diagnostic(owner=OWNER, function=function,
                                   category=category, code=code,
                                   expected=expected, actual=actual, details=details))


def parse_e9n_sizes(value: str) -> tuple[int, ...]:
    try:
        sizes = tuple(int(item.strip()) for item in value.split(","))
    except (ValueError, AttributeError) as exc:
        fail("parse_e9n_sizes", "data", "E9N_INVALID_SIZES",
             expected="comma-separated increasing multiples of 5 in [5,100]",
             actual=value, details=str(exc))
    if (not sizes or tuple(sorted(set(sizes))) != sizes
            or any(n < 5 or n > 100 or n % 5 for n in sizes)):
        fail("parse_e9n_sizes", "data", "E9N_INVALID_SIZES",
             expected="unique increasing multiples of 5 in [5,100]",
             actual=sizes)
    return sizes


def validate_e9n_contract(args: argparse.Namespace) -> tuple[int, ...]:
    """Prerecorded formal scope; pilots are labeled pilots, not mixed in formal."""
    sizes = parse_e9n_sizes(args.sizes)
    validate_packet_loss_probability(args.loss)
    if (type(args.seeds) is not int or args.seeds <= 0 or
            type(args.max_rounds) is not int or args.max_rounds <= 0):
        fail("validate_e9n_contract", "data", "E9N_INVALID_RUN_LENGTH",
             expected="positive integer seeds and max_rounds", actual=(args.seeds,args.max_rounds))
    if args.formal and (sizes != SIZES or args.seeds != 100 or args.loss != 0.30
                       or args.max_rounds != 160):
        fail("validate_e9n_contract", "contract", "E9N_FORMAL_CONFIG_FROZEN",
             expected={"sizes":SIZES,"seeds":100,"loss":.30,"guard":160},
             actual={"sizes":sizes,"seeds":args.seeds,"loss":args.loss,
                     "guard":args.max_rounds},
             details="Use --formal only for registered 20N x 100seed cell")
    if not args.formal and args.seeds > 3:
        fail("validate_e9n_contract", "safety", "E9N_SMOKE_TOO_LARGE",
             expected="<=3 seeds or use full --formal contract", actual=args.seeds)
    return sizes


def verify_geometry_identity(scene) -> str:
    """Verify *actual* N=T historical generator yields same robot/task positions."""
    original = generate_e0_scenario(scene.seed, scene.robots, scene.tasks)
    if (scene.capacity != 1 or original.robot_positions != scene.robot_positions
            or original.task_positions != scene.task_positions):
        fail("verify_geometry_identity", "contract", "E9N_SCENE_NOT_IDENTICAL",
             expected="same original E9I/J/L seed robot/task positions and C1",
             actual={"N":scene.robots,"seed":scene.seed,"capacity":scene.capacity})
    content = json.dumps({"robots":scene.robot_positions,
                          "tasks":scene.task_positions},separators=(",",":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def prepare_e9n_output(path: Path) -> None:
    """An original output root is immutable; a retry must use a new root."""
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        fail("prepare_e9n_output", "state", "E9N_OUTPUT_EXISTS",
             expected="new experiment output directory", actual=str(path),
             details=str(exc))


def read_e9n_git_sha() -> str:
    try:
        sha = subprocess.check_output(["git","rev-parse","HEAD"],
                                      text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        fail("read_e9n_git_sha", "dependency", "E9N_GIT_SHA_UNAVAILABLE",details=str(exc))
    if len(sha)!=40 or any(c not in "0123456789abcdef" for c in sha):
        fail("read_e9n_git_sha", "contract", "E9N_GIT_SHA_INVALID",actual=sha)
    return sha


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_e9n_cases(rows: list[dict], sizes: tuple[int, ...], seeds: int) -> list[dict]:
    """All-seed denominator for timing/traffic/success, success-only for quality."""
    result = []
    for n in sizes:
        for method in METHODS:
            cohort = [r for r in rows if r["robots"]==n and r["method"]==method]
            if len(cohort)!=seeds or {r["seed"] for r in cohort}!=set(range(seeds)):
                fail("summarize_e9n_cases", "contract", "E9N_INCOMPLETE_SEED_GRID",
                     expected={"N":n,"method":method,"seeds":seeds},actual=len(cohort))
            completed = [r for r in cohort if r["success"]]
            mean = lambda values, key: sum(float(r[key]) for r in values)/len(values) if values else None
            result.append({
                "robots":n,"tasks":n,"capacity":1,"method":method,
                "total_seeds":len(cohort),"completed_seeds":len(completed),
                "completion_rate":len(completed)/len(cohort),
                "guard_censored_seeds":sum(r["guard_censored"] for r in cohort),
                "mean_all_seed_stop_ms":mean(cohort,"allocation_ms"),
                "mean_all_seed_sender_bytes":mean(cohort,"sender_bytes"),
                "mean_all_seed_sender_sends":mean(cohort,"sender_sends"),
                "mean_success_only_total_distance_m":mean(completed,"total_distance_m"),
                "mean_success_only_makespan_s":mean(completed,"makespan_s"),
                "mean_success_only_discounted_reward":mean(completed,"discounted_reward"),
            })
    return result


def write_e9n_summary(output: Path, summary: list[dict]) -> Path:
    dest=output/"summary_e9n.csv"
    with dest.open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    return dest


def write_e9n_manifest(output: Path, *, git_sha: str, started_utc: str,
                       sizes: tuple[int,...], seeds: int, loss: float, guard: int,
                       legacy_path: Path, profile, formal: bool,
                       additional_files: tuple[Path,...]) -> None:
    """Original input SHA + method/end-point labels in the executed manifest."""
    evidence=[output/"per_seed_e9n.csv",output/"summary_e9n.csv",*additional_files]
    manifest={
        "study":"E9N_single_task_common_N_equal_T_capacity1",
        "status":"formal_native_E9N_two_methods_plus_frozen_E9I_J_L" if formal else "smoke_not_formal",
        "git_sha":git_sha,
        "started_utc":started_utc,"finished_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "configuration":{"robots_and_tasks":sizes,"capacity":1,"seed_ids":list(range(seeds)),
                         "packet_loss":loss,"max_rounds":guard,"world_size_m":100.0,
                         "speed_m_per_s":1.0,"task_service_s":0.0,
                         "wifi_assumed_mbps":144.0,"methods":METHODS},
        "new_algorithms":["Voting Multi-task (E9M implementation, capacity1)",
                          "Original CBBA (E9M implementation, capacity1)"],
        "archival_not_reexecuted_algorithms":["Voting E9I","CBAA E9J",
                                               "Price Auction E9L"],
        "legacy_plot_git_blob_sha":git_blob_sha(legacy_path),
        "legacy_plot_path":str(legacy_path),
        "radio_note":"Rady ROS samples + hypothesized shared 144Mbps; not measured WiFi PHY/MAC",
        "terminal_note":"E9N CBBA modeled observer stopping != Voting reliable paid Commit",
        "endpoint_coverage_note":"E9I/J completion per N unknown from frozen historical plot CSV; never inferred",
        "cross_algorithm_paired_inference":"NOT AVAILABLE from archived per-N aggregate sources",
        "rady":{"source_commit":profile.source_commit,
                "source_blob_sha":profile.source_blob_sha,
                "sample_count":profile.sample_count},
        "sha256":{p.name:sha256_file(p) for p in evidence}
    }
    (output/"manifest_e9n.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")


def git_blob_sha(path: Path) -> str:
    data=path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()


def parse_args(argv: list[str] | None=None) -> argparse.Namespace:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes",default=",".join(map(str,SIZES)))
    parser.add_argument("--seeds",type=int,default=3)
    parser.add_argument("--loss",type=float,default=.30)
    parser.add_argument("--max-rounds",type=int,default=160)
    parser.add_argument("--formal",action="store_true")
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--legacy-source",type=Path,default=DEFAULT_LEGACY)
    return parser.parse_args(argv)


def run_e9n(args: argparse.Namespace) -> list[dict]:
    sizes=validate_e9n_contract(args)
    # Gate original-source identity and corrected Vote code before expensive work.
    legacy=validate_legacy_source(args.legacy_source)
    sha=read_e9n_git_sha()
    verify_corrected_git_source(sha,repo_root=Path(__file__).resolve().parents[1])
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    prepare_e9n_output(args.output_root)
    started=datetime.now(timezone.utc).isoformat()
    rows=[]
    raw=args.output_root/"per_seed_e9n.csv"
    with raw.open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=ROW_FIELDS)
        writer.writeheader()
        f.flush()
        for n in sizes:
            for seed in range(args.seeds):
                scene=generate_multitask_scene(seed,n,n,1)
                scene_sha=verify_geometry_identity(scene)
                for method in METHODS:
                    outcome=run_e9m_case(scene,method,profile,args.loss,args.max_rounds)
                    row={"robots":n,"tasks":n,"capacity":1,
                         "scene_sha256":scene_sha,**outcome}
                    writer.writerow(row)
                    f.flush()
                    os.fsync(f.fileno())
                    rows.append(row)
                    print(f"E9N N={n} seed={seed}/{args.seeds-1} method={method} "
                          f"success={row['success']} coverage={row['covered_tasks']}/{n} "
                          f"time_s={row['allocation_ms']/1000:.3f} "
                          f"bytes={row['sender_bytes']} failure={row['failure_code']}",
                          flush=True)
    summary=summarize_e9n_cases(rows,sizes,args.seeds)
    write_e9n_summary(args.output_root,summary)
    extra=()
    if args.formal:
        combined=compose_five_method_rows(legacy,summary)
        svg=args.output_root/"five_method_common_cap1.svg"
        svg.write_text(render_five_method_svg(combined),encoding="utf-8")
        comparison=args.output_root/"five_method_common_cap1_source.csv"
        write_five_method_table(comparison,combined)
        extra=(svg,comparison)
    write_e9n_manifest(args.output_root,git_sha=sha,started_utc=started,
                       sizes=sizes,seeds=args.seeds,loss=args.loss,guard=args.max_rounds,
                       legacy_path=args.legacy_source,profile=profile,formal=args.formal,
                       additional_files=extra)
    print(f"E9N_RESULTS={args.output_root} GIT_SHA={sha} CASES={len(rows)} "
          f"UNIFIED_FIVE_METHOD={int(args.formal)}",flush=True)
    return rows


def main(argv: list[str]|None=None) -> None:
    args=parse_args(argv)
    rows=run_e9n(args)
    if args.loss==0.0 and any(not r["success"] for r in rows):
        raise SystemExit("E9N_ZERO_LOSS_SMOKE_FAILED: inspect preserved CSV")


if __name__=="__main__":
    main()
