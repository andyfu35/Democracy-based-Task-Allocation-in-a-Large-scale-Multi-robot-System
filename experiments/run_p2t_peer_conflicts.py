"""P2T: P2S Cost/Vote plus sender-paid PEER intent comparison; NO task owner.

This experimental protocol MAY produce duplicate tentative actions under loss.
No simulated tentative act represents a safe hardware execution grant.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import sys

from democracy_mrta.claim_resolution import coordinate_p2t_peer_conflicts
from democracy_mrta.coordination import simulate_p2k_local_vote_epoch
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import (
    solve_visible_batched_greedy_assignment, solve_hungarian_assignment,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, read_source_sha, scene_sha256, sha256_file,
)
from experiments.run_p2k_consensus_free import validate_p2k_config

OWNER = "experiments.run_p2t_peer_conflicts"
STUDY = "P2T_P2S_PEER_INTENT_NO_FIXED_TASK_OWNER"
POLICY = "adaptive_local_matching"
PHASES = (
    "task", "cost", "vote", "p2t_intent", "p2t_execution",
)
FIELDS = (
    "source_sha","scene_sha256","seed","robots","tasks","loss_percent",
    "votes_per_voter","policy","intent_repetitions","announcement_repetitions",
    "max_rounds","initial_intent_count","attempted_robot_count",
    "unique_task_count","duplicate_task_count","unassigned_task_count",
    "unique_completion_percent","distinct_coverage_percent",
    "full_valid_allocation","attempted_cost","actual_cost_if_valid",
    "global_greedy_cost","hungarian_cost",
    "optimality_gap_percent_if_valid","greedy_gap_percent_if_valid",
    "rounds_executed","locally_observed_conflicts","yielded_candidates",
    "retargeted_intents","sender_sends","sender_bytes",
    "task_sends","task_bytes","cost_sends","cost_bytes",
    "vote_sends","vote_bytes","p2t_intent_sends","p2t_intent_bytes",
    "p2t_execution_sends","p2t_execution_bytes",
    "cost_receiver_drops","vote_receiver_drops",
    "p2t_intent_receiver_drops","p2t_execution_receiver_drops",
    "native_stop_ms","first_failure_owner","first_failure_function",
    "first_failure_category","first_failure_code","first_failure_json",
    "attempted_pairs_json",
)
SUMMARY_FIELDS = (
    "loss_percent","seeds","full_valid_count","full_valid_percent",
    "mean_unique_completion_percent","mean_distinct_coverage_percent",
    "mean_duplicate_tasks","mean_unassigned_tasks",
    "mean_attempted_robots","mean_rounds",
    "mean_locally_observed_conflicts","mean_yielded_candidates",
    "mean_retargeted_intents","mean_sender_bytes",
    "mean_intent_bytes","mean_execution_notice_bytes",
    "mean_native_stop_ms","valid_cost_samples",
    "mean_valid_actual_cost","mean_valid_optimality_gap_percent",
    "mean_valid_greedy_gap_percent",
)


def fail(function, category, code, *, expected=None, actual=None, details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual, details=details,
    ))


def validate_p2t_axes(args):
    """Bound the cohort without modifying frozen P2S/P2R runner defaults."""
    losses, votes = validate_p2k_config(args)
    if (votes != (1000,) or args.k != 1 or args.epsilon != 0.0
            or type(args.max_rounds) is not int or not 1 <= args.max_rounds <= 255
            or type(args.intent_repetitions) is not int
            or not 1 <= args.intent_repetitions <= 5
            or type(args.announcement_repetitions) is not int
            or not 1 <= args.announcement_repetitions <= 5):
        fail("validate_p2t_axes","data","P2T_INVALID_STUDY_AXES",
             expected="B1000, k1, epsilon0, bounded rounds, 1..5 copies",
             actual=vars(args))
    return losses


def audit_p2t_case(*, scene, peer, votes, task_trace,
                   task_sampler, coord_sampler, loss, source_sha,
                   args) -> dict:
    """Observer-owned cost/one-robot-capacity and real sender ledger checks."""
    robots, tasks = scene.num_robots, scene.num_tasks
    attempts = peer.attempted_pairs
    if (len({robot for robot, _task in attempts}) != len(attempts)
            or any(not 0 <= robot < robots or not 0 <= task < tasks
                   for robot, task in attempts)):
        fail("audit_p2t_case","safety","P2T_INVALID_ATTEMPT_PAIRS",
             expected="valid capacity-one attempts",actual=attempts)
    expected_cache = [set() for _ in range(robots)]
    for robot, task in attempts:
        expected_cache[robot].add(task)
    for receipt in peer.deliveries:
        if receipt.phase == "p2t_execution" and receipt.delivered:
            expected_cache[receipt.receiver_id].add(receipt.task_id)
    if (tuple(tuple(sorted(tasks_seen)) for tasks_seen in expected_cache)
            != peer.recipient_seen_executing_tasks):
        fail("audit_p2t_case","contract","P2T_PHANTOM_EXECUTION_KNOWLEDGE",
             expected=tuple(tuple(sorted(x)) for x in expected_cache),
             actual=peer.recipient_seen_executing_tasks)
    events = tuple(task_trace.events) + votes.events + peer.events
    deliveries = votes.deliveries + peer.deliveries
    counts = {phase: {"sends":0,"bytes":0} for phase in PHASES}
    for event in events:
        phase = "task" if event.phase == "task_announcement" else event.phase
        if phase not in counts:
            fail("audit_p2t_case","contract","P2T_UNEXPECTED_WIRE_PHASE",
                 expected=PHASES,actual=phase)
        counts[phase]["sends"] += 1
        counts[phase]["bytes"] += event.payload_bytes
    if (counts["cost"]["sends"] != robots or
            counts["vote"]["sends"] != robots):
        fail("audit_p2t_case","contract","P2T_COST_VOTE_SEND_MISMATCH",
             expected={"cost":robots,"vote":robots},
             actual={k:v["sends"] for k,v in counts.items()})
    if (counts["p2t_intent"]["sends"] % args.intent_repetitions
            or counts["p2t_execution"]["sends"] %
            args.announcement_repetitions):
        fail("audit_p2t_case","contract","P2T_REPEAT_PACKET_COUNT_INVALID",
             expected="whole repeated P2TI and P2TE batches",
             actual={k:v["sends"] for k,v in counts.items()})
    total_sends = len(events)
    total_bytes = sum(e.payload_bytes for e in events)
    task_ledger = task_sampler.summarize_network()
    coord_ledger = coord_sampler.summarize_network()
    if ((task_ledger["packet_count"] + coord_ledger["packet_count"])
            != total_sends or
        (task_ledger["application_sender_bytes"]
         + coord_ledger["application_sender_bytes"]) != total_bytes):
        fail("audit_p2t_case","contract","P2T_ATTEMPTED_SENDER_LEDGER_MISMATCH",
             expected=(total_sends,total_bytes),
             actual=(task_ledger["packet_count"]+
                     coord_ledger["packet_count"],
                     task_ledger["application_sender_bytes"]+
                     coord_ledger["application_sender_bytes"]))
    if (peer.duplicate_task_count + peer.unassigned_task_count
            + peer.unique_task_count != tasks):
        fail("audit_p2t_case","contract","P2T_COVERAGE_COUNT_INVALID",
             expected=tasks,actual=(peer.unique_task_count,
                                    peer.duplicate_task_count,
                                    peer.unassigned_task_count))
    # NOTE: do not repair duplicated/unsupported peer actions with oracle!
    full = int(peer.unique_task_count == tasks and
               peer.duplicate_task_count == 0)
    if loss == 0:
        optimal_pairs = solve_hungarian_assignment(scene.cost_matrix).assigned_pairs
        if not full or set(attempts) != set(optimal_pairs):
            fail("audit_p2t_case","contract","P2T_ZERO_LOSS_HUNGARIAN_PARITY",
                 expected=optimal_pairs,actual=attempts)
    greedy = solve_visible_batched_greedy_assignment(
        scene.cost_matrix,frozenset(range(robots)),
    ).total_cost
    optimal = solve_hungarian_assignment(scene.cost_matrix).total_cost
    attempted_cost = sum(scene.cost_matrix[robot][task]
                         for robot, task in attempts)
    first = peer.first_diagnostic
    row = {
        "source_sha":source_sha,"scene_sha256":scene_sha256(scene),
        "seed":scene.seed,"robots":robots,"tasks":tasks,
        "loss_percent":round(loss*100),"votes_per_voter":1000,
        "policy":POLICY,"intent_repetitions":args.intent_repetitions,
        "announcement_repetitions":args.announcement_repetitions,
        "max_rounds":args.max_rounds,
        "initial_intent_count":peer.initial_candidate_count,
        "attempted_robot_count":len(attempts),
        "unique_task_count":peer.unique_task_count,
        "duplicate_task_count":peer.duplicate_task_count,
        "unassigned_task_count":peer.unassigned_task_count,
        "unique_completion_percent":100*peer.unique_task_count/tasks,
        "distinct_coverage_percent":100*(tasks-peer.unassigned_task_count)/tasks,
        "full_valid_allocation":full,"attempted_cost":attempted_cost,
        "actual_cost_if_valid":attempted_cost if full else "",
        "global_greedy_cost":greedy,"hungarian_cost":optimal,
        "greedy_gap_percent_if_valid":100*(attempted_cost/greedy-1) if full else "",
        "optimality_gap_percent_if_valid":100*(attempted_cost/optimal-1)
                                          if full else "",
        "rounds_executed":peer.rounds_executed,
        "locally_observed_conflicts":peer.locally_observed_conflicts,
        "yielded_candidates":peer.yielded_candidates,
        "retargeted_intents":peer.retargeted_intents,
        "sender_sends":total_sends,"sender_bytes":total_bytes,
        "native_stop_ms":max((e.arrival_time_ms for e in task_trace.events),
                             default=0.0)+peer.finish_ms,
        "first_failure_owner":first.owner if first else "",
        "first_failure_function":first.function if first else "",
        "first_failure_category":first.category if first else "",
        "first_failure_code":first.code if first else "",
        "first_failure_json":json.dumps(asdict(first),ensure_ascii=False,
                          separators=(",",":")) if first else "",
        "attempted_pairs_json":json.dumps(attempts,separators=(",",":")),
    }
    for phase in PHASES:
        row[phase+"_sends"]=counts[phase]["sends"]
        row[phase+"_bytes"]=counts[phase]["bytes"]
    for phase in ("cost","vote","p2t_intent","p2t_execution"):
        row[phase+"_receiver_drops"]=sum(
            1 for receipt in deliveries
            if receipt.phase==phase and not receipt.delivered
        )
    if set(row) != set(FIELDS):
        fail("audit_p2t_case","contract","P2T_ROW_SCHEMA_MISMATCH",
             expected=sorted(FIELDS),actual=sorted(row))
    return row


def summarize_p2t(rows):
    by_loss={}
    for row in rows:
        by_loss.setdefault(row["loss_percent"],[]).append(row)
    def mean(batch,name):
        return sum(float(x[name]) for x in batch)/len(batch)
    result=[]
    for loss,batch in sorted(by_loss.items()):
        valid=[row for row in batch if row["full_valid_allocation"]]
        result.append({
            "loss_percent":loss,"seeds":len(batch),
            "full_valid_count":len(valid),
            "full_valid_percent":100*len(valid)/len(batch),
            "mean_unique_completion_percent":mean(
                batch,"unique_completion_percent"),
            "mean_distinct_coverage_percent":mean(
                batch,"distinct_coverage_percent"),
            "mean_duplicate_tasks":mean(batch,"duplicate_task_count"),
            "mean_unassigned_tasks":mean(batch,"unassigned_task_count"),
            "mean_attempted_robots":mean(batch,"attempted_robot_count"),
            "mean_rounds":mean(batch,"rounds_executed"),
            "mean_locally_observed_conflicts":mean(
                batch,"locally_observed_conflicts"),
            "mean_yielded_candidates":mean(batch,"yielded_candidates"),
            "mean_retargeted_intents":mean(batch,"retargeted_intents"),
            "mean_sender_bytes":mean(batch,"sender_bytes"),
            "mean_intent_bytes":mean(batch,"p2t_intent_bytes"),
            "mean_execution_notice_bytes":mean(
                batch,"p2t_execution_bytes"),
            "mean_native_stop_ms":mean(batch,"native_stop_ms"),
            "valid_cost_samples":len(valid),
            "mean_valid_actual_cost":mean(valid,"actual_cost_if_valid")
                                      if valid else "",
            "mean_valid_optimality_gap_percent":mean(
                valid,"optimality_gap_percent_if_valid") if valid else "",
            "mean_valid_greedy_gap_percent":mean(valid,"greedy_gap_percent_if_valid")
                                           if valid else "",
        })
    return result


def save_p2t_evidence(*,root,rows,audits,config):
    with (root/"summary_p2t.csv").open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=SUMMARY_FIELDS,extrasaction="raise")
        writer.writeheader()
        writer.writerows(summarize_p2t(rows))
    items=[root/name for name in (
        "per_seed_p2t.csv","summary_p2t.csv","audit_p2t.jsonl","run_config_p2t.json",
    )]
    manifest={
        "study":STUDY,"source_sha":config["source_sha"],
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),"sha256":{p.name:sha256_file(p) for p in items},
        "notice":"P2T no owner: tentative acts can collide under lost peer P2TI; "
                 "only unique collision-free full cases have valid cost.",
    }
    (root/"manifest_p2t.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8",
    )


def run_one_p2t_case(*,scene,profile,loss,source_sha,args,capture_audit):
    task_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    loss_sampler=BernoulliLossSampler(scene.seed)
    task_trace=broadcast_task_information(
        task_positions=scene.task_positions,num_robots=scene.num_robots,
        sampler=task_sampler,loss_sampler=loss_sampler,
        p_loss=0.0,phase_timeout_ms=1e9,
    )
    costs=reconstruct_local_cost_rows(
        local_robot_positions=scene.robot_positions,
        announced_tasks_by_robot=task_trace.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=costs,expected=scene.cost_matrix,
    )
    coord_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    guard=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=scene.num_robots,
        total_tasks=scene.num_tasks,reference_phy_mbps=144.0,
    )
    votes=simulate_p2k_local_vote_epoch(
        cost_matrix=costs,sampler=coord_sampler,
        loss_sampler=loss_sampler,p_loss=loss,
        phase_timeout_ms=guard,seed=scene.seed,votes_per_voter=1000,
        policy=POLICY,k=1,epsilon=0.0,temperature=args.temperature,
    )
    peer=coordinate_p2t_peer_conflicts(
        run=votes,cost_matrix=costs,votes_per_voter=1000,
        sampler=coord_sampler,loss_sampler=loss_sampler,
        p_loss=loss,max_rounds=args.max_rounds,
        intent_repetitions=args.intent_repetitions,
        announcement_repetitions=args.announcement_repetitions,
    )
    row=audit_p2t_case(
        scene=scene,peer=peer,votes=votes,task_trace=task_trace,
        task_sampler=task_sampler,coord_sampler=coord_sampler,loss=loss,
        source_sha=source_sha,args=args,
    )
    audit=None
    if capture_audit:
        audit={
            "source_sha":source_sha,"seed":scene.seed,
            "scene_sha256":row["scene_sha256"],
            "loss_percent":row["loss_percent"],
            "visibility":[sorted(x) for x in votes.cost_visible_rows],
            "local_assignments":votes.local_assignments,
            "local_vote_views":votes.local_vote_views,
            "initial_claims":votes.robot_claims,
            "tentative_attempted_pairs":peer.attempted_pairs,
            "recipient_locally_seen_executing":
                peer.recipient_seen_executing_tasks,
            "physical_peer_events":[asdict(e) for e in peer.events],
            "physical_peer_receipts":[asdict(d) for d in peer.deliveries],
            "first_diagnostic":(
                asdict(peer.first_diagnostic) if peer.first_diagnostic else None
            ),
        }
    return row,audit


def run_p2t(args):
    losses=validate_p2t_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2t","state","P2T_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only output directory",actual=str(root))
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    config={
        "study":STUDY,"policy":POLICY,"source_sha":source_sha,
        "robots":args.robots,"tasks":args.tasks,"seed_count":args.seeds,
        "first_seed":args.first_seed,"loss_percent":losses,
        "votes_per_voter":1000,"k":1,"epsilon":0.0,
        "temperature":args.temperature,
        "max_rounds":args.max_rounds,
        "intent_repetitions":args.intent_repetitions,
        "announcement_repetitions":args.announcement_repetitions,
        "protocol":"P2TI 36B announced by each tentative executor; peers "
                   "locally compare normalized self-support, raw votes, "
                   "own announced task cost, robot ID; local losers retarget. "
                   "P2TE 16B records peer attempted execution; no owner, ACK, "
                   "DENY, COMMIT, P2NX. Observer NEVER resolves hidden collisions.",
        "transport":"original sender-paid reliable TASK; physical lossy "
                    "single Cost broadcast + 1016B P2KV Vote per robot; "
                    "one Rady/144Mbps radio-proxy timeline",
        "safe_full":"requires exact one robot attempted every task; unsafe "
                    "simultaneous peer acts are exposed as collisions",
        "audit_seeds":args.audit_seeds,
    }
    root.mkdir(parents=True)
    (root/"run_config_p2t.json").write_text(
        json.dumps(config,indent=2,ensure_ascii=False),encoding="utf-8",
    )
    rows=[]
    with (root/"per_seed_p2t.csv").open("x",newline="",encoding="utf-8") as raw, \
         (root/"audit_p2t.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(raw,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,args.robots,args.tasks)
                row,audit=run_one_p2t_case(
                    scene=scene,profile=profile,loss=loss/100,source_sha=source_sha,
                    args=args,capture_audit=seed<args.first_seed+args.audit_seeds,
                )
                writer.writerow(row)
                raw.flush()
                rows.append(row)
                if audit is not None:
                    audit_file.write(json.dumps(
                        audit,ensure_ascii=False,separators=(",",":"))+"\n")
                    audit_file.flush()
                print(
                    f"P2T loss={loss}% seed={seed} "
                    f"unique={row['unique_task_count']}/{args.tasks} "
                    f"duplicate_tasks={row['duplicate_task_count']} "
                    f"missing={row['unassigned_task_count']} "
                    f"safe_full={row['full_valid_allocation']} "
                    f"bytes={row['sender_bytes']} "
                    f"stop_s={row['native_stop_ms']/1000:.3f}",
                    flush=True,
                )
    save_p2t_evidence(root=root,rows=rows,audits=[],config=config)
    print(f"P2T_COMPLETE cases={len(rows)} root={root}",flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50,0.90")
    parser.add_argument("--votes",default="1000")
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=100)
    parser.add_argument("--seeds",type=int,default=100)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--k",type=int,default=1)
    parser.add_argument("--epsilon",type=float,default=0.0)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--max-rounds",type=int,default=101)
    parser.add_argument("--intent-repetitions",type=int,default=3)
    parser.add_argument("--announcement-repetitions",type=int,default=3)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2t(parse_args(argv))


if __name__ == "__main__":
    main()
