"""P2K: no-Score/no-Commit autonomous MRTA hypothesis test.

Every receiver independently counts real timely Cost/Vote deliveries, runs
its own matching, and *only* executes its OWN locally inferred assignment.
The global observer has no corrective authority. CPU optimizer time is
not simulated; Wi-Fi-6 timing is a Rady-derived shared-medium proxy.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np

from democracy_mrta.coordination import simulate_p2k_local_vote_epoch
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, read_source_sha, scene_sha256, sha256_file,
)

OWNER="experiments.run_p2k_consensus_free"
STUDY="P2K_CONSENSUS_FREE_LOCAL_OPTIMIZATION"
POLICIES=("cost_softmax","optimized_kbest")
FIELDS=(
    "source_sha","seed","scene_sha256","robots","tasks","loss_percent",
    "votes_per_voter","policy","k","epsilon","temperature",
    "task_coverage_percent","unique_task_completion_percent",
    "duplicate_task_count","unassigned_task_count","full_valid_allocation",
    "assignment_agreement_percent","vote_distribution_similarity",
    "cost_if_valid","claims_cost_partial","global_greedy_cost",
    "cost_gap_percent_if_valid","claim_count","sender_sends","sender_bytes",
    "task_sends","task_bytes","cost_sends","cost_bytes",
    "vote_sends","vote_bytes","cost_receiver_drops","vote_receiver_drops",
    "native_stop_ms","local_assignment_digest","claims_json",
)
SUMMARY_FIELDS=(
    "policy","loss_percent","votes_per_voter","seeds",
    "full_valid_percent","mean_coverage_percent","mean_unique_percent",
    "mean_duplicate_tasks","mean_unassigned_tasks",
    "mean_assignment_agreement_percent","mean_vote_similarity",
    "mean_sender_bytes","mean_native_stop_ms",
    "valid_cost_samples","mean_valid_cost_gap_percent",
)


def fail(function: str,category: str,code: str,*,expected=None,actual=None,
         details: str="") -> None:
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2k_config(args: argparse.Namespace) -> tuple[tuple[int,...],tuple[int,...]]:
    """Frozen experiment settings; no seeded data generated before validation."""
    try:
        raw_loss=tuple(float(s) for s in args.losses.split(","))
        votes=tuple(int(s) for s in args.votes.split(","))
    except (ValueError,TypeError,AttributeError) as exc:
        fail("validate_p2k_config","data","P2K_BAD_AXIS_TEXT",actual=str(exc))
    losses=tuple(int(round(100*p)) for p in raw_loss if math.isfinite(p))
    valid=(len(losses)==len(raw_loss) and len(losses)>0
           and tuple(sorted(set(losses)))==losses
           and all(0<=p<=90 and abs(source-p/100)<1e-12
                   for source,p in zip(raw_loss,losses))
           and votes and tuple(sorted(set(votes)))==votes
           and type(args.robots) is int and 2<=args.robots<=100
           and type(args.tasks) is int and 1<=args.tasks<=args.robots
           and all(type(v) is int and args.tasks<=v<=1184
                   and v%args.tasks==0 for v in votes)
           and type(args.seeds) is int and 1<=args.seeds<=100
           and type(args.first_seed) is int and args.first_seed>=0
           and args.first_seed+args.seeds<=100
           and type(args.k) is int and 1<=args.k<=10
           and type(args.temperature) in (float,int)
           and math.isfinite(args.temperature) and args.temperature>0
           and type(args.epsilon) in (float,int)
           and math.isfinite(args.epsilon) and 0<=args.epsilon<=1
           and type(args.audit_seeds) is int and args.audit_seeds>=0)
    if not valid:
        fail("validate_p2k_config","data","P2K_INVALID_AXIS",
             expected="losses unique ascending 0..0.9; votes sorted unique "
                      "task-divisible 1..1184; 2<=robots<=100, 1<=tasks<=robots, "
                      "seeds 0..99, k 1..10, epsilon 0..1, tau>0",
             actual=vars(args))
    return losses,votes


def analyze_p2k_local_claims(*, scene, run) -> dict:
    """Observer-only metrics: NEVER feeds decisions back into any robot."""
    robots=scene.num_robots
    tasks=scene.num_tasks
    claims=run.robot_claims
    per_task=[0]*tasks
    for robot,task in claims:
        per_task[task]+=1
    if len({robot for robot,task in claims})!=len(claims):
        fail("analyze_p2k_local_claims","safety","P2K_ROBOT_CAPACITY_VIOLATION",
             expected="at most 1 claim per robot",actual=claims)
    unique=sum(count==1 for count in per_task)
    duplicate=sum(count>1 for count in per_task)
    unassigned=sum(count==0 for count in per_task)
    valid=int(unique==tasks and duplicate==0)
    claim_cost=sum(scene.cost_matrix[robot][task] for robot,task in claims)
    reference=solve_visible_batched_greedy_assignment(
        scene.cost_matrix,frozenset(range(robots)),
    ).total_cost
    # Overall view agreement is measured only OFFLINE by a central observer.
    # Each receiver locally gets a complete tentative assignment; only its
    # own row may become a physical claim, so disagreement can be substantial.
    local_vectors=[]
    for pairs in run.local_assignments:
        assignments=[-1]*tasks
        for robot,task in pairs:
            assignments[task]=robot
        local_vectors.append(assignments)
    array=np.array(local_vectors,dtype=np.int32)
    agree=0
    for task in range(tasks):
        counts=np.bincount(array[:,task]+1,minlength=robots+1)
        agree+=int(counts.max())
    agreement=100*agree/(robots*tasks)
    view=np.asarray(run.local_vote_views,dtype=np.float64)
    # Normalize each receiver's support for each task; skip zero-ticket tasks
    # instead of falsely claiming an identical all-zero probability vector.
    denominator=view.sum(axis=1,keepdims=True)
    normalized=np.divide(view,denominator,
        out=np.zeros_like(view),where=denominator>0)
    means=normalized.mean(axis=0,keepdims=True)
    similarity=100*(1-float(np.abs(normalized-means).sum(axis=1).mean())/(2*tasks))
    if not (0<=agreement<=100 and -1e-8<=similarity<=100+1e-8):
        fail("analyze_p2k_local_claims","contract","P2K_BAD_OFFLINE_SIMILARITY",
             expected="[0,100]",actual=(agreement,similarity))
    return {
        "task_coverage_percent":100*(tasks-unassigned)/tasks,
        "unique_task_completion_percent":100*unique/tasks,
        "duplicate_task_count":duplicate,"unassigned_task_count":unassigned,
        "full_valid_allocation":valid,
        "assignment_agreement_percent":agreement,
        "vote_distribution_similarity":similarity,
        "claims_cost_partial":claim_cost,
        "cost_if_valid":claim_cost if valid else "",
        "global_greedy_cost":reference,
        "cost_gap_percent_if_valid":100*(claim_cost/reference-1) if valid else "",
        "claim_count":len(claims),
        "local_assignment_digest":hashlib.sha256(
            repr(run.local_assignments).encode("utf-8")).hexdigest(),
        "claims_json":json.dumps(claims,separators=(",",":")),
    }


def run_one_p2k_case(*, scene,profile,loss: float,votes: int,policy: str,
                     source_sha: str,k: int,epsilon: float,temperature: float,
                     capture_audit: bool) -> tuple[dict,dict|None]:
    """Use real prior TASK, Cost, and Vote send/receipt owners without PSCR."""
    robots=scene.num_robots
    task_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    loss_sampler=BernoulliLossSampler(scene.seed)
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
    coord_sampler=create_e9g_sampler(
        profile=profile,seed=scene.seed,phy_rate_mbps=144.0,
    )
    cost_guard=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=robots,total_tasks=scene.num_tasks,
        reference_phy_mbps=144.0,
    )
    result=simulate_p2k_local_vote_epoch(
        cost_matrix=costs,sampler=coord_sampler,loss_sampler=loss_sampler,
        p_loss=loss,phase_timeout_ms=cost_guard,seed=scene.seed,
        votes_per_voter=votes,policy=policy,k=k,
        epsilon=epsilon,temperature=temperature,
    )
    if any(e.phase not in ("cost","vote") for e in result.events):
        fail("run_one_p2k_case","contract","P2K_FORBIDDEN_RELIABLE_SCORE_COMMIT",
             expected="Cost and Vote exclusively",
             actual=sorted(set(e.phase for e in result.events)))
    phases={}
    for event in result.events:
        ledger=phases.setdefault(event.phase,{"sends":0,"bytes":0})
        ledger["sends"]+=1
        ledger["bytes"]+=event.payload_bytes
    expected={"cost":robots,"vote":robots}
    if ({k:phases.get(k,{}).get("sends",0) for k in expected}!=expected
            or sum(p["bytes"] for p in phases.values())!=result.sender_bytes):
        fail("run_one_p2k_case","contract","P2K_SEND_LEDGER_MISMATCH",
             expected=expected,actual=phases)
    task_net=task_sampler.summarize_network()
    vote_net=coord_sampler.summarize_network()
    expected_packets=len(task_trace.events)+len(result.events)
    expected_bytes=task_trace.sender_bytes+result.sender_bytes
    if ((task_net["packet_count"]+vote_net["packet_count"])!=expected_packets
            or task_net["application_sender_bytes"]
                 +vote_net["application_sender_bytes"]!=expected_bytes):
        fail("run_one_p2k_case","contract","P2K_NETWORK_LEDGER_MISMATCH",
             expected=(expected_packets,expected_bytes),
             actual=(task_net["packet_count"]+vote_net["packet_count"],
                     task_net["application_sender_bytes"]
                     +vote_net["application_sender_bytes"]))
    metrics=analyze_p2k_local_claims(scene=scene,run=result)
    cost_drops=sum(1 for obs in result.deliveries
                   if obs.phase=="cost" and not obs.delivered)
    vote_drops=sum(1 for obs in result.deliveries
                   if obs.phase=="vote" and not obs.delivered)
    row={
        "source_sha":source_sha,"seed":scene.seed,
        "scene_sha256":scene_sha256(scene),
        "robots":robots,"tasks":scene.num_tasks,
        "loss_percent":round(loss*100),"votes_per_voter":votes,
        "policy":policy,"k":k,"epsilon":epsilon,"temperature":temperature,
        **metrics,
        "sender_sends":expected_packets,"sender_bytes":expected_bytes,
        "task_sends":len(task_trace.events),
        "task_bytes":task_trace.sender_bytes,
        "cost_sends":phases["cost"]["sends"],
        "cost_bytes":phases["cost"]["bytes"],
        "vote_sends":phases["vote"]["sends"],
        "vote_bytes":phases["vote"]["bytes"],
        "cost_receiver_drops":cost_drops,
        "vote_receiver_drops":vote_drops,
        "native_stop_ms":max(
            (e.arrival_time_ms for e in task_trace.events),default=0.0
        )+result.decision_time_ms,
    }
    audit=None
    if capture_audit:
        audit={
            "source_sha":source_sha,"seed":scene.seed,"loss_percent":row["loss_percent"],
            "votes_per_voter":votes,"policy":policy,
            "cost_visible_rows":[sorted(x) for x in result.cost_visible_rows],
            "per_robot_local_assignment":result.local_assignments,
            "per_robot_own_claim":[next(
                (task for robot_id,task in result.robot_claims if robot_id==r),None
            ) for r in range(robots)],
            "per_robot_received_vote_matrices":result.local_vote_views,
            "first_failure_or_repair":"NONE: no Score, no Commit, no correction",
        }
    return row,audit


def summarize_p2k_rows(rows: list[dict]) -> list[dict]:
    """Published summary owner; empty invalid-cost cohorts are NEVER zero."""
    groups={}
    for row in rows:
        key=(row["policy"],row["loss_percent"],row["votes_per_voter"])
        groups.setdefault(key,[]).append(row)
    def avg(batch,key):
        return sum(float(row[key]) for row in batch)/len(batch)
    result=[]
    for (policy,loss,votes),batch in sorted(groups.items()):
        completed=[r for r in batch if r["full_valid_allocation"]]
        result.append({
            "policy":policy,"loss_percent":loss,"votes_per_voter":votes,
            "seeds":len(batch),
            "full_valid_percent":100*len(completed)/len(batch),
            "mean_coverage_percent":avg(batch,"task_coverage_percent"),
            "mean_unique_percent":avg(batch,"unique_task_completion_percent"),
            "mean_duplicate_tasks":avg(batch,"duplicate_task_count"),
            "mean_unassigned_tasks":avg(batch,"unassigned_task_count"),
            "mean_assignment_agreement_percent":avg(
                batch,"assignment_agreement_percent"),
            "mean_vote_similarity":avg(batch,"vote_distribution_similarity"),
            "mean_sender_bytes":avg(batch,"sender_bytes"),
            "mean_native_stop_ms":avg(batch,"native_stop_ms"),
            "valid_cost_samples":len(completed),
            "mean_valid_cost_gap_percent":(
                avg(completed,"cost_gap_percent_if_valid") if completed else ""
            ),
        })
    return result


def save_p2k_results(*,root: Path,rows: list[dict],source_sha: str,
                     config: dict) -> None:
    summary=summarize_p2k_rows(rows)
    path=root/"summary_p2k.csv"
    with path.open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)
    checks={p.name:sha256_file(p) for p in (
        root/"per_seed_p2k.csv",root/"audit_p2k.jsonl",path,
        root/"run_config_p2k.json",
    )}
    manifest={
        "study":STUDY,"source_sha":source_sha,"created_utc":
        datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),"groups":len(summary),"config":config,
        "sha256":checks,
        "notice":"Audit only. No reliable PSCR, Commit or repair. Historical "
                 "P2J V3 has extra reliable control messages and is not a "
                 "matched no-consensus network baseline. Invalid cost gap blank.",
    }
    (root/"manifest_p2k.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8",
    )


def run_p2k(args: argparse.Namespace) -> None:
    losses,votes=validate_p2k_config(args)
    source_sha=read_source_sha()
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2k","state","P2K_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only result directory",actual=str(root))
    root.mkdir(parents=True)
    config={
        "study":STUDY,"source_sha":source_sha,"robots":args.robots,
        "tasks":args.tasks,"losses":losses,"votes":votes,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "k":args.k,"epsilon":args.epsilon,"temperature":args.temperature,
        "audit_seeds":args.audit_seeds,"policies":POLICIES,
        "task_announcement":"paid model-reliable once, same as P2J",
        "data_transport":"single original lossy Cost and one P2KV Vote per robot",
        "coordination":"NO PSCR, NO Commit, NO fallback, NO consensus",
        "network":"Rady Wi-Fi 6 trace + hypothetical shared 144Mbps medium",
        "optimizer_timing":"not included, pure modeled communication time",
        "local_optimizer":"exact visible assignment + <=k distinct seeded "
                          "perturb-and-MAP candidates; not exact k-best",
        "reference":"offline full-information global greedy, valid allocations only",
    }
    (root/"run_config_p2k.json").write_text(
        json.dumps(config,indent=2,ensure_ascii=False),encoding="utf-8",
    )
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows=[]
    with (root/"per_seed_p2k.csv").open("x",newline="",encoding="utf-8") as csv_file, \
         (root/"audit_p2k.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(csv_file,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for votes_per_voter in votes:
                for seed in range(args.first_seed,args.first_seed+args.seeds):
                    scene=generate_e0_scenario(seed,args.robots,args.tasks)
                    for policy in POLICIES:
                        row,audit=run_one_p2k_case(
                            scene=scene,profile=profile,loss=loss/100,
                            votes=votes_per_voter,policy=policy,
                            source_sha=source_sha,k=args.k,
                            epsilon=args.epsilon,temperature=args.temperature,
                            capture_audit=seed<args.first_seed+args.audit_seeds,
                        )
                        if audit is not None:
                            audit_file.write(json.dumps(audit,separators=(",",":"))+"\n")
                        writer.writerow(row)
                        csv_file.flush()
                        rows.append(row)
                        print(
                            f"P2K loss={loss}% votes={votes_per_voter} seed={seed} "
                            f"policy={policy} unique={row['unique_task_completion_percent']:.1f}% "
                            f"duplicate={row['duplicate_task_count']} "
                            f"missing={row['unassigned_task_count']} "
                            f"agreement={row['assignment_agreement_percent']:.1f}% "
                            f"SEND_bytes={row['sender_bytes']}",flush=True,
                        )
    save_p2k_results(root=root,rows=rows,source_sha=source_sha,config=config)
    print(f"P2K_COMPLETE rows={len(rows)} "
          f"groups={len(summarize_p2k_rows(rows))} root={root}",flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50,0.70,0.90")
    parser.add_argument("--votes",default="100,200,500,1000")
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=100)
    parser.add_argument("--seeds",type=int,default=2)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--k",type=int,default=5)
    parser.add_argument("--epsilon",type=float,default=0.10)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2k(parse_args(argv))


if __name__=="__main__":
    main()
