"""P2D: one new Centralized Method × 1000, three SHA-verified native archives.

All original P1/P2/P2-C method data remain immutable. This runner is
experiment-only, never a second allocation/packet state machine.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from democracy_mrta.centralized_method import simulate_one_shot_centralized
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from democracy_mrta.optimizer import (
    solve_hungarian_assignment, solve_visible_batched_greedy_assignment,
    solve_visible_task_ordered_greedy_assignment,
)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, OUTPUT_FIELDS, read_source_sha, verify_one_scene,
    scene_sha256, sha256_file, write_csv,
)
from experiments.p2_baseline_reuse import (
    read_verified_p2c_voting, read_verified_original_baselines,
    merge_p2d_paired_evidence,
)

OWNER = "experiments.run_p2d_centralized"
METHODS = ("voting", "cbaa", "cbba", "centralized")
LOSSES = tuple(range(0, 91, 10))
EXTRA_FIELDS = ("committed_task_count","task_coverage",
                "full_info_greedy_cost_m","cost_airtime_ms")
NATIVE_FIELDS = ("loss_percent",) + OUTPUT_FIELDS + EXTRA_FIELDS
COMBINED_FIELDS = NATIVE_FIELDS + (
    "source_role","source_git_sha","quality_vs_full_info_greedy",
)


def fail(function: str, category: str, code: str, expected=None, actual=None):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual,
    ))


def validate_config(args: argparse.Namespace) -> tuple[int, ...]:
    """Freeze 100R100T / 10 losses × 100 seeds, both original ZIP evidence."""
    try:
        raw = tuple(float(x.strip()) for x in args.losses.split(","))
    except (ValueError, AttributeError):
        fail("validate_config","data","P2D_INVALID_LOSS_GRID",LOSSES,args.losses)
    values = tuple(round(v*100) for v in raw)
    if (not values or values != tuple(sorted(set(values)))
            or any(x not in LOSSES for x in values)
            or any(abs(x/100-v)>1e-12 for x,v in zip(values,raw))):
        fail("validate_config","data","P2D_INVALID_LOSS_GRID",LOSSES,raw)
    if (type(args.seeds) is not int or type(args.first_seed) is not int
            or not 1 <= args.seeds <= 100 or args.first_seed < 0
            or args.first_seed+args.seeds > 100):
        fail("validate_config","data","P2D_INVALID_SEEDS",
             "first_seed + 1..100 seeds within 0..99",
             (args.first_seed,args.seeds))
    if args.formal and (values != LOSSES or args.first_seed != 0
                         or args.seeds != 100):
        fail("validate_config","contract","P2D_FORMAL_GRID_CHANGED",
             (LOSSES,0,100),(values,args.first_seed,args.seeds))
    if not args.p2c_voting_zip or not args.original_p2_zip:
        fail("validate_config","dependency","P2D_TWO_ARCHIVES_REQUIRED",
             "exact original P2-C and P2 original user ZIPs",
             (args.p2c_voting_zip,args.original_p2_zip))
    return values


def prepare_evidence(args, source_sha: str, percentages: tuple[int, ...]):
    """Append-only native source and strict same-prefix --resume identity."""
    root = Path(args.output_root)
    identity = {
        "source_sha":source_sha, "methods":METHODS,
        "executed_methods":("centralized",), "robots":100,"tasks":100,"capacity":1,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "loss_percent":percentages,"formal":bool(args.formal),
        "p2c_voting_zip":str(Path(args.p2c_voting_zip).expanduser().resolve()),
        "original_p2_zip":str(Path(args.original_p2_zip).expanduser().resolve()),
        "rady_json":str(args.rady_json),
    }
    cfg=root/"run_config_p2d.json"
    raw=root/"per_seed_p2d.csv"
    if not args.resume:
        if root.exists():
            fail("prepare_evidence","state","P2D_OUTPUT_EXISTS",
                 "new directory",str(root))
        root.mkdir(parents=True)
        cfg.write_text(json.dumps(identity,indent=2),encoding="utf-8")
        with raw.open("x",newline="",encoding="utf-8") as handle:
            csv.DictWriter(handle,fieldnames=NATIVE_FIELDS).writeheader()
        return [],identity
    if (not raw.is_file() or not cfg.is_file() or
            (root/"manifest_p2d.json").exists()):
        fail("prepare_evidence","state","P2D_RESUME_INVALID",
             "incomplete P2D source root",str(root))
    previous=json.loads(cfg.read_text(encoding="utf-8"))
    if previous != json.loads(json.dumps(identity)):
        fail("prepare_evidence","contract","P2D_RESUME_IDENTITY_CHANGED",
             previous,identity)
    with raw.open(newline="",encoding="utf-8") as handle:
        reader=csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != NATIVE_FIELDS:
            fail("prepare_evidence","contract","P2D_RESUME_COLUMNS_CHANGED",
                 NATIVE_FIELDS,reader.fieldnames)
        rows=list(reader)
    expected=[(p,s,"centralized") for p in percentages
              for s in range(args.first_seed,args.first_seed+args.seeds)]
    existing=[(int(r["loss_percent"]),int(r["seed"]),r["method"])
              for r in rows]
    if existing != expected[:len(existing)]:
        fail("prepare_evidence","contract","P2D_RESUME_PREFIX_CHANGED",
             expected[:len(existing)],existing)
    return rows,identity


def run_one_centralized_case(
    scene, profile, p_loss: float, max_cost_rounds: int = 1,
    planning_rule: str = "global",
) -> dict:
    """Read-only measurements for true original Centralized owner (opt-in retry)."""
    verify_one_scene(scene)
    native=simulate_one_shot_centralized(
        cost_matrix=scene.cost_matrix,task_positions=scene.task_positions,
        profile=profile,seed=scene.seed,p_loss=p_loss,
        max_cost_rounds=max_cost_rounds, planning_rule=planning_rule,
    )
    reference_planner=(solve_visible_task_ordered_greedy_assignment
                       if planning_rule=="task_ordered"
                       else solve_visible_batched_greedy_assignment)
    full_greedy=reference_planner(
        scene.cost_matrix,frozenset(range(scene.num_robots)),
    )
    if p_loss == 0.0 and (
        not native.native_success or native.assignment != full_greedy.assigned_pairs
    ):
        fail("run_one_centralized_case","contract",
             "P2D_ZERO_LOSS_GREEDY_MISMATCH",
             full_greedy.assigned_pairs,native.assignment)
    complete = native.native_success
    total_distance=(sum(scene.cost_matrix[r][t] for r,t in native.assignment)
                    if complete else "")
    hungarian_cost=solve_hungarian_assignment(scene.cost_matrix).total_cost
    other={"loss_percent":int(round(p_loss*100))}
    row={
        "robots":scene.num_robots,"tasks":scene.num_tasks,"capacity":1,
        "seed":scene.seed,"scene_sha256":scene_sha256(scene),
        "method":"centralized","p_loss":p_loss,
        "native_success":int(complete),"native_stop_reason":native.stop_reason,
        "native_guard_censored":0,"native_stop_ms":native.native_stop_ms,
        "observer_snapshots":1,
        "first_feasible_seen":int(complete),
        "first_feasible_ms":native.native_stop_ms if complete else "",
        "first_feasible_cost_m":total_distance,
        "first_feasible_hungarian_ratio":(
            total_distance/hungarian_cost if complete else ""),
        "final_feasible":int(complete),
        "final_total_distance_m":total_distance,
        "final_makespan_s":(
            max(scene.cost_matrix[r][t] for r,t in native.assignment)
            if complete else ""),
        "final_hungarian_gap_m":(
            total_distance-hungarian_cost if complete else ""),
        "final_hungarian_ratio":(
            total_distance/hungarian_cost if complete else ""),
        "oracle_total_m":hungarian_cost,
        "native_sender_sends":native.sender_sends,
        "native_sender_bytes":native.sender_bytes,
        "native_receiver_attempts":native.receiver_attempts,
        "native_receiver_drops":native.receiver_drops,
        "original_traffic_ledger_json":json.dumps(native.event_ledger,sort_keys=True),
        "native_assignment_json":json.dumps(native.assignment,separators=(",",":")),
        "native_diagnostic":"",
        "method_contract":(
            "one-shot task-ID-order Greedy coordinator: one Cost attempt per sender"
            if planning_rule=="task_ordered" else
            "one-shot coordinator paid reliable assignment + executor Commit, no retry"
            if max_cost_rounds == 1 else
            "repeat missing physically lost Cost to coordinator; one Global Greedy + reliable Commit"
        ),
        "committed_task_count":len(native.assignment),
        "task_coverage":native.task_coverage,
        "full_info_greedy_cost_m":full_greedy.total_cost,
        "cost_airtime_ms":native.cost_airtime_ms,
    }
    if max_cost_rounds != 1 or planning_rule != "global":
        row["cost_rounds_executed"] = native.cost_rounds_executed
        row["cost_sender_sends"] = native.cost_sender_sends
        row["cost_sender_bytes"] = native.cost_sender_bytes
        row["cost_receiver_drops"] = native.cost_receiver_drops
    return {**other,**row}


def validate_complete_grid(rows, percentages, first_seed, seeds, *, methods=METHODS):
    """Exact cells and physically identical paired scene identity."""
    expected={(p,seed,method) for p in percentages
              for seed in range(first_seed,first_seed+seeds)
              for method in methods}
    actual=[(int(r["loss_percent"]),int(r["seed"]),r["method"]) for r in rows]
    if len(actual)!=len(expected) or set(actual)!=expected:
        fail("validate_complete_grid","contract","P2D_INCOMPLETE_CELL_GRID",
             len(expected),{"rows":len(actual),"unique":len(set(actual))})
    for p in percentages:
        for seed in range(first_seed,first_seed+seeds):
            scene={r["scene_sha256"] for r in rows
                   if int(r["loss_percent"])==p and int(r["seed"])==seed}
            if len(scene)!=1:
                fail("validate_complete_grid","contract","P2D_UNPAIRED_SEED_SCENE",
                     "one scene per paired cell",(p,seed,scene))


def augment_full_info_quality(rows):
    """Read-only quality reference; incomplete native methods remain missing."""
    cache={}
    out=[]
    for raw in rows:
        row={field:raw.get(field,"") for field in COMBINED_FIELDS}
        seed=int(row["seed"])
        if seed not in cache:
            scene=generate_e0_scenario(seed,100,100)
            cache[seed]=solve_visible_batched_greedy_assignment(
                scene.cost_matrix,frozenset(range(100)),
            ).total_cost
        denom=cache[seed]
        row["full_info_greedy_cost_m"]=denom
        is_success=int(row["native_success"]) and int(row["final_feasible"])
        raw_distance=row["final_total_distance_m"]
        row["quality_vs_full_info_greedy"]=(
            float(raw_distance)/denom if is_success and raw_distance!="" else ""
        )
        out.append(row)
    return out


def summarize(rows, percentages):
    """Report conditional quality separately from unconditional 100-seed stops."""
    output=[]
    for loss in percentages:
        for method in METHODS:
            subset=[r for r in rows if int(r["loss_percent"])==loss and r["method"]==method]
            completed=[r for r in subset if int(r["native_success"]) and int(r["final_feasible"])]
            native_times=[float(r["native_stop_ms"]) for r in subset
                          if r.get("native_stop_ms") not in ("",None)]
            bytes_sent=[float(r["native_sender_bytes"]) for r in subset
                        if r.get("native_sender_bytes") not in ("",None)]
            qualities=[float(r["quality_vs_full_info_greedy"]) for r in completed
                       if r.get("quality_vs_full_info_greedy") not in ("",None)]
            coverage=[float(r["task_coverage"]) for r in subset
                      if r.get("task_coverage") not in ("",None)]
            mean=lambda x:sum(x)/len(x) if x else ""
            n=len(subset)
            output.append({
                "loss_percent":loss,"method":method,"trials":n,
                "native_complete":len(completed),
                "completion_rate":len(completed)/n if n else "",
                "native_stop_record_count":len(native_times),
                "mean_all_seed_native_stop_ms":(
                    mean(native_times) if len(native_times)==n else ""),
                "sender_bytes_record_count":len(bytes_sent),
                "mean_all_seed_sender_bytes":(
                    mean(bytes_sent) if len(bytes_sent)==n else ""),
                "quality_sample_count":len(qualities),
                "mean_cost_over_full_info_greedy":mean(qualities),
                "task_coverage_record_count":len(coverage),
                "mean_task_coverage":mean(coverage),
            })
    return output


def write_evidence(args, native_rows, baseline_rows, percentages,
                   source_sha, source_identity, old_provenance, p2c_provenance):
    """Fresh SHA-attested combined CSV/summary/SVG; never edit original archives."""
    root=Path(args.output_root)
    combined=merge_p2d_paired_evidence(
        voting_rows=p2c_provenance["selected_rows"],
        native_baselines=baseline_rows,
        centralized_rows=native_rows,
        percentages=percentages,first_seed=args.first_seed,seeds=args.seeds,
        centralized_source_sha=source_sha,
    )
    validate_complete_grid(combined,percentages,args.first_seed,args.seeds)
    with_quality=augment_full_info_quality(combined)
    p_comb=root/"per_seed_p2d_combined.csv"
    write_csv(p_comb,with_quality,fields=COMBINED_FIELDS)
    groups=summarize(with_quality,percentages)
    p_summary=root/"summary_p2d.csv"
    write_csv(p_summary,groups)
    generated=[root/"run_config_p2d.json",root/"per_seed_p2d.csv",
               p_comb,p_summary]
    if args.formal:
        from experiments.p2d_plot import render_p2d_figure
        figure=root/"p2d_four_panel.svg"
        figure.write_text(render_p2d_figure(groups,percentages),
                          encoding="utf-8")
        generated.append(figure)
    manifest={
        "study":"P2D_CENTRALIZED_ONE_SHOT_NO_RETRY_AND_3000_NATIVE_REUSE",
        "source_sha":source_sha,
        "config":source_identity,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "new_centralized_cases":len(native_rows),
        "reused_verified_cases":len(baseline_rows)+len(p2c_provenance["selected_rows"]),
        "combined_cases":len(combined),
        "groups":len(groups),
        "p2c_original_provenance":p2c_provenance["manifest"],
        "p2_original_provenance":old_provenance,
        "sha256":{p.name:sha256_file(p) for p in generated},
        "limits":(
            "One-shot Centralized Cost with no retries, P2-C voting paid "
            "Score/Commit, CBAA/CBBA unequal native STOP; sampled Rady delay "
            "and hypothetical 144Mbps; Control TASK/decision/Commit reliable."
        ),
    }
    (root/"manifest_p2d.json").write_text(
        json.dumps(manifest,indent=2),encoding="utf-8",
    )
    return groups


def run_p2d(args):
    percentages=validate_config(args)
    # Both full ZIPs are validated BEFORE any new output or transmission.
    voting_rows,voting_prov=read_verified_p2c_voting(
        Path(args.p2c_voting_zip),percentages,args.first_seed,args.seeds,
    )
    old_all,old_prov=read_verified_original_baselines(
        Path(args.original_p2_zip),percentages,args.first_seed,args.seeds,
    )
    originals=[r for r in old_all if r["method"] in ("cbaa","cbba")]
    sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows,identity=prepare_evidence(args,sha,percentages)
    cells=[(p,seed) for p in percentages
           for seed in range(args.first_seed,args.first_seed+args.seeds)]
    output=Path(args.output_root)/"per_seed_p2d.csv"
    with output.open("a",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=NATIVE_FIELDS)
        for loss,seed in cells[len(rows):]:
            scene=generate_e0_scenario(seed,100,100)
            record=run_one_centralized_case(scene,profile,loss/100)
            writer.writerow(record)
            f.flush()
            os.fsync(f.fileno())
            rows.append(record)
            print(f"P2D PL={loss}% seed={seed} central_native={record['native_success']} "
                  f"committed={record['committed_task_count']} "
                  f"stop_ms={record['native_stop_ms']:.3f} "
                  f"bytes={record['native_sender_bytes']}",flush=True)
    validate_complete_grid(rows,percentages,args.first_seed,args.seeds,
                           methods=("centralized",))
    groups=write_evidence(
        args, rows, originals, percentages, sha, identity, old_prov,
        {"selected_rows":voting_rows,"manifest":voting_prov},
    )
    print(f"P2D_COMPLETE new={len(rows)} original={len(originals)+len(voting_rows)} "
          f"groups={len(groups)} root={args.output_root}",flush=True)
    return groups


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal",action="store_true")
    parser.add_argument("--losses",default=",".join(f"{p/100:.2f}" for p in LOSSES))
    parser.add_argument("--seeds",type=int,default=2)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--p2c-voting-zip",type=Path,required=True)
    parser.add_argument("--original-p2-zip",type=Path,required=True)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--resume",action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    run_p2d(parse_args(argv))


if __name__=="__main__":
    main()
