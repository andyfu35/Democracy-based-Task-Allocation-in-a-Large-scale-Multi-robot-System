"""P2Q NEW METHOD ONLY: optimize first, then vote by inverse-square ranks.

This experiment deliberately turns OFF CLAIM/ACK/GRANT/Score/Commit
so the underlying research question is not hidden by task-owner safety.
Each robot acts solely on its *own* receiver-local matching after one
genuinely lossy Cost and one genuinely lossy 1016B P2KV packet.
The global observer may diagnose duplicate or missing self-claims,
but never repairs them or feeds them into any robot.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p1_matched_five import DEFAULT_RADY, read_source_sha, sha256_file
from experiments.run_p2k_consensus_free import (
    FIELDS as SOURCE_FIELDS, run_one_p2k_case, validate_p2k_config,
)

OWNER="experiments.run_p2q_rank_square_voting"
STUDY="P2Q_OPTIMIZED_KBEST_RANK_SQUARED_NO_CLAIM_ONLY"
POLICY="optimized_rank_square"
NEW_FIELDS=(
    "receiver_task_positive_support_count",
    "receiver_task_top_vote_ties",
    "receiver_task_zero_vote_support_count",
    "receiver_task_top_tie_percent",
    "mean_positive_top_two_vote_margin",
    "task_any_receiver_top_tie_count",
    "first_diagnostic_json",
)
FIELDS=SOURCE_FIELDS+NEW_FIELDS
SUMMARY_FIELDS=(
    "loss_percent","votes_per_voter","seeds",
    "full_valid_count","full_valid_percent",
    "mean_unique_completion_percent",
    "mean_duplicate_tasks","mean_unassigned_tasks",
    "mean_assignment_agreement_percent",
    "mean_receiver_top_tie_percent",
    "mean_top_two_vote_margin",
    "mean_zero_support_receiver_tasks",
    "mean_task_any_receiver_tie_count",
    "mean_sender_bytes","mean_stop_ms",
    "valid_cost_samples","mean_cost_if_valid",
    "mean_cost_gap_percent_if_valid",
)


def fail(function,category,code,*,expected=None,actual=None,details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2q_axes(args):
    """P2Q is strictly one new policy, no old algorithm arms."""
    losses,votes=validate_p2k_config(args)
    if votes!=(1000,) or args.k!=5 or args.epsilon!=0.0:
        fail("validate_p2q_axes","data","P2Q_INVALID_RANK_SQUARE_SCOPE",
             expected={"votes":[1000],"k":5,"epsilon":0.0},
             actual={"votes":votes,"k":args.k,"epsilon":args.epsilon})
    return losses


def validate_p2q_received_vote_matrices(*,source_row,matrices):
    """Data/contract boundary: the offline observer's actual receipt view."""
    robots=source_row["robots"]
    tasks=source_row["tasks"]
    if (len(matrices)!=robots
            or any(len(view)!=robots for view in matrices)
            or any(len(row)!=tasks for view in matrices
                   for row in view)):
        fail("validate_p2q_received_vote_matrices","contract",
             "P2Q_INVALID_AUDIT_VIEW",
             expected=f"{robots} receivers x {robots} robots x {tasks} tasks",
             actual={"receivers":len(matrices)})
    for view in matrices:
        for row in view:
            for value in row:
                if type(value) is not int or value<0:
                    fail("validate_p2q_received_vote_matrices","data",
                         "P2Q_NEGATIVE_OR_NONINTEGER_RECEIVED_VOTE",
                         expected="nonnegative integral received vote count",
                         actual=value)


def diagnose_p2q_local_execution(*,source_row):
    """Safety observation; NEVER authorize or repair any self-claim."""
    if source_row["full_valid_allocation"]:
        return ""
    diagnostic=Diagnostic(
        owner=OWNER,function="diagnose_p2q_local_execution",
        category="safety",code="P2Q_LOCAL_EXECUTIONS_NOT_ONE_TO_ONE",
        expected={"unique_tasks":source_row["tasks"],
                  "duplicate_tasks":0,"unassigned_tasks":0},
        actual={"unique_percent":
                source_row["unique_task_completion_percent"],
                "duplicate_tasks":source_row["duplicate_task_count"],
                "unassigned_tasks":source_row["unassigned_task_count"]},
        details="Different receiver-local matchings led to unverified "
                "self-executions. No CLAIM/Commit/owner repair exists.",
    )
    return json.dumps(
        asdict(diagnostic),ensure_ascii=False,separators=(",",":"),
    )


