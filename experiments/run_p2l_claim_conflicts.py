"""P2L paired 1000-ticket Softmax: local-only vs small conflict CLAIMs.

All arms start from the SAME original P2K Cost/Vote physical SEND and
receiver-specific local decisions. The conflict arm sends only candidate's
own CLAIM evidence; it never publishes global PSCR/Score or a global
Vote matrix. Bounded ACK arms charge lossy CLAIM retries and ACK SENDs.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import platform
from pathlib import Path
import sys

import numpy as np

from democracy_mrta.claim_resolution import coordinate_p2l_claims
from democracy_mrta.coordination import simulate_p2k_local_vote_epoch
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
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
from experiments.run_p2k_consensus_free import analyze_p2k_local_claims

OWNER="experiments.run_p2l_claim_conflicts"
STUDY="P2L_1000_SOFTMAX_CONFLICT_ONLY_PAIRED"
CHANNELS=("bounded_ack", "ideal_paid")
FIELDS=(
    "source_sha","seed","scene_sha256","robots","tasks",
    "loss_percent","votes_per_voter","temperature","arm","channel",
    "preclaim_unique_percent","preclaim_duplicate_tasks",
    "preclaim_unassigned_tasks","preclaim_assignment_agreement_percent",
    "corrected_preclaim_vote_similarity_percent",
    "unique_task_completion_percent","task_coverage_percent",
    "duplicate_task_count","unassigned_task_count",
    "full_valid_allocation","claimed_cost_if_valid",
    "cost_gap_percent_if_valid","partial_claim_cost","global_greedy_cost",
    "task_sender_sends","task_sender_bytes",
    "cost_sender_sends","cost_sender_bytes",
    "vote_sender_sends","vote_sender_bytes",
    "claim_sender_sends","claim_sender_bytes",
    "ack_sender_sends","ack_sender_bytes",
    "total_sender_sends","total_sender_bytes",
    "cost_receiver_drops","vote_receiver_drops",
    "claim_receiver_drops","ack_receiver_drops",
    "claim_rounds","conflict_task_rounds","reassignment_claims",
    "initial_conflict_tasks","claim_exchange_complete",
    "claim_diagnostic","claim_diagnostic_json","native_stop_ms","execution_pairs_json",
)
SUMMARY_FIELDS=(
    "arm","loss_percent","votes_per_voter","seeds",
    "full_valid_percent","mean_unique_completion_percent",
    "mean_task_coverage_percent","mean_duplicate_tasks",
    "mean_unassigned_tasks","mean_preclaim_unique_percent",
    "mean_preclaim_assignment_agreement_percent",
    "mean_corrected_vote_similarity_percent",
    "mean_sender_kB","mean_claim_kB","mean_ack_kB",
    "mean_stop_s","mean_claim_rounds",
    "mean_reassignment_claims","claim_exchange_failure_percent",
    "valid_cost_seeds","mean_valid_cost_gap_percent",
)


def fail(function: str,category: str,code: str,*,expected=None,actual=None,
         details: str="") -> None:
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2l_axes(args) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """A small matched hypothesis test; default 10 seeds, 1000 votes."""
    try:
        raw_loss=tuple(float(s.strip()) for s in args.losses.split(","))
        channels=tuple(x.strip() for x in args.channels.split(","))
    except (TypeError,AttributeError,ValueError) as exc:
        fail("validate_p2l_axes","data","P2L_INVALID_AXIS_TEXT",
             actual=str(exc))
    losses=tuple(int(round(100*x)) for x in raw_loss if math.isfinite(x))
    valid=(
        losses and len(losses)==len(raw_loss)
        and losses==tuple(sorted(set(losses)))
        and all(0<=p<=90 and abs(x-p/100)<1e-12
                for p,x in zip(losses,raw_loss))
        and channels and len(channels)==len(set(channels))
        and all(c in CHANNELS for c in channels)
        and type(args.robots) is int and 2<=args.robots<=100
        and type(args.tasks) is int and 1<=args.tasks<=args.robots
        and type(args.votes) is int and args.votes==1000
        and args.votes%args.tasks==0
        and type(args.seeds) is int and 1<=args.seeds<=100
        and type(args.first_seed) is int and args.first_seed>=0
        and args.first_seed+args.seeds<=100
        and type(args.temperature) in (float,int)
        and math.isfinite(args.temperature) and args.temperature>0
        and type(args.max_claim_attempts) is int
        and 1<=args.max_claim_attempts<=128
        and type(args.max_claim_rounds) is int
        and 1<=args.max_claim_rounds<=255
        and type(args.audit_seeds) is int and args.audit_seeds>=0
    )
    if not valid:
        fail("validate_p2l_axes","data","P2L_INVALID_EXPERIMENT_AXES",
             expected="0..90% loss, 1000 tickets divisible by tasks, "
                      "100R100T default, <=100 seeds, bounded_ack/ideal_paid, "
                      "1..128 retries and 1..255 claim rounds",
             actual=vars(args))
    return losses,channels


def compute_p2l_vote_view_similarity(
    local_views: tuple[tuple[tuple[int, ...], ...], ...],
) -> float:
    """Correct mean per-task TV calculation; does NOT mutate historical P2K."""
    data=np.asarray(local_views,dtype=np.float64)
    totals=data.sum(axis=1,keepdims=True)
    distribution=np.divide(data,totals,out=np.zeros_like(data),where=totals>0)
    mean=distribution.mean(axis=0,keepdims=True)
    tv=0.5*np.abs(distribution-mean).sum(axis=1)
    similarity=100.0*(1.0-float(tv.mean()))
    if not -1e-8<=similarity<=100.0+1e-8:
        fail("compute_p2l_vote_view_similarity","contract",
             "P2L_INVALID_VOTE_SIMILARITY",
             expected="[0,100]",actual=similarity)
    return min(100.0,max(0.0,similarity))


def analyze_p2l_actual_executions(
    *, scene, pairs: tuple[tuple[int,int], ...], reference_cost: float,
) -> dict:
    """OFFLINE only; no hidden global assignment or fixed duplicates online."""
    robots,tasks=scene.num_robots,scene.num_tasks
    counts=[0]*tasks
    robot_ids=[]
    for robot,task in pairs:
        if robot not in range(robots) or task not in range(tasks):
            fail("analyze_p2l_actual_executions","data",
                 "P2L_EXECUTOR_ID_OUT_OF_RANGE",actual=(robot,task))
        counts[task]+=1
        robot_ids.append(robot)
    if len(set(robot_ids))!=len(robot_ids):
        fail("analyze_p2l_actual_executions","safety",
             "P2L_EXECUTOR_CAPACITY_VIOLATION",
             expected="robot at most one task",actual=tuple(robot_ids))
    unique=sum(c==1 for c in counts)
    duplicate=sum(c>1 for c in counts)
    unassigned=sum(c==0 for c in counts)
    valid=int(unique==tasks and duplicate==0)
    partial_cost=sum(scene.cost_matrix[r][t] for r,t in pairs)
    return {
        "unique_task_completion_percent":100.0*unique/tasks,
        "task_coverage_percent":100.0*(tasks-unassigned)/tasks,
        "duplicate_task_count":duplicate,
        "unassigned_task_count":unassigned,
        "full_valid_allocation":valid,
        "claimed_cost_if_valid":partial_cost if valid else "",
        "cost_gap_percent_if_valid":(
            100.0*(partial_cost/reference_cost-1) if valid else ""
        ),
        "partial_claim_cost":partial_cost,
        "execution_pairs_json":json.dumps(pairs,separators=(",",":")),
    }


def run_p2l_paired_seed(
    *, scene, profile, loss: float, votes: int, channels: tuple[str,...],
    source_sha: str, temperature: float, max_claim_attempts: int,
    max_claim_rounds: int, capture_audit: bool,
) -> tuple[list[dict], list[dict]]:
    """One source Cost/Vote trace; each alternative CLAIM channel is a paired arm."""
    robots=scene.num_robots
    loss_sampler=BernoulliLossSampler(scene.seed)
    task_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    task_trace=broadcast_task_information(
        task_positions=scene.task_positions,num_robots=robots,
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
    vote_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    cost_guard=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=robots,total_tasks=scene.num_tasks,
        reference_phy_mbps=144.0,
    )
    run=simulate_p2k_local_vote_epoch(
        cost_matrix=costs,sampler=vote_sampler,loss_sampler=loss_sampler,
        p_loss=loss,phase_timeout_ms=cost_guard,seed=scene.seed,
        votes_per_voter=votes,policy="cost_softmax",
        temperature=temperature,
    )
    if ({e.phase for e in run.events} != {"cost","vote"}
            or sum(e.phase=="cost" for e in run.events)!=robots
            or sum(e.phase=="vote" for e in run.events)!=robots):
        fail("run_p2l_paired_seed","contract","P2L_COST_VOTE_SEND_CONTRACT",
             expected={"cost":robots,"vote":robots},
             actual=[e.phase for e in run.events])
    source_network=task_sampler.summarize_network()
    vote_network=vote_sampler.summarize_network()
    if (source_network["packet_count"]!=len(task_trace.events)
            or source_network["application_sender_bytes"]!=task_trace.sender_bytes
            or vote_network["packet_count"]!=len(run.events)
            or vote_network["application_sender_bytes"]!=run.sender_bytes):
        fail("run_p2l_paired_seed","contract","P2L_SOURCE_NETWORK_LEDGER_MISMATCH",
             expected=(len(task_trace.events),task_trace.sender_bytes,
                       len(run.events),run.sender_bytes),
             actual=(source_network["packet_count"],
                     source_network["application_sender_bytes"],
                     vote_network["packet_count"],
                     vote_network["application_sender_bytes"]))
    original=analyze_p2k_local_claims(scene=scene,run=run)
    similarity=compute_p2l_vote_view_similarity(run.local_vote_views)
    cost_events=[e for e in run.events if e.phase=="cost"]
    vote_events=[e for e in run.events if e.phase=="vote"]
    shared={
        "source_sha":source_sha,"seed":scene.seed,
        "scene_sha256":scene_sha256(scene),
        "robots":robots,"tasks":scene.num_tasks,
        "loss_percent":round(loss*100),"votes_per_voter":votes,
        "preclaim_unique_percent":original["unique_task_completion_percent"],
        "preclaim_duplicate_tasks":original["duplicate_task_count"],
        "preclaim_unassigned_tasks":original["unassigned_task_count"],
        "preclaim_assignment_agreement_percent":original["assignment_agreement_percent"],
        "corrected_preclaim_vote_similarity_percent":similarity,
        "task_sender_sends":len(task_trace.events),
        "task_sender_bytes":task_trace.sender_bytes,
        "cost_sender_sends":len(cost_events),
        "cost_sender_bytes":sum(e.payload_bytes for e in cost_events),
        "vote_sender_sends":len(vote_events),
        "vote_sender_bytes":sum(e.payload_bytes for e in vote_events),
        "cost_receiver_drops":sum(
            o.phase=="cost" and not o.delivered for o in run.deliveries),
        "vote_receiver_drops":sum(
            o.phase=="vote" and not o.delivered for o in run.deliveries),
        "global_greedy_cost":original["global_greedy_cost"],
        "initial_conflict_tasks":original["duplicate_task_count"],
        "temperature":temperature,
    }
    task_done=max((e.arrival_time_ms for e in task_trace.events),default=0.0)
    rows=[]
    audits=[]
    for channel in ("local_only",)+channels:
        if channel=="local_only":
            claim=None
            claimed_pairs=run.robot_claims
            extra=[]
            complete=1
            stop_ms=task_done+run.decision_time_ms
        else:
            claim_sampler=create_e9g_sampler(
                profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
            )
            claim=coordinate_p2l_claims(
                run=run,cost_matrix=costs,votes_per_voter=votes,
                sampler=claim_sampler,loss_sampler=loss_sampler,
                p_loss=loss,channel=channel,
                max_attempts=max_claim_attempts,
                max_rounds=max_claim_rounds,
            )
            claim_net=claim_sampler.summarize_network()
            if (claim_net["packet_count"]!=len(claim.events)
                    or claim_net["application_sender_bytes"]!=claim.sender_bytes):
                fail("run_p2l_paired_seed","contract","P2L_CLAIM_NETWORK_LEDGER_MISMATCH",
                     expected=(len(claim.events),claim.sender_bytes),
                     actual=(claim_net["packet_count"],
                             claim_net["application_sender_bytes"]))
            claimed_pairs=claim.assigned_pairs
            extra=claim.events
            complete=int(claim.complete_exchange)
            stop_ms=task_done+claim.finish_ms
        if any(e.phase not in ("claim","claim_ack") for e in extra):
            fail("run_p2l_paired_seed","contract",
                 "P2L_FORBIDDEN_SCORE_OR_COMMIT",
                 expected=("claim","claim_ack"),
                 actual=sorted({e.phase for e in extra}))
        results=analyze_p2l_actual_executions(
            scene=scene,pairs=claimed_pairs,
            reference_cost=original["global_greedy_cost"],
        )
        claim_events=[e for e in extra if e.phase=="claim"]
        ack_events=[e for e in extra if e.phase=="claim_ack"]
        claim_deliveries=claim.deliveries if claim is not None else ()
        attempted=len(task_trace.events)+len(run.events)+len(extra)
        attempted_bytes=task_trace.sender_bytes+run.sender_bytes+sum(
            e.payload_bytes for e in extra)
        row={
            **shared,"arm":channel,
            "channel":("none" if channel=="local_only" else channel),
            **results,
            "claim_sender_sends":len(claim_events),
            "claim_sender_bytes":sum(e.payload_bytes for e in claim_events),
            "ack_sender_sends":len(ack_events),
            "ack_sender_bytes":sum(e.payload_bytes for e in ack_events),
            "total_sender_sends":attempted,
            "total_sender_bytes":attempted_bytes,
            "claim_receiver_drops":sum(
                o.phase=="claim" and not o.delivered
                for o in claim_deliveries),
            "ack_receiver_drops":sum(
                o.phase=="claim_ack" and not o.delivered
                for o in claim_deliveries),
            "claim_rounds":claim.rounds_executed if claim is not None else 0,
            "conflict_task_rounds":(
                claim.conflict_task_rounds if claim is not None else 0),
            "reassignment_claims":(
                claim.reassignment_claims if claim is not None else 0),
            "claim_exchange_complete":complete,
            "claim_diagnostic":(
                f"{claim.first_diagnostic.owner}/"
                f"{claim.first_diagnostic.function}/"
                f"{claim.first_diagnostic.category}/"
                f"{claim.first_diagnostic.code}"
                if claim is not None and claim.first_diagnostic is not None else ""
            ),
            "claim_diagnostic_json":(
                json.dumps(asdict(claim.first_diagnostic),
                           ensure_ascii=False,separators=(",",":"))
                if claim is not None and claim.first_diagnostic is not None
                else ""
            ),
            "native_stop_ms":stop_ms,
        }
        if tuple(row)!=FIELDS:
            missing=set(FIELDS)-set(row)
            extra_keys=set(row)-set(FIELDS)
            if missing or extra_keys:
                fail("run_p2l_paired_seed","contract","P2L_RAW_COLUMN_MISMATCH",
                     expected={"missing":[],"extra":[]},
                     actual={"missing":sorted(missing),"extra":sorted(extra_keys)})
        rows.append(row)
        if capture_audit:
            audits.append({
                "seed":scene.seed,"loss_percent":round(loss*100),
                "arm":channel,"votes":votes,
                "original_local_claims":run.robot_claims,
                "actual_executed_claims":claimed_pairs,
                "claim_network_phase_sends":{
                    "claim":len(claim_events),"claim_ack":len(ack_events)},
                "claim_failure":row["claim_diagnostic"],
                "local_assignment_per_robot":run.local_assignments,
                "per_robot_own_received_vote_row":tuple(
                    run.local_vote_views[r][r] for r in range(robots)),
                "per_robot_received_vote_batch_count":tuple(
                    sum(sum(row) for row in run.local_vote_views[r])//votes
                    for r in range(robots)),
                "certified_public_claims":(
                    [asdict(record) for record in claim.public_claims]
                    if claim is not None else []),
                "first_claim_diagnostic_json":row["claim_diagnostic_json"],
            })
    return rows,audits


def summarize_p2l_rows(rows: list[dict]) -> list[dict]:
    groups={}
    for row in rows:
        key=(row["arm"],row["loss_percent"],row["votes_per_voter"])
        groups.setdefault(key,[]).append(row)
    def mean(rs,field):
        return sum(float(row[field]) for row in rs)/len(rs)
    result=[]
    for (arm,loss,votes),group in sorted(groups.items()):
        valid=[row for row in group if row["full_valid_allocation"]]
        result.append({
            "arm":arm,"loss_percent":loss,"votes_per_voter":votes,
            "seeds":len(group),
            "full_valid_percent":100*len(valid)/len(group),
            "mean_unique_completion_percent":mean(
                group,"unique_task_completion_percent"),
            "mean_task_coverage_percent":mean(group,"task_coverage_percent"),
            "mean_duplicate_tasks":mean(group,"duplicate_task_count"),
            "mean_unassigned_tasks":mean(group,"unassigned_task_count"),
            "mean_preclaim_unique_percent":mean(group,"preclaim_unique_percent"),
            "mean_preclaim_assignment_agreement_percent":mean(
                group,"preclaim_assignment_agreement_percent"),
            "mean_corrected_vote_similarity_percent":mean(
                group,"corrected_preclaim_vote_similarity_percent"),
            "mean_sender_kB":mean(group,"total_sender_bytes")/1000,
            "mean_claim_kB":mean(group,"claim_sender_bytes")/1000,
            "mean_ack_kB":mean(group,"ack_sender_bytes")/1000,
            "mean_stop_s":mean(group,"native_stop_ms")/1000,
            "mean_claim_rounds":mean(group,"claim_rounds"),
            "mean_reassignment_claims":mean(group,"reassignment_claims"),
            "claim_exchange_failure_percent":100*sum(
                not row["claim_exchange_complete"] for row in group)/len(group),
            "valid_cost_seeds":len(valid),
            "mean_valid_cost_gap_percent":(
                mean(valid,"cost_gap_percent_if_valid") if valid else ""),
        })
    return result


def save_p2l_evidence(*,root: Path,rows: list[dict], config: dict,
                      source_sha: str) -> None:
    summary=summarize_p2l_rows(rows)
    path=root/"summary_p2l.csv"
    with path.open("x",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)
    paths=[
        root/"per_seed_p2l.csv",
        root/"summary_p2l.csv",
        root/"audit_p2l.jsonl",
        root/"run_config_p2l.json",
    ]
    manifest={
        "study":STUDY,"source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),"groups":len(summary),"config":config,
        "sha256":{p.name:sha256_file(p) for p in paths},
        "warning":"ideal_paid is an optimistic model-reliable CLAIM upper bound; "
                  "bounded_ack uses actual lossy CLAIM and lossy ACK attempts, "
                  "with no execution on incomplete receipt. Both use shared "
                  "synchronous round barriers; not async consensus proof.",
    }
    (root/"manifest_p2l.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8",
    )


def run_p2l(args) -> None:
    losses,channels=validate_p2l_axes(args)
    sha=read_source_sha()
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2l","state","P2L_OUTPUT_EXISTS",
             expected="new append-only directory",actual=str(root))
    root.mkdir(parents=True)
    config={
        "study":STUDY,"source_sha":sha,"seeds":args.seeds,
        "first_seed":args.first_seed,
        "robots":args.robots,"tasks":args.tasks,
        "votes":args.votes,"temperature":args.temperature,
        "loss_percent":losses,"channels":channels,
        "max_claim_attempts":args.max_claim_attempts,
        "max_claim_rounds":args.max_claim_rounds,
        "audit_seeds":args.audit_seeds,
        "voting":"P2K cost_softmax 1000 tickets; one lossy P2KV per voter",
        "conflicts":"candidate-only normalized CLAIM scores; losers retry "
                    "available tasks using their own Vote row and own Cost row",
        "claim_channel":"bounded_ack models both CLAIM and ACK loss; "
                        "ideal_paid assumes guaranteed CLAIM receipt without ACK",
        "control":"P2K no-CLAIM no-PSCR, matched same native Cost/Vote",
        "network":"Rady trace + hypothetical shared-medium 144Mbps",
        "cpu_optimization_time":"not modeled",
        "task_announcement":"model-reliable paid TASK as in P2K",
    }
    (root/"run_config_p2l.json").write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8",
    )
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows=[]
    with (root/"per_seed_p2l.csv").open("x",newline="",encoding="utf-8") as raw, \
         (root/"audit_p2l.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(raw,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,args.robots,args.tasks)
                cases,audits=run_p2l_paired_seed(
                    scene=scene,profile=profile,loss=loss/100,
                    votes=args.votes,channels=channels,source_sha=sha,
                    temperature=args.temperature,
                    max_claim_attempts=args.max_claim_attempts,
                    max_claim_rounds=args.max_claim_rounds,
                    capture_audit=seed<args.first_seed+args.audit_seeds,
                )
                for row in cases:
                    writer.writerow({field:row[field] for field in FIELDS})
                    raw.flush()
                    rows.append(row)
                    print(
                        f"P2L loss={loss}% seed={seed} arm={row['arm']} "
                        f"unique={row['unique_task_completion_percent']:.1f}% "
                        f"duplicate={row['duplicate_task_count']} "
                        f"missing={row['unassigned_task_count']} "
                        f"complete={row['full_valid_allocation']} "
                        f"claim_ok={row['claim_exchange_complete']} "
                        f"bytes={row['total_sender_bytes']}",flush=True,
                    )
                for item in audits:
                    audit_file.write(json.dumps(item,separators=(",",":"))+"\n")
    save_p2l_evidence(root=root,rows=rows,config=config,source_sha=sha)
    print(f"P2L_COMPLETE rows={len(rows)} "
          f"groups={len(summarize_p2l_rows(rows))} root={root}",flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50,0.90")
    parser.add_argument("--votes",type=int,default=1000)
    parser.add_argument("--seeds",type=int,default=10)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=100)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--channels",default="bounded_ack,ideal_paid")
    parser.add_argument("--max-claim-attempts",type=int,default=24)
    parser.add_argument("--max-claim-rounds",type=int,default=101)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2l(parse_args(argv))


if __name__=="__main__":
    main()
