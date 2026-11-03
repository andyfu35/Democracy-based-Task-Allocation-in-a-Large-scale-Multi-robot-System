"""P2R ONLY: P2Q rank-square Cost/Vote, tentative INTENT, conflicts, COMMIT.

One new native method per seed/loss. No legacy algorithm arm and NO
re-simulation of the original P2Q Vote epoch. Original 1000-ticket
P2KV local view remains private; only lossy 28B INTENT is initially
broadcast. A robot cannot execute without an actual task-owner COMMIT.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime,timezone
import json
from pathlib import Path
import platform
import sys

from democracy_mrta.claim_resolution import coordinate_p2r_announced_intents
from democracy_mrta.coordination import simulate_p2k_local_vote_epoch
from democracy_mrta.diagnostics import Diagnostic,ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,ensure_rady_dataset,load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information,reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler
from experiments.run_p1_matched_five import (
    DEFAULT_RADY,read_source_sha,scene_sha256,sha256_file,
)
from experiments.run_p2k_consensus_free import validate_p2k_config

OWNER="experiments.run_p2r_intent_conflict_commit"
STUDY="P2R_RANK_SQUARED_VOTE_INTENT_CONFLICT_ONLY_COMMIT"
PHASES=(
    "task","cost","vote","p2r_intent","p2r_challenge",
    "p2r_commit","p2r_deny","execution_announce",
)
FIELDS=(
    "source_sha","seed","scene_sha256",
    "robots","tasks","loss_percent","votes_per_voter",
    "policy","k","epsilon","intent_repetitions",
    "decision_repetitions","announcement_repetitions","max_rounds",
    "initial_intent_count","initial_duplicate_tasks",
    "initial_unassigned_tasks","initial_unique_percent",
    "executed_count","reserved_count","unique_completion_percent",
    "unassigned_task_count","duplicate_task_count","full_valid_allocation",
    "partial_actual_cost","actual_cost_if_valid","global_greedy_cost",
    "cost_gap_percent_if_valid",
    "rounds_executed","owner_observed_conflicts",
    "peer_observed_challenges","challenge_deferrals",
    "denial_receipts","retargeted_intents","intents_seen_by_owner",
    "sender_sends","sender_bytes",
    "task_sends","task_bytes","cost_sends","cost_bytes",
    "vote_sends","vote_bytes",
    "p2r_intent_sends","p2r_intent_bytes",
    "p2r_challenge_sends","p2r_challenge_bytes",
    "p2r_commit_sends","p2r_commit_bytes",
    "p2r_deny_sends","p2r_deny_bytes",
    "execution_announce_sends","execution_announce_bytes",
    "cost_receiver_drops","vote_receiver_drops",
    "p2r_intent_receiver_drops","p2r_challenge_receiver_drops",
    "p2r_commit_receiver_drops","p2r_deny_receiver_drops",
    "execution_announce_receiver_drops",
    "native_stop_ms","owner_finish_ms",
    "first_failure_owner","first_failure_function",
    "first_failure_category","first_failure_code",
    "first_failure_json",
    "executed_pairs_json","reserved_pairs_json",
)
SUMMARY_FIELDS=(
    "loss_percent","seeds","full_valid_count","full_valid_percent",
    "mean_unique_completion_percent","mean_unassigned_tasks",
    "mean_duplicate_tasks","mean_reserved_count",
    "mean_initial_duplicate_tasks","mean_rounds",
    "mean_owner_observed_conflicts","mean_challenge_sends",
    "mean_challenge_deferrals","mean_denial_receipts",
    "mean_retargeted_intents","mean_intent_bytes",
    "mean_commit_bytes","mean_deny_bytes",
    "mean_total_sender_bytes","mean_native_stop_ms",
    "valid_cost_samples","mean_valid_actual_cost",
    "mean_valid_global_greedy_gap_percent",
)


def fail(function,category,code,*,expected=None,actual=None,details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2r_axes(args):
    """Only P2R rank-square 1000-ticket, challenge+COMMIT study."""
    losses,votes=validate_p2k_config(args)
    if (votes!=(1000,) or args.k!=5 or args.epsilon!=0.0
            or type(args.max_rounds) is not int
            or not 1<=args.max_rounds<=255
            or any(type(reps) is not int or not 1<=reps<=5
                   for reps in (args.intent_repetitions,
                                args.decision_repetitions,
                                args.announcement_repetitions))):
        fail("validate_p2r_axes","data","P2R_INVALID_STUDY_AXIS",
             expected="rank-square B1000, K=5, epsilon0; 1..5 physical "
                      "INTENT/decision/EXECUTING copies; rounds 1..255",
             actual=vars(args))
    return losses


def validate_p2r_execution_evidence(*,scene,owner_result):
    """Observer safety gate without modifying any local robot decision."""
    robots,tasks=scene.num_robots,scene.num_tasks
    executed=owner_result.executed_pairs
    reserved=owner_result.reserved_pairs
    if (len({r for r,_ in executed})!=len(executed)
            or len({t for _,t in executed})!=len(executed)
            or len({r for r,_ in reserved})!=len(reserved)
            or len({t for _,t in reserved})!=len(reserved)
            or not set(executed).issubset(set(reserved))
            or any(not 0<=r<robots or not 0<=t<tasks
                   for r,t in executed)):
        fail("validate_p2r_execution_evidence","safety",
             "P2R_INVALID_EXECUTION_EVIDENCE",
             expected="unique one-to-one executed and reserved owner "
                      "pairs; actual executions subset of reservations",
             actual={"executed":executed,"reserved":reserved})
    for robot,actual_cache in enumerate(
            owner_result.recipient_seen_executing_tasks):
        predicted={
            task for executor,task in executed if executor==robot
        }
        predicted.update(
            receipt.task_id for receipt in owner_result.deliveries
            if receipt.phase=="execution_announce"
            and receipt.delivered and receipt.receiver_id==robot
        )
        if set(actual_cache)!=predicted:
            fail("validate_p2r_execution_evidence","contract",
                 "P2R_PHANTOM_EXECUTION_NOTICE",
                 expected=sorted(predicted),actual={
                     "robot":robot,"cache":actual_cache,
                 })


def summarize_p2r_rows(rows):
    """Cost is conditioned strictly on ALL tasks uniquely assigned."""
    by_loss={}
    for row in rows:
        by_loss.setdefault(row["loss_percent"],[]).append(row)
    def mean(batch,name):
        return sum(float(x[name]) for x in batch)/len(batch)
    summary=[]
    for loss,batch in sorted(by_loss.items()):
        valid=[r for r in batch if r["full_valid_allocation"]]
        summary.append({
            "loss_percent":loss,"seeds":len(batch),
            "full_valid_count":len(valid),
            "full_valid_percent":100.0*len(valid)/len(batch),
            "mean_unique_completion_percent":mean(
                batch,"unique_completion_percent"),
            "mean_unassigned_tasks":mean(batch,"unassigned_task_count"),
            "mean_duplicate_tasks":mean(batch,"duplicate_task_count"),
            "mean_reserved_count":mean(batch,"reserved_count"),
            "mean_initial_duplicate_tasks":mean(
                batch,"initial_duplicate_tasks"),
            "mean_rounds":mean(batch,"rounds_executed"),
            "mean_owner_observed_conflicts":mean(
                batch,"owner_observed_conflicts"),
            "mean_challenge_sends":mean(batch,"p2r_challenge_sends"),
            "mean_challenge_deferrals":mean(
                batch,"challenge_deferrals"),
            "mean_denial_receipts":mean(batch,"denial_receipts"),
            "mean_retargeted_intents":mean(batch,"retargeted_intents"),
            "mean_intent_bytes":mean(batch,"p2r_intent_bytes"),
            "mean_commit_bytes":mean(batch,"p2r_commit_bytes"),
            "mean_deny_bytes":mean(batch,"p2r_deny_bytes"),
            "mean_total_sender_bytes":mean(batch,"sender_bytes"),
            "mean_native_stop_ms":mean(batch,"native_stop_ms"),
            "valid_cost_samples":len(valid),
            "mean_valid_actual_cost":(
                mean(valid,"actual_cost_if_valid") if valid else ""),
            "mean_valid_global_greedy_gap_percent":(
                mean(valid,"cost_gap_percent_if_valid") if valid else ""),
        })
    return summary


def make_p2r_evidence_row(
    *, scene,source_sha,loss,vote_run,task_trace,task_sampler,
    coord_sampler,owner_result,
):
    """Same original Cost/Vote ledger plus ONLY real P2R physical SENDs."""
    validate_p2r_execution_evidence(
        scene=scene,owner_result=owner_result,
    )
    robots,tasks=scene.num_robots,scene.num_tasks
    events=tuple(task_trace.events)+vote_run.events+owner_result.events
    observations=vote_run.deliveries+owner_result.deliveries
    phases={}
    for event in events:
        phase="task" if event.phase=="task_announcement" else event.phase
        record=phases.setdefault(phase,{"sends":0,"bytes":0})
        record["sends"]+=1
        record["bytes"]+=event.payload_bytes
    extra_phases={e.phase for e in owner_result.events}
    if (any(e.phase not in ("task_announcement",)+PHASES[1:]
            for e in events)
            or any(phase not in PHASES for phase in extra_phases)
            or {phase:phases.get(phase,{}).get("sends",0)
                for phase in ("cost","vote")}!={"cost":robots,"vote":robots}):
        fail("make_p2r_evidence_row","contract",
             "P2R_NATIVE_PHASE_MISMATCH",
             expected="only TASK, 100 original Cost, 100 original Vote, "
                      "and named P2R phases",
             actual=phases)
    task_ledger=task_sampler.summarize_network()
    vote_ledger=coord_sampler.summarize_network()
    expected_count=len(events)
    expected_bytes=sum(event.payload_bytes for event in events)
    if ((task_ledger["packet_count"]+
         vote_ledger["packet_count"])!=expected_count
         or (task_ledger["application_sender_bytes"]+
             vote_ledger["application_sender_bytes"])!=expected_bytes):
        fail("make_p2r_evidence_row","contract",
             "P2R_ACTUAL_SEND_LEDGER_MISMATCH",
             expected=(expected_count,expected_bytes),
             actual=(task_ledger["packet_count"]+vote_ledger["packet_count"],
                     task_ledger["application_sender_bytes"]+
                     vote_ledger["application_sender_bytes"]))
    initial=[0]*tasks
    for robot,task in vote_run.robot_claims:
        initial[task]+=1
    initial_unique=sum(c==1 for c in initial)
    initial_duplicate=sum(c>1 for c in initial)
    initial_missing=sum(c==0 for c in initial)
    executed=owner_result.executed_pairs
    actual_cost=sum(scene.cost_matrix[r][t] for r,t in executed)
    reference=solve_visible_batched_greedy_assignment(
        scene.cost_matrix,frozenset(range(robots)),
    ).total_cost
    full=int(len(executed)==tasks)
    failure=owner_result.first_diagnostic
    row={
        "source_sha":source_sha,"seed":scene.seed,
        "scene_sha256":scene_sha256(scene),
        "robots":robots,"tasks":tasks,
        "loss_percent":round(loss*100),
        "votes_per_voter":1000,"policy":"optimized_rank_square",
        "k":5,"epsilon":0.0,
        "intent_repetitions":3,
        "decision_repetitions":3,
        "announcement_repetitions":3,
        "max_rounds":101,
        "initial_intent_count":len(vote_run.robot_claims),
        "initial_duplicate_tasks":initial_duplicate,
        "initial_unassigned_tasks":initial_missing,
        "initial_unique_percent":100*initial_unique/tasks,
        "executed_count":len(executed),
        "reserved_count":len(owner_result.reserved_pairs),
        "unique_completion_percent":100*len(executed)/tasks,
        "unassigned_task_count":tasks-len(executed),
        "duplicate_task_count":0,"full_valid_allocation":full,
        "partial_actual_cost":actual_cost,
        "actual_cost_if_valid":actual_cost if full else "",
        "global_greedy_cost":reference,
        "cost_gap_percent_if_valid":(100*(actual_cost/reference-1)
                                      if full else ""),
        "rounds_executed":owner_result.rounds_executed,
        "owner_observed_conflicts":owner_result.owner_observed_conflicts,
        "peer_observed_challenges":owner_result.peer_observed_challenges,
        "challenge_deferrals":owner_result.challenge_deferrals,
        "denial_receipts":owner_result.denial_receipts,
        "retargeted_intents":owner_result.retargeted_intents,
        "intents_seen_by_owner":owner_result.intents_seen_by_owner,
        "sender_sends":expected_count,"sender_bytes":expected_bytes,
        "cost_receiver_drops":sum(
            1 for obs in observations if obs.phase=="cost" and not obs.delivered),
        "vote_receiver_drops":sum(
            1 for obs in observations if obs.phase=="vote" and not obs.delivered),
        "native_stop_ms":max(
            (event.arrival_time_ms for event in task_trace.events),
            default=0.0,
        )+owner_result.finish_ms,
        "owner_finish_ms":owner_result.finish_ms,
        "first_failure_owner":failure.owner if failure else "",
        "first_failure_function":failure.function if failure else "",
        "first_failure_category":failure.category if failure else "",
        "first_failure_code":failure.code if failure else "",
        "first_failure_json":(
            json.dumps(asdict(failure),ensure_ascii=False,
                       separators=(",",":")) if failure else ""),
        "executed_pairs_json":json.dumps(executed,separators=(",",":")),
        "reserved_pairs_json":json.dumps(
            owner_result.reserved_pairs,separators=(",",":"),
        ),
    }
    for phase in PHASES:
        row[phase+"_sends"]=phases.get(phase,{}).get("sends",0)
        row[phase+"_bytes"]=phases.get(phase,{}).get("bytes",0)
        if phase not in ("task",):
            row[phase+"_receiver_drops"]=sum(
                1 for obs in observations
                if obs.phase==phase and not obs.delivered
            )
    return row


def run_one_p2r_case(*,scene,profile,loss,source_sha,args,capture_audit):
    """One real P2Q source epoch and P2R ownership; no alternate arm."""
    task_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    loss_sampler=BernoulliLossSampler(scene.seed)
    task_trace=broadcast_task_information(
        task_positions=scene.task_positions,
        num_robots=scene.num_robots,
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
    vote_run=simulate_p2k_local_vote_epoch(
        cost_matrix=costs,sampler=coord_sampler,
        loss_sampler=loss_sampler,p_loss=loss,
        phase_timeout_ms=guard,seed=scene.seed,votes_per_voter=1000,
        policy="optimized_rank_square",k=5,epsilon=0.0,
        temperature=args.temperature,
    )
    owner_result=coordinate_p2r_announced_intents(
        run=vote_run,cost_matrix=costs,votes_per_voter=1000,
        sampler=coord_sampler,loss_sampler=loss_sampler,
        p_loss=loss,max_rounds=args.max_rounds,
        intent_repetitions=args.intent_repetitions,
        decision_repetitions=args.decision_repetitions,
        announcement_repetitions=args.announcement_repetitions,
    )
    row=make_p2r_evidence_row(
        scene=scene,source_sha=source_sha,loss=loss,
        vote_run=vote_run,task_trace=task_trace,
        task_sampler=task_sampler,coord_sampler=coord_sampler,
        owner_result=owner_result,
    )
    row.update({
        "intent_repetitions":args.intent_repetitions,
        "decision_repetitions":args.decision_repetitions,
        "announcement_repetitions":args.announcement_repetitions,
        "max_rounds":args.max_rounds,
    })
    audit=None
    if capture_audit:
        audit={
            "source_sha":source_sha,"seed":scene.seed,
            "scene_sha256":row["scene_sha256"],"loss_percent":row["loss_percent"],
            "source":"one original local-only P2Q Cost/Vote epoch",
            "initial_local_self_intents":vote_run.robot_claims,
            "local_cost_visible_rows":[sorted(row)
                                       for row in vote_run.cost_visible_rows],
            "per_robot_local_assignment":vote_run.local_assignments,
            "per_robot_received_vote_matrices":vote_run.local_vote_views,
            "owner_decisions":owner_result.decisions,
            "owner_reserved_pairs":owner_result.reserved_pairs,
            "actual_granted_execution_pairs":owner_result.executed_pairs,
            "per_receiver_actual_execution_knowledge":
                owner_result.recipient_seen_executing_tasks,
            "physical_owner_control_sends":[asdict(event)
                for event in owner_result.events],
            "physical_owner_receiver_observations":[asdict(obs)
                for obs in owner_result.deliveries],
            "first_diagnostic":(asdict(owner_result.first_diagnostic)
                                if owner_result.first_diagnostic else None),
        }
    return row,audit


def save_p2r_evidence(*,root,rows,config,source_sha):
    summary=summarize_p2r_rows(rows)
    with (root/"summary_p2r.csv").open("x",newline="",
                                     encoding="utf-8") as file:
        w=csv.DictWriter(file,fieldnames=SUMMARY_FIELDS,extrasaction="raise")
        w.writeheader()
        w.writerows(summary)
    sources=(
        root/"per_seed_p2r.csv",root/"summary_p2r.csv",
        root/"audit_p2r.jsonl",root/"run_config_p2r.json",
    )
    manifest={
        "study":STUDY,"source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),"groups":len(summary),"config":config,
        "sha256":{p.name:sha256_file(p) for p in sources},
        "notice":"P2R ONLY. No new Cost/Vote protocol or hidden global "
                 "fallback. Same-source private rank-square matching "
                 "drives 3x INTENT broadcasts. Only owner-received INTENT "
                 "may reserve, 16B challenge only when a contestant "
                 "heard a rival, 20B COMMIT to sole winner, 20B DENY "
                 "only to physically observed loser, 3x P2NX on receipt. "
                 "No ACK or silence-as-approval. All SENDs including "
                 "failed attempts counted; no crash-tolerant consensus proof.",
    }
    (root/"manifest_p2r.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8",
    )


def run_p2r(args):
    losses=validate_p2r_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2r","state","P2R_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only directory",actual=str(root))
    source_sha=read_source_sha()
    root.mkdir(parents=True)
    config={
        "study":STUDY,"source_sha":source_sha,
        "robots":args.robots,"tasks":args.tasks,
        "seed_count":args.seeds,"first_seed":args.first_seed,
        "loss_percent":losses,"votes":1000,
        "k":5,"epsilon":0.0,"temperature":args.temperature,
        "intent_repetitions":args.intent_repetitions,
        "decision_repetitions":args.decision_repetitions,
        "announcement_repetitions":args.announcement_repetitions,
        "max_rounds":args.max_rounds,
        "audit_seeds":args.audit_seeds,
        "only_method":STUDY,
        "initial_data":"original sender-paid model-reliable TASK, "
                       "one lossy Cost and one 1016B P2KV Vote per robot",
        "announcement":"only each robot's own local nomination; 3x 28B P2RI",
        "challenge":"16B P2RH from actual local conflicting contestant; "
                    "advisory owner may defer one round",
        "decision":"fixed Task Owner commits irrevocably, 3x 20B P2RC "
                   "to winner; only observed losers get 3x 20B P2RD",
        "execution":"3x original 20B P2NX only after actual P2RC receipt",
        "safety":"silence never approval, no other hidden owner; "
                 "P2RC lost means incomplete unless re-announced",
        "time":"one shared causal 144Mbps Rady WiFi6 sensitivity proxy, "
               "known-roster round barriers; CPU optimizer time excluded",
    }
    (root/"run_config_p2r.json").write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8",
    )
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows=[]
    with (root/"per_seed_p2r.csv").open("x",newline="",
                                        encoding="utf-8") as file, \
         (root/"audit_p2r.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(file,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,args.robots,args.tasks)
                row,audit=run_one_p2r_case(
                    scene=scene,profile=profile,
                    loss=loss/100,source_sha=source_sha,args=args,
                    capture_audit=seed<args.first_seed+args.audit_seeds,
                )
                if set(row)!=set(FIELDS):
                    fail("run_p2r","contract","P2R_OUTPUT_SCHEMA_MISMATCH",
                         expected=sorted(FIELDS),actual=sorted(row))
                writer.writerow(row)
                file.flush()
                rows.append(row)
                if audit is not None:
                    audit_file.write(json.dumps(
                        audit,ensure_ascii=False,separators=(",",":"))+"\n")
                    audit_file.flush()
                print(
                    f"P2R loss={loss}% seed={seed} "
                    f"unique={row['unique_completion_percent']:.1f}% "
                    f"missing={row['unassigned_task_count']} "
                    f"duplicate={row['duplicate_task_count']} "
                    f"rounds={row['rounds_executed']} "
                    f"conflict={row['owner_observed_conflicts']} "
                    f"challenges={row['peer_observed_challenges']} "
                    f"bytes={row['sender_bytes']} "
                    f"finish_s={row['native_stop_ms']/1000:.2f}",
                    flush=True,
                )
    save_p2r_evidence(root=root,rows=rows,config=config,source_sha=source_sha)
    print(
        f"P2R_COMPLETE cases={len(rows)} "
        f"groups={len(summarize_p2r_rows(rows))} root={root}",
        flush=True,
    )


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50,0.90")
    parser.add_argument("--votes",default="1000")
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=100)
    parser.add_argument("--seeds",type=int,default=10)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--k",type=int,default=5)
    parser.add_argument("--epsilon",type=float,default=0.0)
    parser.add_argument("--max-rounds",type=int,default=101)
    parser.add_argument("--intent-repetitions",type=int,default=3)
    parser.add_argument("--decision-repetitions",type=int,default=3)
    parser.add_argument("--announcement-repetitions",type=int,default=3)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2r(parse_args(argv))


if __name__=="__main__":
    main()