def analyze_p2q_vote_consensus(*,source_row,received_vote_matrices):
    """Observer-only analysis, separate from data validation and safety.

    A top-vote tie for one receiver/task is NOT a globally
    duplicated task self-execution. This cannot affect live decisions.
    """
    validate_p2q_received_vote_matrices(
        source_row=source_row,matrices=received_vote_matrices,
    )
    robots=source_row["robots"]
    tasks=source_row["tasks"]
    ties=0
    positive=0
    zero=0
    gaps=0
    any_ties=[False]*tasks
    for receiver_view in received_vote_matrices:
        for task_id in range(tasks):
            ranking=sorted(
                (receiver_view[r][task_id] for r in range(robots)),
                reverse=True,
            )
            best=ranking[0]
            if best==0:
                zero+=1
                continue
            positive+=1
            gaps+=best-ranking[1]
            if ranking[1]==best:
                ties+=1
                any_ties[task_id]=True
    if positive+zero!=robots*tasks or ties>positive:
        fail("analyze_p2q_vote_consensus","contract",
             "P2Q_INCONSISTENT_TIE_DENOMINATOR",
             expected=robots*tasks,
             actual={"positive":positive,"zero":zero,"ties":ties})
    return {
        "receiver_task_positive_support_count":positive,
        "receiver_task_top_vote_ties":ties,
        "receiver_task_zero_vote_support_count":zero,
        "receiver_task_top_tie_percent":(100.0*ties/positive if positive else 0.0),
        "mean_positive_top_two_vote_margin":(gaps/positive if positive else 0.0),
        "task_any_receiver_top_tie_count":sum(any_ties),
        "first_diagnostic_json":diagnose_p2q_local_execution(
            source_row=source_row,
        ),
    }


def summarize_p2q_rows(rows):
    """One cohort per loss; never impute invalid allocation cost as zero."""
    groups={}
    for row in rows:
        groups.setdefault(row["loss_percent"],[]).append(row)
    def mean(batch,key):
        return sum(float(row[key]) for row in batch)/len(batch)
    result=[]
    for loss,batch in sorted(groups.items()):
        valid=[row for row in batch if row["full_valid_allocation"]]
        result.append({
            "loss_percent":loss,
            "votes_per_voter":1000,
            "seeds":len(batch),
            "full_valid_count":len(valid),
            "full_valid_percent":100*len(valid)/len(batch),
            "mean_unique_completion_percent":
                mean(batch,"unique_task_completion_percent"),
            "mean_duplicate_tasks":mean(batch,"duplicate_task_count"),
            "mean_unassigned_tasks":mean(batch,"unassigned_task_count"),
            "mean_assignment_agreement_percent":
                mean(batch,"assignment_agreement_percent"),
            "mean_receiver_top_tie_percent":
                mean(batch,"receiver_task_top_tie_percent"),
            "mean_top_two_vote_margin":
                mean(batch,"mean_positive_top_two_vote_margin"),
            "mean_zero_support_receiver_tasks":
                mean(batch,"receiver_task_zero_vote_support_count"),
            "mean_task_any_receiver_tie_count":
                mean(batch,"task_any_receiver_top_tie_count"),
            "mean_sender_bytes":mean(batch,"sender_bytes"),
            "mean_stop_ms":mean(batch,"native_stop_ms"),
            "valid_cost_samples":len(valid),
            "mean_cost_if_valid":(
                mean(valid,"cost_if_valid") if valid else ""),
            "mean_cost_gap_percent_if_valid":(
                mean(valid,"cost_gap_percent_if_valid") if valid else ""),
        })
    return result


def save_p2q_evidence(*, root, rows, config, source_sha):
    summary=summarize_p2q_rows(rows)
    with (root/"summary_p2q.csv").open("x",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=SUMMARY_FIELDS,
                              extrasaction="raise")
        writer.writeheader()
        writer.writerows(summary)
    source_files=(
        root/"per_seed_p2q.csv",
        root/"summary_p2q.csv",
        root/"audit_p2q.jsonl",
        root/"run_config_p2q.json",
    )
    manifest={
        "study":STUDY,"source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "rows":len(rows),"groups":len(summary),"config":config,
        "sha256":{f.name:sha256_file(f) for f in source_files},
        "warning":"ONLY ranked-square vote policy executed. No CLAIM, ACK, "
                  "GRANT, Score, Commit or collision correction. One-to-one "
                  "inside every receiver does NOT ensure one-to-one across "
                  "independent receivers. Ties and collisions separate.",
    }
    (root/"manifest_p2q.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),
        encoding="utf-8",
    )


