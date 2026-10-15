"""P1: five ORIGINAL native algorithms, paired C1 scenes, read-only first-feasible.

This orchestrator does NOT make assignments or stop the algorithms. It calls
original owners and independent read-only evaluation at incurred phase bounds.
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
from democracy_mrta.network import (
    BernoulliLossSampler, ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms, estimate_e9j_cbaa_consensus_window_ms,
    estimate_e9l_price_auction_stage_ms, validate_packet_loss_probability,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.multitask_scenario import generate_multitask_scene
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
)
from democracy_mrta.price_auction import simulate_price_auction, PACKET
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler
from experiments.run_e9h_adaptive_deadline import (
    DEFAULT_OLD_FIXED_MS, build_e9h_deadline_schedule,
    run_e9h_original_voting_case,
)
from experiments.run_e9i_cost30_scaling import selected_e9i_arms
from experiments.run_e9j_cbaa_vs_e9i import run_e9j_original_cbaa_case
from experiments.run_e9m_multitask import run_e9m_case
from experiments.p1_feasibility import (
    FirstFeasibleObserver, assess_euclidean_assignment,
    valid_unique_assignment,
)
from experiments.p1_plot import render_p1_figure

OWNER = "experiments.run_p1_matched_five"
SIZES = (25, 50, 100)
METHODS = ("voting", "cbaa", "price_auction", "voting_multitask", "cbba")
DEFAULT_RADY = Path("data/e9m_rady_perama_range_testing.json")
OUTPUT_FIELDS = (
    "robots", "tasks", "capacity", "seed", "scene_sha256", "method", "p_loss",
    "native_success", "native_stop_reason", "native_guard_censored",
    "native_stop_ms", "observer_snapshots", "first_feasible_seen",
    "first_feasible_ms", "first_feasible_cost_m", "first_feasible_hungarian_ratio",
    "final_feasible", "final_total_distance_m", "final_makespan_s",
    "final_hungarian_gap_m", "final_hungarian_ratio", "oracle_total_m",
    "native_sender_sends", "native_sender_bytes", "native_receiver_attempts",
    "native_receiver_drops", "original_traffic_ledger_json", "native_assignment_json",
    "native_diagnostic", "method_contract",
)


def fail(function: str, category: str, code: str, *, expected=None, actual=None,
         details: str = "") -> None:
    raise ProtocolError(Diagnostic(
        OWNER, function, category, code, expected=expected,
        actual=actual, details=details))


def parse_sizes(text: str) -> tuple[int, ...]:
    try:
        values = tuple(int(x.strip()) for x in text.split(","))
    except (ValueError, AttributeError):
        fail("parse_sizes", "data", "P1_INVALID_SIZES",
             expected="increasing subset of 25,50,100", actual=text)
    if not values or tuple(sorted(set(values))) != values or any(n not in SIZES for n in values):
        fail("parse_sizes", "data", "P1_INVALID_SIZES",
             expected="increasing subset of 25,50,100", actual=values)
    return values


def validate_config(args: argparse.Namespace) -> tuple[int, ...]:
    sizes = parse_sizes(args.sizes)
    validate_packet_loss_probability(args.loss)
    if not (type(args.seeds) is int and 1 <= args.seeds <= 100
            and type(args.first_seed) is int and 0 <= args.first_seed
            and args.first_seed + args.seeds <= 100
            and type(args.guard) is int and 1 <= args.guard <= 160
            and type(args.voting_guard) is int and 1 <= args.voting_guard <= 300):
        fail("validate_config", "data", "P1_INVALID_EXPERIMENT_AXES",
             expected="1<=seeds<=100, first_seed+seeds<=100, guard<=160, voting_guard<=300",
             actual=vars(args))
    if args.formal and (sizes != SIZES or args.seeds != 100
                        or args.first_seed != 0 or args.loss != .30
                        or args.guard != 160 or args.voting_guard != 300):
        fail("validate_config", "contract", "P1_FORMAL_CONFIG_NOT_FROZEN",
             expected="N=25,50,100; seeds 0..99; loss=.30; native guards 160/300",
             actual={"sizes": sizes, "seeds": args.seeds, "first_seed": args.first_seed,
                     "loss": args.loss, "guard": args.guard, "voting_guard": args.voting_guard})
    if args.formal and args.methods != ",".join(METHODS):
        fail("validate_config", "contract", "P1_FORMAL_METHOD_SET_CHANGED",
             expected=METHODS, actual=args.methods)
    methods=tuple(args.methods.split(","))
    if not methods or len(methods)!=len(set(methods)) or any(m not in METHODS for m in methods):
        fail("validate_config", "data", "P1_INVALID_METHODS", expected=METHODS, actual=methods)
    return sizes


def ensure_new_output(root: Path) -> None:
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        fail("ensure_new_output", "state", "P1_OUTPUT_EXISTS",
             expected="entirely new evidence directory", actual=str(root))


def read_source_sha() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                      stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        fail("read_source_sha", "dependency", "P1_GIT_SHA_NOT_AVAILABLE")
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        fail("read_source_sha", "contract", "P1_GIT_SHA_INVALID", actual=sha)
    return sha


def scene_sha256(scene) -> str:
    """Ground pair ID in the actual original E0 seeded coordinates, not N alone."""
    payload=json.dumps({"robot_positions":scene.robot_positions,
                        "task_positions":scene.task_positions},separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_one_scene(scene) -> str:
    independent=generate_multitask_scene(scene.seed,scene.num_robots,scene.num_tasks,1)
    if (independent.robot_positions != scene.robot_positions
            or independent.task_positions != scene.task_positions):
        fail("verify_one_scene", "contract", "P1_SCENE_GEOMETRY_NOT_MATCHED",
             expected=scene_sha256(scene),
             actual={"n":scene.num_robots,"seed":scene.seed})
    return scene_sha256(scene)


def run_original_voting(scene, profile, loss: float, voting_guard: int,
                        observer: FirstFeasibleObserver,
                        voting_strategy: str = "greedy_task") -> dict:
    n=scene.num_robots
    arm=next(a for a in selected_e9i_arms() if a[0]=="adaptive_guarded_k1_received")
    schedule=build_e9h_deadline_schedule(profile=profile,robots=n,
                                        design_rate_mbps=144.0,margin_factor=1.0,
                                        voting_strategy=voting_strategy)
    guarded=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=n,total_tasks=n,reference_phy_mbps=144.0)
    oracle=solve_hungarian_assignment(scene.cost_matrix).total_cost
    native=run_e9h_original_voting_case(
        scenario=scene,profile=profile,n=n,seed=scene.seed,p_loss=loss,
        p_vote_loss=loss,rate=144.0,max_rounds=voting_guard,
        fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,arm=arm,
        schedules={1.0:schedule},guarded_cost_ms=guarded,
        oracle_total_cost=oracle,external_observer=observer.observe,
        voting_strategy=voting_strategy)
    return {
        "success":bool(native["full_commit"]),
        "reason":"reliable_full_commit" if native["full_commit"] else "native_guard_or_incomplete",
        "censored":bool(native["guard_hit"]),
        "ms":float(native["allocation_or_stop_ms"]),
        "sends":int(native["total_original_send_count"]),
        "bytes":int(native["total_sender_application_bytes"]),
        "receivers":None,"drops":None,
        "ledger":{"native":{"sender_sends":int(native["total_original_send_count"]),
                          "sender_bytes":int(native["total_sender_application_bytes"]),
                          "cost_receiver_observations":native["cost_remote_receiver_observation_count"],
                          "cost_receiver_drops":native["cost_remote_packet_drop_count"],
                          "vote_receiver_drops":native["vote_remote_packet_drop_count"],
                          "late_vote_deliveries":native["late_remote_vote_delivery_count"]},
                  **({"batch": {
                      "task_announcement_sender_frames": native["task_announcement_sender_frames"],
                      "cost_sender_frames": native["cost_sender_frames"],
                      "vote_sender_frames": native["vote_sender_frames"],
                      "score_sender_frames": native["vote_score_send_count"],
                      "commit_sender_frames": native["commit_send_count"],
                      "phase_timing": native["phase_timing"],
                      "sender_by_phase": native["sender_by_phase"],
                      "first_epoch_sha256": native["first_epoch_sha256"],
                      "rounds_executed": native["rounds_executed"],
                  }} if voting_strategy == "greedy_batch" else {})},
        "contract":(
            "capacity-one Global Greedy: one TASK + one Cost, batched Vote/Score, paid Commit"
            if voting_strategy == "greedy_batch"
            else "paid reliable Score/Commit; original E9I guarded adaptive Cost/Vote"
        )}


def run_original_cbaa(scene, profile, loss: float, guard: int,
                      observer: FirstFeasibleObserver) -> dict:
    oracle=solve_hungarian_assignment(scene.cost_matrix).total_cost
    deadline=estimate_e9j_cbaa_consensus_window_ms(
        profile=profile,robots=scene.num_robots,tasks=scene.num_tasks,
        reference_phy_mbps=144.0)
    native=run_e9j_original_cbaa_case(
        scenario=scene,profile=profile,seed=scene.seed,n=scene.num_robots,
        guard=guard,phase_deadline_ms=deadline,oracle_cost=oracle,
        p_bid_loss=loss,external_observer=observer.observe)
    return {
        "success":bool(native["cbaa_certified_and_observer_full"]),
        "reason":native["cbaa_stop_reason"],
        "censored":bool(native["cbaa_guard_hit"]),
        "ms":float(native["allocation_or_stop_ms"]),
        "sends":int(native["total_original_SENDs"]),
        "bytes":int(native["total_original_sender_bytes"]),
        "receivers":int(native["cbaa_receiver_delivery_attempts"]),
        "drops":int(native["cbaa_receiver_packet_drops"]),
        "ledger":{"TASK":{"sender_bytes":native["task_sender_bytes"]},
                  "CBAA":{"sender_bytes":native["cbaa_bid_sender_bytes"],
                          "receiver_attempts":native["cbaa_receiver_delivery_attempts"],
                          "receiver_drops":native["cbaa_receiver_packet_drops"],
                          "late_receivers":native["cbaa_late_receiver_packets"]}},
        "contract":"local-certificate + unpaid simulator shared halt; no Commit"}


def run_original_auction(scene, profile, loss: float, guard: int,
                         observer: FirstFeasibleObserver) -> dict:
    n=scene.num_robots
    # Same native reliable TASK frame and original seed/PHY as archived E9L.
    task_channel=create_e9g_sampler(profile=profile,seed=scene.seed,phy_rate_mbps=144.0)
    drops=BernoulliLossSampler(seed=scene.seed)
    announced=broadcast_task_information(
        task_positions=scene.task_positions,num_robots=n,
        sampler=task_channel,loss_sampler=drops,p_loss=0.0,
        phase_timeout_ms=1.0e9)
    costs=reconstruct_local_cost_rows(
        local_robot_positions=scene.robot_positions,
        announced_tasks_by_robot=announced.per_robot_tasks)
    require_local_source_consistency(reconstructed=costs,expected=scene.cost_matrix)
    task_ms=max((e.arrival_time_ms for e in announced.events),default=0.0)
    window=estimate_e9l_price_auction_stage_ms(
        profile=profile,robots=n,packet_bytes=PACKET.size,
        reference_phy_mbps=144.0)
    channel=create_e9g_sampler(profile=profile,seed=scene.seed,phy_rate_mbps=144.0)
    native=simulate_price_auction(
        cost_matrix=costs,sampler=channel,loss_sampler=drops,
        bid_loss=loss,award_loss=loss,epsilon=10.0,
        stage_window_ms=window,safety_rounds=guard,
        external_observer=lambda t,p: observer.observe(task_ms+t,p))
    a=task_channel.summarize_network()
    b=channel.summarize_network()
    sent=native.bid_sends+native.award_sends
    expected=(len(announced.events)+sent,announced.sender_bytes+native.sender_bytes)
    actual=(a["packet_count"]+b["packet_count"],
            a["application_sender_bytes"]+b["application_sender_bytes"])
    if (actual!=expected or native.sender_bytes!=PACKET.size*sent
            or native.delivery_attempts != native.bid_sends+(n-1)*native.award_sends):
        fail("run_original_auction", "contract", "P1_AUCTION_PACKET_ACCOUNTING",
             expected=expected,actual=actual,
             details=f"bid_sends={native.bid_sends} award_sends={native.award_sends}")
    complete=bool(native.optimistic_local_stop and native.observer_full
                  and len(native.assignment)==n)
    return {"success":complete,"reason":native.stop_reason,
            "censored":not native.optimistic_local_stop,
            "ms":float(task_ms+native.elapsed_ms),
            "sends":expected[0],"bytes":expected[1],
            "receivers":native.delivery_attempts,"drops":native.delivery_drops,
            "ledger":{"TASK":{"sender_sends":len(announced.events),
                              "sender_bytes":announced.sender_bytes},
                      "AUCTION":{"bid_sends":native.bid_sends,
                                 "award_sends":native.award_sends,
                                 "sender_bytes":native.sender_bytes,
                                 "receiver_attempts":native.delivery_attempts,
                                 "receiver_drops":native.delivery_drops,
                                 "late_deliveries":native.late_deliveries}},
            "contract":"native bidder/home 28-byte BID/AWARD, optimistic unpaid local halt"}


def run_original_multitask(scene, profile, loss: float, guard: int,
                           method: str, observer: FirstFeasibleObserver) -> dict:
    independent=generate_multitask_scene(scene.seed,scene.num_robots,
                                         scene.num_tasks,1)
    native=run_e9m_case(independent,method,profile,loss,guard,
                        external_observer=observer.observe)
    ledger=json.loads(native["per_phase_ledger"])
    return {"success":bool(native["success"]),
            "reason":native["failure_code"] or ("paid_score_commit" if method=="voting_multitask" else "observer_agreement"),
            "censored":bool(native["guard_censored"]),
            "ms":float(native["allocation_ms"]),
            "sends":int(native["sender_sends"]),
            "bytes":int(native["sender_bytes"]),
            "receivers":int(native["receiver_attempts"]),
            "drops":int(native["receiver_dropped"]),"ledger":ledger,
            "contract":("paid reliable Score/Commit" if method=="voting_multitask"
                        else "unpaid external CBBA observer stop")}


def run_matched_case(scene, profile, method: str, loss: float,
                     guard: int, voting_guard: int,
                     voting_strategy: str = "greedy_task") -> dict:
    """Orchestrate native run, then independently certify its emitted snapshots.

    Native protocol failures are preserved per seed. Independent data/time/
    contract violations deliberately propagate with their first failing owner.
    """
    n=scene.num_robots
    digest=verify_one_scene(scene)
    oracle=solve_hungarian_assignment(scene.cost_matrix).total_cost
    observer=FirstFeasibleObserver(n)
    native=None
    native_error=None
    if method not in METHODS:
        fail("run_matched_case", "data", "P1_UNKNOWN_NATIVE_METHOD",
             expected=METHODS,actual=method)
    try:
        if method=="voting":
            native=run_original_voting(scene,profile,loss,voting_guard,observer,
                                       voting_strategy=voting_strategy)
        elif method=="cbaa":
            native=run_original_cbaa(scene,profile,loss,guard,observer)
        elif method=="price_auction":
            native=run_original_auction(scene,profile,loss,guard,observer)
        else:
            native=run_original_multitask(scene,profile,loss,guard,method,observer)
    except ProtocolError as exc:
        if exc.diagnostic.owner in ("experiments.p1_feasibility", OWNER):
            raise  # read-only audit/contract bug is NEVER a method failure
        native_error=exc.diagnostic

    # Check snapshots OUTSIDE the native-exception boundary.
    last=assess_euclidean_assignment(scene.cost_matrix,observer.last_pairs,oracle)
    first=assess_euclidean_assignment(scene.cost_matrix,observer.first_pairs,oracle)
    if native is not None:
        if native["success"] and not last["feasible"]:
            fail("run_matched_case", "contract", "P1_NATIVE_SUCCESS_NOT_EXTERNAL_FEASIBLE",
                 expected="full unique C1 final assignment",actual=observer.last_pairs[:8],
                 details=f"N={n} seed={scene.seed} method={method}")
        if observer.first_feasible_ms is not None and observer.first_feasible_ms>native["ms"]+1e-6:
            fail("run_matched_case", "time", "P1_FIRST_FEASIBLE_AFTER_NATIVE_STOP",
                 expected=f"<= {native['ms']}",actual=observer.first_feasible_ms)
        result={"native_success":int(native["success"]),
                "native_stop_reason":native["reason"],
                "native_guard_censored":int(native["censored"]),
                "native_stop_ms":native["ms"],
                "native_sender_sends":native["sends"],
                "native_sender_bytes":native["bytes"],
                "native_receiver_attempts":native["receivers"] if native["receivers"] is not None else "",
                "native_receiver_drops":native["drops"] if native["drops"] is not None else "",
                "original_traffic_ledger_json":json.dumps(native["ledger"],sort_keys=True),
                "native_diagnostic":"", "method_contract":native["contract"]}
    else:
        # No values are invented after a native exception. A paper must flag
        # incomplete traffic separately rather than averaging blank as zero.
        result={"native_success":0,"native_stop_reason":"native_diagnostic",
                "native_guard_censored":0,"native_stop_ms":"",
                "native_sender_sends":"","native_sender_bytes":"",
                "native_receiver_attempts":"","native_receiver_drops":"",
                "original_traffic_ledger_json":"",
                "native_diagnostic":json.dumps(native_error.__dict__,default=str,sort_keys=True),
                "method_contract":"native error: incomplete physical ledger not imputed"}
    return {
        "robots":n,"tasks":n,"capacity":1,"seed":scene.seed,
        "scene_sha256":digest,"method":method,"p_loss":loss,
        **result,"observer_snapshots":observer.observed_phases,
        "first_feasible_seen":int(observer.first_feasible_ms is not None),
        "first_feasible_ms":(observer.first_feasible_ms if observer.first_feasible_ms is not None else ""),
        "first_feasible_cost_m":first["sum_distance_m"],
        "first_feasible_hungarian_ratio":first["hungarian_ratio"],
        "final_feasible":last["feasible"],
        "final_total_distance_m":last["sum_distance_m"],
        "final_makespan_s":last["makespan_s"],
        "final_hungarian_gap_m":last["hungarian_gap"],
        "final_hungarian_ratio":last["hungarian_ratio"],
        "oracle_total_m":oracle,
        "native_assignment_json":json.dumps(observer.last_pairs,separators=(",", ":")),
    }


def validate_complete_grid(rows: list[dict], sizes: tuple[int,...],
                           seeds: int, first_seed: int,
                           methods: tuple[str,...]) -> None:
    expected={(n,seed,method) for n in sizes
              for seed in range(first_seed,first_seed+seeds) for method in methods}
    keys={(int(r["robots"]),int(r["seed"]),r["method"]) for r in rows}
    if keys!=expected or len(rows)!=len(expected):
        fail("validate_complete_grid", "contract", "P1_INCOMPLETE_OR_DUPLICATE_GRID",
             expected={"rows":len(expected)},actual={"rows":len(rows),"unique_keys":len(keys)})
    by_scene={}
    for r in rows:
        key=(int(r["robots"]),int(r["seed"]))
        if key in by_scene and r["scene_sha256"]!=by_scene[key]:
            fail("validate_complete_grid", "contract", "P1_PAIRED_SCENE_SHA_MISMATCH",
                 expected=by_scene[key],actual=r["scene_sha256"],details=str(key))
        by_scene[key]=r["scene_sha256"]


def summarize(rows: list[dict], sizes: tuple[int,...],
              methods: tuple[str,...]) -> list[dict]:
    out=[]
    for n in sizes:
        for method in methods:
            cohort=[r for r in rows if r["robots"]==n and r["method"]==method]
            success=[r for r in cohort if r["native_success"] and r["final_feasible"]]
            feasible=[r for r in cohort if r["first_feasible_seen"]]
            times=[float(r["native_stop_ms"]) for r in cohort if r["native_stop_ms"]!=""]
            bytes_=[int(r["native_sender_bytes"]) for r in cohort if r["native_sender_bytes"]!=""]
            mean=lambda v:sum(v)/len(v) if v else ""
            out.append({
                "robots":n,"method":method,"trials":len(cohort),
                "native_complete":len(success),"first_feasible_observed":len(feasible),
                "guard_censored":sum(int(r["native_guard_censored"]) for r in cohort),
                "method_error":sum(bool(r["native_diagnostic"]) for r in cohort),
                "mean_all_seed_native_stop_ms":mean(times) if len(times)==len(cohort) else "",
                "mean_all_seed_sender_bytes":mean(bytes_) if len(bytes_)==len(cohort) else "",
                "mean_first_feasible_ms_when_seen":mean([float(r["first_feasible_ms"]) for r in feasible]),
                "mean_native_complete_cost_ratio":mean([float(r["final_hungarian_ratio"]) for r in success]),
                "native_endpoint":" / ".join(sorted({r["method_contract"] for r in cohort})),
            })
    return out


def paired_five_quality(rows: list[dict], sizes: tuple[int,...], seeds: int,
                       first_seed:int) -> list[dict]:
    """Never compute a paired quality number from different success subsets."""
    out=[]
    for n in sizes:
        cells=[]
        for seed in range(first_seed,first_seed+seeds):
            group=[r for r in rows if r["robots"]==n and r["seed"]==seed]
            if len(group)!=len(METHODS) or any(not r["native_success"] or not r["final_feasible"] for r in group):
                continue
            cells.append(group)
        for method in METHODS:
            selected=[next(r for r in pair if r["method"]==method) for pair in cells]
            out.append({"robots":n,"method":method,"same_success_paired_seeds":len(selected),
                        "mean_hungarian_ratio":(sum(float(x["final_hungarian_ratio"]) for x in selected)/len(selected)
                                                if selected else "")})
    return out


def write_csv(path: Path, rows: list[dict], fields: tuple[str,...]|None=None) -> None:
    if not rows and fields is None:
        fail("write_csv", "data", "P1_NO_ROWS_FOR_OUTPUT")
    with path.open("x",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields or tuple(rows[0]),extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(root:Path,args:argparse.Namespace,git_sha:str,started:str,
                   rows:list[dict],files:list[Path]) -> None:
    obj={
        "study":"P1_five_original_matched_first_feasible",
        "status":"finished_with_all_original_failures_and_guards_retained",
        "git_sha":git_sha,"started_utc":started,
        "completed_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "config":{"sizes":parse_sizes(args.sizes),"seeds":args.seeds,
                  "first_seed":args.first_seed,"loss":args.loss,
                  "capacity":1,"world_m":100,"methods":args.methods.split(","),
                  "cbaa_cbba_auction_guard":args.guard,"original_voting_guard":args.voting_guard,
                  "epsilon_cost_m":10,"assumed_phy_mbps":144.0,
                  "TASK_reliable":True,"task_service_s":0.0},
        "source_note":"Original Price Auction ported from historical native source; observer hooks never control run",
        "original_price_auction_source_git_blob":"2d2f1c0eaff94143ce256eebf0a0ee30603d8cba",
        "observer_contract":"first global unique C1 snapshot following incurred native phase; never affects stop",
        "native_stop_contract":"method-specific paid Commit vs local/observer, report separately",
        "failure_count":sum(not r["native_success"] for r in rows),
        "external_feasible_seen":sum(r["first_feasible_seen"] for r in rows),
        "sha256":{f.name:sha256_file(f) for f in files},
    }
    (root/"manifest_p1.json").write_text(json.dumps(obj,indent=2),encoding="utf-8")


def parse_args(argv:list[str]|None=None)->argparse.Namespace:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal",action="store_true")
    parser.add_argument("--sizes",default="25,50,100")
    parser.add_argument("--methods",default=",".join(METHODS))
    parser.add_argument("--seeds",type=int,default=3)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--loss",type=float,default=.30)
    parser.add_argument("--guard",type=int,default=160)
    parser.add_argument("--voting-guard",type=int,default=300)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def run_p1(args:argparse.Namespace)->list[dict]:
    sizes=validate_config(args)
    methods=tuple(args.methods.split(","))
    sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    ensure_new_output(args.output_root)
    started=datetime.now(timezone.utc).isoformat()
    raw=args.output_root/"per_seed_p1.csv"
    rows=[]
    with raw.open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=OUTPUT_FIELDS,extrasaction="raise")
        writer.writeheader()
        stream.flush()
        for n in sizes:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,n,n)
                verify_one_scene(scene)
                for method in methods:
                    row=run_matched_case(scene,profile,method,args.loss,
                                         args.guard,args.voting_guard)
                    writer.writerow(row)
                    stream.flush()
                    os.fsync(stream.fileno())
                    rows.append(row)
                    print(f"P1 N={n} seed={seed} method={method} "
                          f"native={row['native_success']} first_feasible={row['first_feasible_seen']} "
                          f"native_s={float(row['native_stop_ms'])/1000 if row['native_stop_ms']!='' else 'NA'} "
                          f"sender_B={row['native_sender_bytes']} diag={row['native_diagnostic'][:90]}",flush=True)
    validate_complete_grid(rows,sizes,args.seeds,args.first_seed,methods)
    summary=summarize(rows,sizes,methods)
    summary_path=args.output_root/"summary_p1.csv"
    write_csv(summary_path,summary)
    output_files=[raw,summary_path]
    if methods==METHODS:
        quality=paired_five_quality(rows,sizes,args.seeds,args.first_seed)
        quality_path=args.output_root/"same_success_quality_p1.csv"
        write_csv(quality_path,quality)
        output_files.append(quality_path)
    if args.formal:
        figure=args.output_root/"five_original_matched_comparison.svg"
        figure.write_text(render_p1_figure(summary,quality),encoding="utf-8")
        output_files.append(figure)
    write_manifest(args.output_root,args,sha,started,rows,output_files)
    print(f"P1_COMPLETE run_root={args.output_root} git_sha={sha} cases={len(rows)} "
          f"failed_native={sum(not r['native_success'] for r in rows)}",flush=True)
    return rows


def main(argv:list[str]|None=None)->None:
    args=parse_args(argv)
    run_p1(args)


if __name__=="__main__":
    main()
