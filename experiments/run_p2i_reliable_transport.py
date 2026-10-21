"""P2I two native Proposed Global Greedy ACK/retry transport arms.

Cost: physically confirmed full peer view in both. Vote: either one physical
batch SEND per voter, or ACK-confirmed same-packet retransmission. TASK/Score/
Commit keep the original reliable-control assumption. No hidden Cost repair.
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

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from democracy_mrta.optimizer import solve_hungarian_assignment, solve_visible_batched_greedy_assignment
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e9h_adaptive_deadline import (
    DEFAULT_OLD_FIXED_MS, build_e9h_deadline_schedule, run_e9h_original_voting_case,
)
from experiments.run_e9i_cost30_scaling import selected_e9i_arms
from experiments.run_p1_matched_five import DEFAULT_RADY, read_source_sha, scene_sha256, sha256_file

OWNER = "experiments.run_p2i_reliable_transport"
MODES = ("full_retry", "cost_retry_vote_once")
LOSSES = tuple(range(0, 91, 10))
FIELDNAMES = (
    "loss_percent","seed","mode","git_sha","scene_sha256",
    "native_success","committed_tasks","cost_increase_percent",
    "full_info_greedy_cost_m","assignment_cost_m",
    "native_stop_ms","native_sender_sends","native_sender_bytes",
    "cost_sender_sends","cost_sender_bytes","cost_ack_sender_sends",
    "cost_ack_sender_bytes","vote_sender_sends","vote_sender_bytes",
    "vote_ack_sender_sends","vote_ack_sender_bytes",
    "score_sender_sends","score_sender_bytes","commit_sender_sends",
    "commit_sender_bytes","native_rounds","native_cost_receiver_observations",
    "native_cost_receiver_drops","native_vote_receiver_drops",
    "retry_limit","native_diagnostic",
)


def fail(function, category, code, expected=None, actual=None, details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual, details=details,
    ))


def validate_config(args):
    try:
        raw=tuple(float(v.strip()) for v in args.losses.split(","))
    except (AttributeError,ValueError,TypeError):
        fail("validate_config","data","P2I_BAD_LOSSES","subset of 0,.10,...,.90",args.losses)
    losses=tuple(int(round(v*100)) for v in raw)
    if (not raw or any(not math.isfinite(v) for v in raw) or
            losses != tuple(sorted(set(losses))) or
            any(p not in LOSSES or abs(v-p/100)>1e-12 for v,p in zip(raw,losses))):
        fail("validate_config","data","P2I_BAD_LOSSES",LOSSES,raw)
    if (type(args.seeds) is not int or not 1<=args.seeds<=100 or
            type(args.first_seed) is not int or args.first_seed<0 or
            args.first_seed+args.seeds>100 or
            type(args.retry_limit) is not int or not 1<=args.retry_limit<=300):
        fail("validate_config","data","P2I_BAD_AXES",
             "seeds 1..100 within 0..99, retry_limit 1..300",
             (args.seeds,args.first_seed,args.retry_limit))
    if args.formal and (losses!=LOSSES or args.seeds!=100 or args.first_seed!=0):
        fail("validate_config","contract","P2I_FORMAL_GRID_CHANGED",
             (LOSSES,100,0),(losses,args.seeds,args.first_seed))
    return losses


def run_native(scene, profile, loss, mode, retry_limit, source_sha):
    """Invoke the ONLY original native decision owner and retain its genuine SEND ledger."""
    n=scene.num_robots
    arm=next(v for v in selected_e9i_arms() if v[0]=="adaptive_guarded_k1_received")
    schedule=build_e9h_deadline_schedule(
        profile=profile,robots=n,design_rate_mbps=144.0,margin_factor=1.0,
        voting_strategy="greedy_batch",batch_vote_scope="all",
    )
    # Cost reliable stage owns its own ACK-gated dynamic close; no hidden grid.
    full=solve_visible_batched_greedy_assignment(
        scene.cost_matrix, frozenset(range(n)),
    )
    native=run_e9h_original_voting_case(
        scenario=scene,profile=profile,n=n,seed=scene.seed,p_loss=loss,
        p_vote_loss=loss,rate=144.0,max_rounds=1,
        fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,
        arm=arm,schedules={1.0:schedule},
        oracle_total_cost=solve_hungarian_assignment(scene.cost_matrix).total_cost,
        guarded_cost_ms=schedule[0].deadline_ms if False else None,
        voting_strategy="greedy_batch",batch_vote_scope="all",
        reliable_cost=True,reliable_vote=(mode=="full_retry"),
        retry_limit=retry_limit,
    )
    # Full Cost -> all original greedy proposals match; Vote retry changes
    # physical receipts, never invents a replacement assignment.
    success=bool(native["full_commit"])
    actual_cost=float(native["total_assignment_cost"])
    increase=100*(actual_cost/full.total_cost-1) if success else ""
    phases=native["sender_by_phase"]
    if not isinstance(phases,dict):
        fail("run_native","contract","P2I_MISSING_NATIVE_SENDER_LEDGER","phase sender ledger",phases)
    fields={}
    for label in ("cost","cost_ack","vote","vote_ack","score","commit"):
        record=phases[label]
        fields[label+"_sender_sends"]=int(record["sender_sends"])
        fields[label+"_sender_bytes"]=int(record["sender_bytes"])
    if (sum(fields[v+"_sender_sends"] for v in
            ("cost","cost_ack","vote","vote_ack","score","commit"))+
            int(phases["task"]["sender_sends"])!=int(native["total_original_send_count"]) or
        sum(fields[v+"_sender_bytes"] for v in
            ("cost","cost_ack","vote","vote_ack","score","commit"))+
            int(phases["task"]["sender_bytes"])!=int(native["total_sender_application_bytes"])):
        fail("run_native","contract","P2I_SENDER_ACCOUNTING_MISMATCH",
             "all attempted original SENDs including ACK",fields)
    if fields["cost_ack_sender_sends"]<n:
        fail("run_native","contract","P2I_NO_PAID_COST_ACK",f">={n}",fields["cost_ack_sender_sends"])
    if mode=="full_retry" and fields["vote_ack_sender_sends"]<n:
        fail("run_native","contract","P2I_NO_PAID_VOTE_ACK",f">={n}",fields["vote_ack_sender_sends"])
    if mode=="cost_retry_vote_once" and (
            fields["vote_ack_sender_sends"]!=0 or fields["vote_sender_sends"]!=n):
        fail("run_native","contract","P2I_VOTE_ONCE_VIOLATED",
             (0,n),(fields["vote_ack_sender_sends"],fields["vote_sender_sends"]))
    if loss==0 and (not success or abs(float(increase))>1e-9):
        fail("run_native","contract","P2I_ZERO_LOSS_GREEDY_MISMATCH",
             (100,0),(native["tasks_committed"],increase))
    return {
        "loss_percent":int(round(loss*100)),"seed":scene.seed,"mode":mode,
        "git_sha":source_sha,"scene_sha256":scene_sha256(scene),
        "native_success":int(success),"committed_tasks":int(native["tasks_committed"]),
        "cost_increase_percent":increase,"full_info_greedy_cost_m":full.total_cost,
        "assignment_cost_m":actual_cost if success else "",
        "native_stop_ms":native["allocation_or_stop_ms"],
        "native_sender_sends":native["total_original_send_count"],
        "native_sender_bytes":native["total_sender_application_bytes"],
        **fields,"native_rounds":native["rounds_executed"],
        "native_cost_receiver_observations":native["cost_remote_receiver_observation_count"],
        "native_cost_receiver_drops":native["cost_remote_packet_drop_count"],
        "native_vote_receiver_drops":native["vote_remote_packet_drop_count"],
        "retry_limit":retry_limit,"native_diagnostic":"",
    }


def summarize(rows, losses):
    groups=[]
    for loss in losses:
        for mode in MODES:
            subset=[r for r in rows if int(r["loss_percent"])==loss and r["mode"]==mode]
            success=[r for r in subset if int(r["native_success"])]
            def mean(key,cohort=subset):
                return sum(float(r[key]) for r in cohort)/len(cohort) if cohort else ""
            groups.append({
                "loss_percent":loss,"mode":mode,"seeds":len(subset),
                "full_completion_percent":100*len(success)/len(subset) if subset else "",
                "mean_task_coverage_percent":mean("committed_tasks"),
                "cost_success_n":len(success),
                "cost_increase_percent":mean("cost_increase_percent",success),
                "mean_stop_s":mean("native_stop_ms")/1000 if subset else "",
                "mean_sender_kB":mean("native_sender_bytes")/1000 if subset else "",
                **{f"mean_{phase}_sender_bytes":mean(f"{phase}_sender_bytes")
                   for phase in ("cost","cost_ack","vote","vote_ack","score","commit")},
            })
    return groups


def run(args):
    losses=validate_config(args)
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    root=Path(args.output_root)
    if root.exists():
        fail("run","state","P2I_OUTPUT_ALREADY_EXISTS","new append-only root",str(root))
    root.mkdir(parents=True)
    config={
        "study":"P2I_PROPOSED_ACK_RETRY_TWO_MODES",
        "source_sha":source_sha,"modes":MODES,"loss_percent":losses,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "retry_limit":args.retry_limit,"robots":100,"tasks":100,
        "capacity":1,"cost_reliable":True,
        "vote_reliable_by_mode":{"full_retry":True,"cost_retry_vote_once":False},
        "planning":"Global minimum-pair Greedy",
        "cost_reference":"full-info Global minimum-pair Greedy",
        "sender_accounting":"all physical application SENDs including failed frames and reliable paid ACKs",
        "radio_model":"Rady bootstrap + hypothetical 144Mbps shared-medium; no RF collisions/EDCA/OFDMA",
        "reliable_control_assumption":"TASK, Cost/Vote bitmap ACK, Score, Commit",
        "rady_json":str(args.rady_json),
        "formal":bool(args.formal),
    }
    (root/"run_config_p2i.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    raw=root/"per_seed_p2i.csv"
    rows=[]
    with raw.open("x",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDNAMES)
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,100,100)
                for mode in MODES:
                    row=run_native(scene,profile,loss/100,mode,args.retry_limit,source_sha)
                    writer.writerow({key:row.get(key,"") for key in FIELDNAMES})
                    stream.flush()
                    os.fsync(stream.fileno())
                    rows.append(row)
                    print(f"P2I PL={loss}% seed={seed} mode={mode} "
                          f"committed={row['committed_tasks']} "
                          f"cost_pct={row['cost_increase_percent']} "
                          f"bytes={row['native_sender_bytes']} "
                          f"stop_ms={row['native_stop_ms']:.3f}",flush=True)
    groups=summarize(rows,losses)
    from experiments.run_p1_matched_five import write_csv
    write_csv(root/"summary_p2i.csv",groups)
    manifest={
        "study":config["study"],"source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "executions":len(rows),"groups":len(groups),"config":config,
        "sha256":{p.name:sha256_file(p) for p in (
            root/"run_config_p2i.json",raw,root/"summary_p2i.csv")},
    }
    (root/"manifest_p2i.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(f"P2I_COMPLETE cases={len(rows)} groups={len(groups)} root={root}",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default=",".join(f"{p/100:.2f}" for p in LOSSES))
    parser.add_argument("--seeds",type=int,default=2)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--retry-limit",type=int,default=300)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--formal",action="store_true")
    run(parser.parse_args(argv))


if __name__=="__main__":
    main()