def run_p2q(args):
    """Exactly one new vote policy per (loss,seed); no legacy arms."""
    losses=validate_p2q_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2q","state","P2Q_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only experiment directory",actual=str(root))
    source_sha=read_source_sha()
    root.mkdir(parents=True)
    config={
        "study":STUDY,"source_sha":source_sha,
        "robots":args.robots,"tasks":args.tasks,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "loss_percent":losses,"votes":1000,
        "policy":POLICY,"k":args.k,"epsilon":args.epsilon,
        "temperature":args.temperature,
        "rank_weight":"w_k=1/k^2; local K proposals sorted by original cost",
        "task_tickets":"deterministic Hamilton largest remainder, 10 per task",
        "only_method":"P2Q optimized_rank_square vote-only",
        "wire":"TASK paid assumed reliable; original lossy Cost + original "
               "1016B P2KV Vote per robot; no further control messages",
        "network":"Rady WiFi6 hypothetical shared 144Mbps medium; modeled "
                  "communication time excludes CPU optimization",
        "offline_ties":"per receiver/task equal maximum positive vote "
                        "counts among candidate robot IDs",
        "offline_conflicts":"task IDs self-executed by >1 robots independently",
        "complete_cost":"only if ALL 100 tasks are uniquely assigned",
        "audit_seeds":args.audit_seeds,
    }
    (root/"run_config_p2q.json").write_text(
        json.dumps(config,ensure_ascii=False,indent=2),
        encoding="utf-8",
    )
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows=[]
    with (root/"per_seed_p2q.csv").open("x",newline="",encoding="utf-8") as raw, \
         (root/"audit_p2q.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(raw,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,args.robots,args.tasks)
                # The original P2K physical source creates one real
                # Cost+Vote epoch. Always materialize one observer-only
                # ephemeral audit for *this same run*, not a second arm.
                source,audit=run_one_p2k_case(
                    scene=scene,profile=profile,loss=loss/100,
                    votes=1000,policy=POLICY,source_sha=source_sha,
                    k=args.k,epsilon=args.epsilon,
                    temperature=args.temperature,capture_audit=True,
                )
                if audit is None:
                    fail("run_p2q","contract","P2Q_SOURCE_AUDIT_MISSING",
                         expected="the one native receiver-local vote audit",
                         actual=None)
                extras=analyze_p2q_vote_consensus(
                    source_row=source,
                    received_vote_matrices=audit[
                        "per_robot_received_vote_matrices"],
                )
                row={**source,**extras}
                if set(row)!=set(FIELDS) or row["policy"]!=POLICY:
                    fail("run_p2q","contract","P2Q_RAW_SCHEMA_OR_POLICY_MISMATCH",
                         expected=sorted(FIELDS),
                         actual={"fields":sorted(row),
                                 "policy":row.get("policy")})
                writer.writerow(row)
                raw.flush()
                rows.append(row)
                if seed<args.first_seed+args.audit_seeds:
                    audit_file.write(json.dumps(
                        {**audit,
                         "source_sha":source_sha,
                         "local_vote_policy":POLICY,
                         "ranked_square_tie_metrics":extras},
                        ensure_ascii=False,separators=(",",":"),
                    )+"\n")
                    audit_file.flush()
                print(
                    f"P2Q loss={loss}% seed={seed} "
                    f"unique={row['unique_task_completion_percent']:.1f}% "
                    f"duplicate={row['duplicate_task_count']} "
                    f"missing={row['unassigned_task_count']} "
                    f"tie={row['receiver_task_top_vote_ties']}/"
                    f"{row['receiver_task_positive_support_count']} "
                    f"top_margin={row['mean_positive_top_two_vote_margin']:.2f} "
                    f"valid={row['full_valid_allocation']} "
                    f"bytes={row['sender_bytes']}",
                    flush=True,
                )
    save_p2q_evidence(root=root,rows=rows,config=config,source_sha=source_sha)
    print(f"P2Q_COMPLETE cases={len(rows)} "
          f"groups={len(summarize_p2q_rows(rows))} root={root}",flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50,0.90")
    parser.add_argument("--votes",default="1000")
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=100)
    parser.add_argument("--seeds",type=int,default=10)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--k",type=int,default=5)
    parser.add_argument("--epsilon",type=float,default=0.0)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2q(parse_args(argv))


if __name__=="__main__":
    main()
