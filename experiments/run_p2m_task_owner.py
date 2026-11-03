"""P2M: ONLY new fixed per-task owner arbitration after 1000 Softmax votes.

No P2K local-only, no P2L idealized CLAIM and no old comparison arms
are executed. Each task owner sees only physically confirmed unicast
candidate CLAIMs and replies only to those candidates. Observed
collisions before arbitration are diagnostic, NOT an experiment arm.
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

from democracy_mrta.claim_resolution import coordinate_p2m_task_owners
from democracy_mrta.coordination import simulate_p2k_local_vote_epoch
from democracy_mrta.diagnostics import Diagnostic,ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,ensure_rady_dataset,load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information,reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler
from experiments.run_p1_matched_five import (
    DEFAULT_RADY,read_source_sha,scene_sha256,sha256_file,
)
from experiments.run_p2l_claim_conflicts import compute_p2l_vote_view_similarity

OWNER="experiments.run_p2m_task_owner"
STUDY="P2M_1000_SOFTMAX_FIXED_TASK_OWNER_ONLY"
PHASES=(
    "task","cost","vote","owner_request","owner_request_ack",
    "owner_decision","owner_decision_ack",
)
FIELDS=(
    "source_sha","seed","scene_sha256","robots","tasks","loss_percent",
    "votes_per_voter","temperature","max_attempts","max_rounds",
    "preclaim_duplicate_tasks","preclaim_unassigned_tasks",
    "preclaim_unique_percent","vote_view_similarity_percent",
    "unique_task_completion_percent","task_coverage_percent",
    "duplicate_task_count","unassigned_task_count",
    "full_valid_allocation","actual_cost_if_valid","partial_actual_cost",
    "initial_claim_count","executed_count","reserved_count",
    "blocked_robot_count","request_receipt_ack_timeouts","rounds_executed",
    "conflicted_task_rounds","reassignment_requests",
    "sender_sends","sender_bytes",
    "task_sends","task_bytes","cost_sends","cost_bytes",
    "vote_sends","vote_bytes",
    "owner_request_sends","owner_request_bytes",
    "owner_request_ack_sends","owner_request_ack_bytes",
    "owner_decision_sends","owner_decision_bytes",
    "owner_decision_ack_sends","owner_decision_ack_bytes",
    "cost_receiver_drops","vote_receiver_drops",
    "owner_request_receiver_drops","owner_request_ack_receiver_drops",
    "owner_decision_receiver_drops","owner_decision_ack_receiver_drops",
    "native_stop_ms","first_owner_failure","first_owner_failure_json",
    "execution_pairs_json","reserved_pairs_json",
)
SUMMARY_FIELDS=(
    "loss_percent","seeds","full_valid_percent",
    "mean_unique_task_completion_percent","mean_coverage_percent",
    "mean_duplicate_tasks","mean_unassigned_tasks",
    "mean_preclaim_duplicates","mean_preclaim_unique_percent",
    "mean_vote_similarity_percent","mean_rounds",
    "mean_conflicted_task_rounds","mean_reassignments",
    "mean_blocked_robots","mean_request_receipt_ack_timeouts","mean_send_kB",
    "mean_extra_owner_kB","mean_stop_s",
    "valid_cost_seeds","mean_valid_actual_cost",
)


def fail(function,category,code,*,expected=None,actual=None,details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2m_axes(args):
    """One new method only; reproducible bounded 10-seed study."""
    try:
        raw=tuple(float(x.strip()) for x in args.losses.split(","))
    except (ValueError,TypeError,AttributeError) as exc:
        fail("validate_p2m_axes","data","P2M_BAD_LOSS_GRID",actual=str(exc))
    losses=tuple(int(round(p*100)) for p in raw if math.isfinite(p))
    valid=(
        len(losses)==len(raw) and losses
        and losses==tuple(sorted(set(losses)))
        and all(0<=p<=90 and abs(l/100-p)<1e-12 for l,p in zip(losses,raw))
        and type(args.robots) is int and 2<=args.robots<=100
        and type(args.tasks) is int and 1<=args.tasks<=args.robots
        and type(args.votes) is int and args.votes==1000
        and args.votes%args.tasks==0
        and type(args.seeds) is int and 1<=args.seeds<=100
        and type(args.first_seed) is int and args.first_seed>=0
        and args.first_seed+args.seeds<=100
        and type(args.temperature) in (float,int)
        and math.isfinite(args.temperature) and args.temperature>0
        and type(args.max_attempts) is int and 1<=args.max_attempts<=128
        and type(args.max_rounds) is int and 1<=args.max_rounds<=255
        and type(args.audit_seeds) is int and args.audit_seeds>=0
    )
    if not valid:
        fail("validate_p2m_axes","data","P2M_INVALID_EXPERIMENT_AXIS",
             expected="1000 tickets divisible by tasks, robots 2..100, "
                      "seeds 0..99, ascending loss 0..90%, retries 1..128, "
                      "rounds 1..255, positive tau",
             actual=vars(args))
    return losses


def analyze_p2m_owner_result(*,scene,local_run,owner_result):
    """Independent offline evidence only; never repairs robot/task decisions."""
    robots,tasks=scene.num_robots,scene.num_tasks
    initial_claims=local_run.robot_claims
    before=[0]*tasks
    for robot,task in initial_claims:before[task]+=1
    after=[0]*tasks
    executed=owner_result.executed_pairs
    for robot,task in executed:
        if robot not in range(robots) or task not in range(tasks):
            fail("analyze_p2m_owner_result","safety",
                 "P2M_OUT_OF_RANGE_EXECUTOR",actual=(robot,task))
        after[task]+=1
    if any(c>1 for c in after) or len({r for r,t in executed})!=len(executed):
        fail("analyze_p2m_owner_result","safety",
             "P2M_TASK_OWNER_DUPLICATE_EXECUTION",
             expected="each robot <=1 task, each task <=1 robot",
             actual=executed)
    cost=sum(scene.cost_matrix[robot][task] for robot,task in executed)
    full=int(len(executed)==tasks)
    return {
        "preclaim_duplicate_tasks":sum(n>1 for n in before),
        "preclaim_unassigned_tasks":sum(n==0 for n in before),
        "preclaim_unique_percent":100*sum(n==1 for n in before)/tasks,
        "vote_view_similarity_percent":compute_p2l_vote_view_similarity(
            local_run.local_vote_views),
        "unique_task_completion_percent":100*sum(n==1 for n in after)/tasks,
        "task_coverage_percent":100*sum(n>0 for n in after)/tasks,
        "duplicate_task_count":sum(n>1 for n in after),
        "unassigned_task_count":sum(n==0 for n in after),
        "full_valid_allocation":full,
        "actual_cost_if_valid":cost if full else "",
        "partial_actual_cost":cost,
        "initial_claim_count":len(initial_claims),
        "executed_count":len(executed),
        "reserved_count":len(owner_result.reserved_pairs),
        "blocked_robot_count":len(owner_result.blocked_robot_ids),
        "request_receipt_ack_timeouts":(
            owner_result.request_receipt_ack_timeouts),
        "rounds_executed":owner_result.rounds_executed,
        "conflicted_task_rounds":owner_result.conflicted_task_rounds,
        "reassignment_requests":owner_result.reassignment_requests,
        "execution_pairs_json":json.dumps(executed,separators=(",",":")),
        "reserved_pairs_json":json.dumps(
            owner_result.reserved_pairs,separators=(",",":")),
    }


def run_one_p2m_case(*,scene,profile,loss,votes,temperature,
                     max_attempts,max_rounds,source_sha,capture_audit):
    """One physical Cost/Softmax/Vote epoch + only new task-owner unicast."""
    robots=scene.num_robots
    loss_sampler=BernoulliLossSampler(scene.seed)
    task_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    task_wire=broadcast_task_information(
        task_positions=scene.task_positions,num_robots=robots,
        sampler=task_sampler,loss_sampler=loss_sampler,
        p_loss=0.0,phase_timeout_ms=1e9,
    )
    local_costs=reconstruct_local_cost_rows(
        local_robot_positions=scene.robot_positions,
        announced_tasks_by_robot=task_wire.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=local_costs,expected=scene.cost_matrix,
    )
    local_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    guard=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=robots,
        total_tasks=scene.num_tasks,reference_phy_mbps=144.0,
    )
    local=simulate_p2k_local_vote_epoch(
        cost_matrix=local_costs,sampler=local_sampler,
        loss_sampler=loss_sampler,p_loss=loss,
        phase_timeout_ms=guard,seed=scene.seed,
        votes_per_voter=votes,policy="cost_softmax",
        temperature=temperature,
    )
    owner_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    result=coordinate_p2m_task_owners(
        run=local,cost_matrix=local_costs,
        votes_per_voter=votes,sampler=owner_sampler,
        loss_sampler=loss_sampler,p_loss=loss,
        max_attempts=max_attempts,max_rounds=max_rounds,
    )
    all_events=tuple(task_wire.events)+local.events+result.events
    stage={"task":tuple(task_wire.events),"cost":tuple(
        e for e in local.events if e.phase=="cost"),
        "vote":tuple(e for e in local.events if e.phase=="vote")}
    for phase in PHASES[3:]:
        stage[phase]=tuple(e for e in result.events if e.phase==phase)
    if (any(e.phase not in (("task_announcement",)+PHASES[1:]) for e in all_events)
            or len(stage["cost"])!=robots or len(stage["vote"])!=robots
            or sum(len(v) for v in stage.values())!=len(all_events)):
        fail("run_one_p2m_case","contract","P2M_UNEXPECTED_NETWORK_PHASE",
             expected=PHASES,actual=[e.phase for e in all_events])
    models=(
        (task_sampler,task_wire.events),
        (local_sampler,local.events),
        (owner_sampler,result.events),
    )
    for sampler,events in models:
        network=sampler.summarize_network()
        if (network["packet_count"]!=len(events)
                or network["application_sender_bytes"]
                !=sum(e.payload_bytes for e in events)):
            fail("run_one_p2m_case","contract",
                 "P2M_SEND_LEDGER_MISMATCH",
                 expected={"sends":len(events),
                           "bytes":sum(e.payload_bytes for e in events)},
                 actual={"sends":network["packet_count"],
                         "bytes":network["application_sender_bytes"]})
    metrics=analyze_p2m_owner_result(
        scene=scene,local_run=local,owner_result=result,
    )
    first=result.first_diagnostic
    row={
        "source_sha":source_sha,"seed":scene.seed,
        "scene_sha256":scene_sha256(scene),
        "robots":robots,"tasks":scene.num_tasks,
        "loss_percent":round(loss*100),"votes_per_voter":votes,
        "temperature":temperature,"max_attempts":max_attempts,
        "max_rounds":max_rounds,**metrics,
        "sender_sends":len(all_events),
        "sender_bytes":sum(e.payload_bytes for e in all_events),
        "cost_receiver_drops":sum(
            e.phase=="cost" and not e.delivered for e in local.deliveries),
        "vote_receiver_drops":sum(
            e.phase=="vote" and not e.delivered for e in local.deliveries),
        "native_stop_ms":max(
            (e.arrival_time_ms for e in task_wire.events),default=0.0
        )+result.finish_ms,
        "first_owner_failure":(
            f"{first.owner}/{first.function}/{first.category}/{first.code}"
            if first is not None else ""),
        "first_owner_failure_json":(
            json.dumps(asdict(first),ensure_ascii=False,separators=(",",":"))
            if first is not None else ""),
    }
    for phase in PHASES:
        row[phase+"_sends"]=len(stage[phase])
        row[phase+"_bytes"]=sum(e.payload_bytes for e in stage[phase])
        if phase.startswith("owner_"):
            row[phase+"_receiver_drops"]=sum(
                e.phase==phase and not e.delivered for e in result.deliveries)
    if set(row)!=set(FIELDS):
        fail("run_one_p2m_case","contract","P2M_RAW_FIELD_SCHEMA_MISMATCH",
             expected=sorted(FIELDS),actual=sorted(row))
    audit=None
    if capture_audit:
        audit={
            "source_sha":source_sha,"seed":scene.seed,
            "loss_percent":round(loss*100),"votes_per_voter":votes,
            "owner_rule":"task_id % robots",
            "per_robot_own_vote_support_rows":tuple(
                local.local_vote_views[r][r] for r in range(robots)),
            "per_robot_actual_receipt_counts":tuple(
                sum(sum(row) for row in local.local_vote_views[r])//votes
                for r in range(robots)),
            "original_private_assignment":local.local_assignments,
            "original_self_claims":local.robot_claims,
            "per_task_owner_decision_records":result.owner_decisions,
            "blocked_robot_ids":result.blocked_robot_ids,
            "request_receipt_ack_timeouts":result.request_receipt_ack_timeouts,
            "actual_executions":result.executed_pairs,
            "irreversible_task_reservations":result.reserved_pairs,
            "first_failure":asdict(first) if first is not None else None,
        }
    return row,audit


def summarize_p2m_rows(rows):
    def mean(records,field):
        return sum(float(r[field]) for r in records)/len(records)
    groups={}
    for row in rows:
        groups.setdefault(row["loss_percent"],[]).append(row)
    summary=[]
    for loss,group in sorted(groups.items()):
        full=[r for r in group if r["full_valid_allocation"]]
        extra=lambda r:sum(int(r[p+"_bytes"]) for p in PHASES[3:])
        summary.append({
            "loss_percent":loss,"seeds":len(group),
            "full_valid_percent":100*len(full)/len(group),
            "mean_unique_task_completion_percent":mean(
                group,"unique_task_completion_percent"),
            "mean_coverage_percent":mean(group,"task_coverage_percent"),
            "mean_duplicate_tasks":mean(group,"duplicate_task_count"),
            "mean_unassigned_tasks":mean(group,"unassigned_task_count"),
            "mean_preclaim_duplicates":mean(group,"preclaim_duplicate_tasks"),
            "mean_preclaim_unique_percent":mean(
                group,"preclaim_unique_percent"),
            "mean_vote_similarity_percent":mean(
                group,"vote_view_similarity_percent"),
            "mean_rounds":mean(group,"rounds_executed"),
            "mean_conflicted_task_rounds":mean(
                group,"conflicted_task_rounds"),
            "mean_reassignments":mean(group,"reassignment_requests"),
            "mean_blocked_robots":mean(group,"blocked_robot_count"),
            "mean_request_receipt_ack_timeouts":mean(
                group,"request_receipt_ack_timeouts"),
            "mean_send_kB":mean(group,"sender_bytes")/1000,
            "mean_extra_owner_kB":sum(extra(r) for r in group)/len(group)/1000,
            "mean_stop_s":mean(group,"native_stop_ms")/1000,
            "valid_cost_seeds":len(full),
            "mean_valid_actual_cost":mean(full,"actual_cost_if_valid") if full else "",
        })
    return summary


def save_p2m_evidence(*,root,rows,config,source_sha):
    summary=summarize_p2m_rows(rows)
    with (root/"summary_p2m.csv").open("x",newline="",encoding="utf-8") as file:
        w=csv.DictWriter(file,fieldnames=SUMMARY_FIELDS)
        w.writeheader();w.writerows(summary)
    sources=[
        root/"per_seed_p2m.csv",root/"summary_p2m.csv",
        root/"audit_p2m.jsonl",root/"run_config_p2m.json",
    ]
    manifest={
        "study":STUDY,"source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),"loss_groups":len(summary),"config":config,
        "sha256":{p.name:sha256_file(p) for p in sources},
        "notice":"ONLY task_owner method was executed. TASK is initially "
                 "model-reliable and sender-paid, owner protocol is receiver "
                 "lossy and ACK bounded. No oracle recovery and no old arms. "
                 "Task owners reserve irrevocably: a missed GRANT may strand "
                 "a task, but cannot create duplicate execution.",
    }
    (root/"manifest_p2m.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8",
    )


def run_p2m(args):
    losses=validate_p2m_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2m","state","P2M_OUTPUT_ALREADY_EXISTS",
             expected="new append-only output",actual=str(root))
    source_sha=read_source_sha()
    root.mkdir(parents=True)
    config={
        "study":STUDY,"source_sha":source_sha,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "robots":args.robots,"tasks":args.tasks,
        "votes":args.votes,"temperature":args.temperature,
        "loss_percent":losses,"max_attempts":args.max_attempts,
        "max_rounds":args.max_rounds,"audit_seeds":args.audit_seeds,
        "method":"task_owner ONLY; no other arms executed",
        "owner_map":"task_id % num_robots",
        "cost_vote":"one lossy Cost and one task-balanced 1000-ticket "
                    "P2KV broadcast per robot",
        "owner_wire":"28B P2LC unicast plus 16B per-owner receipt ACK; "
                     "20B owner GRANT/REJECT plus 16B decision ACK",
        "safety":"GRANT irrevocable; no unconfirmed robot execution; "
                 "unreachable candidate blocked, never oracle repaired",
        "external_tasks":"model-reliable sender-paid TASK",
        "runtime":"Rady-based hypothesized 144Mbps Wi-Fi 6 shared-medium "
                  "proxy; CPU optimization time not modeled",
    }
    (root/"run_config_p2m.json").write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8",
    )
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows=[]
    with (root/"per_seed_p2m.csv").open("x",newline="",encoding="utf-8") as raw, \
         (root/"audit_p2m.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(raw,fieldnames=FIELDS)
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,args.robots,args.tasks)
                row,audit=run_one_p2m_case(
                    scene=scene,profile=profile,loss=loss/100,
                    votes=args.votes,temperature=args.temperature,
                    max_attempts=args.max_attempts,
                    max_rounds=args.max_rounds,
                    source_sha=source_sha,
                    capture_audit=seed<args.first_seed+args.audit_seeds,
                )
                writer.writerow(row)
                raw.flush()
                rows.append(row)
                if audit is not None:
                    audit_file.write(json.dumps(
                        audit,ensure_ascii=False,separators=(",",":"))+"\n")
                print(
                    f"P2M loss={loss}% seed={seed} 1000-Softmax "
                    f"pre_collision={row['preclaim_duplicate_tasks']} "
                    f"post_duplicate={row['duplicate_task_count']} "
                    f"unique={row['unique_task_completion_percent']:.1f}% "
                    f"missing={row['unassigned_task_count']} "
                    f"blocked={row['blocked_robot_count']} "
                    f"SEND_bytes={row['sender_bytes']}",flush=True,
                )
    save_p2m_evidence(root=root,rows=rows,config=config,source_sha=source_sha)
    print(f"P2M_COMPLETE cases={len(rows)} "
          f"loss_groups={len(summarize_p2m_rows(rows))} root={root}",flush=True)


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--losses",default="0.00,0.30,0.50,0.90")
    p.add_argument("--votes",type=int,default=1000)
    p.add_argument("--seeds",type=int,default=10)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--robots",type=int,default=100)
    p.add_argument("--tasks",type=int,default=100)
    p.add_argument("--temperature",type=float,default=5.0)
    p.add_argument("--max-attempts",type=int,default=24)
    p.add_argument("--max-rounds",type=int,default=101)
    p.add_argument("--audit-seeds",type=int,default=1)
    p.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    p.add_argument("--output-root",type=Path,required=True)
    return p.parse_args(argv)


def main(argv=None):
    run_p2m(parse_args(argv))


if __name__=="__main__":
    main()
