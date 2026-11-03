"""P2O ONLY: 1000-ticket Softmax, identical task owners, causal radio time.

Only the P2O method runs: unchanged original per-robot Cost/Softmax/Vote,
same owner assignment, four lossy control packet types, three repeated
EXECUTING notices. New: causally timed parallel contenders on ONE
serialized physical wireless medium, explicit retry deadlines and
first-received-GRANT execution time.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

from democracy_mrta.claim_resolution import (
    validate_p2n_announcement_repetitions, validate_p2o_timing_scope,
)
from democracy_mrta.diagnostics import Diagnostic,ProtocolError
from democracy_mrta.network import ensure_rady_dataset,load_rady_latency_profile
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p1_matched_five import DEFAULT_RADY,read_source_sha,sha256_file
from experiments.run_p2m_task_owner import (
    FIELDS as P2M_FIELDS,P2N_EXTENSION_FIELDS,P2O_EXTENSION_FIELDS,
    PHASES as P2M_PHASES,run_one_p2m_case,validate_p2m_axes,
)

OWNER="experiments.run_p2o_execution_announcement"
STUDY="P2O_1000_SOFTMAX_TASK_OWNER_CAUSAL_TIMING_ONLY"
FIELDS=P2M_FIELDS+P2N_EXTENSION_FIELDS+P2O_EXTENSION_FIELDS
PHASES=P2M_PHASES+("execution_announce",)
SUMMARY_FIELDS=(
    "loss_percent","seeds","full_valid_percent",
    "mean_unique_completion_percent","mean_unassigned_tasks",
    "mean_duplicate_tasks","mean_initial_unique_percent",
    "mean_initial_duplicate_tasks",
    "mean_claim_rounds","mean_reassignment_requests",
    "mean_avoided_known_task_requests",
    "mean_announced_executions","mean_announcement_known_task_receipts",
    "mean_announcement_sender_sends","mean_announcement_sender_bytes",
    "mean_announcement_receiver_drops",
    "mean_owner_unicast_bytes","mean_total_sender_bytes",
    "mean_native_stop_ms","mean_blocked_robots",
    "mean_request_window_ms","mean_decision_window_ms",
    "mean_retry_timeout_wait_ms","mean_last_first_grant_ms",
    "mean_owner_protocol_finish_ms",
    "valid_cost_samples","mean_valid_allocation_cost",
)


def fail(function,category,code,*,expected=None,actual=None,details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2o_axes(args):
    """Only one new algorithm; no old-arm arguments or loops."""
    losses=validate_p2m_axes(args)
    repeats=validate_p2n_announcement_repetitions(
        args.announcement_repetitions,
    )
    validate_p2o_timing_scope(
        retry_timeout_ms=args.retry_timeout_ms,
        plans=(),phase="request",robots=args.robots,
        max_attempts=args.max_attempts,start_ms=0.0,
    )
    if repeats==0:
        fail("validate_p2o_axes","data","P2O_ANNOUNCEMENTS_REQUIRED",
             expected="1..5 actual broadcasts per received owner GRANT",
             actual=repeats)
    if type(args.votes) is not int or args.votes!=1000:
        fail("validate_p2o_axes","data","P2O_EXPECTS_1000_VOTES",
             expected=1000,actual=args.votes)
    return losses


def summarize_p2o_rows(rows):
    """No historical/matched arms, one 10-seed cohort per loss level."""
    groups={}
    for row in rows:
        groups.setdefault(row["loss_percent"],[]).append(row)
    def mean(batch,field):
        return sum(float(r[field]) for r in batch)/len(batch)
    def mean_nonempty(batch,field):
        values=[float(r[field]) for r in batch if r[field]!=""]
        return sum(values)/len(values) if values else ""
    summary=[]
    for loss,batch in sorted(groups.items()):
        valid=[r for r in batch if r["full_valid_allocation"]]
        owner_bytes=lambda row:sum(
            int(row[phase+"_bytes"])
            for phase in PHASES if phase.startswith("owner_")
        )
        summary.append({
            "loss_percent":loss,"seeds":len(batch),
            "full_valid_percent":100*len(valid)/len(batch),
            "mean_unique_completion_percent":mean(
                batch,"unique_task_completion_percent"),
            "mean_unassigned_tasks":mean(batch,"unassigned_task_count"),
            "mean_duplicate_tasks":mean(batch,"duplicate_task_count"),
            "mean_initial_unique_percent":mean(batch,"preclaim_unique_percent"),
            "mean_initial_duplicate_tasks":mean(batch,"preclaim_duplicate_tasks"),
            "mean_claim_rounds":mean(batch,"rounds_executed"),
            "mean_reassignment_requests":mean(batch,"reassignment_requests"),
            "mean_avoided_known_task_requests":mean(
                batch,"announcement_avoided_requests"),
            "mean_announced_executions":mean(batch,"announced_execution_count"),
            "mean_announcement_known_task_receipts":mean(
                batch,"announcement_known_task_receipts"),
            "mean_announcement_sender_sends":mean(
                batch,"execution_announce_sends"),
            "mean_announcement_sender_bytes":mean(
                batch,"execution_announce_bytes"),
            "mean_announcement_receiver_drops":mean(
                batch,"execution_announce_receiver_drops"),
            "mean_owner_unicast_bytes":sum(owner_bytes(r) for r in batch)/len(batch),
            "mean_total_sender_bytes":mean(batch,"sender_bytes"),
            "mean_native_stop_ms":mean(batch,"native_stop_ms"),
            "mean_blocked_robots":mean(batch,"blocked_robot_count"),
            "mean_request_window_ms":mean(batch,"request_window_total_ms"),
            "mean_decision_window_ms":mean(batch,"decision_window_total_ms"),
            "mean_retry_timeout_wait_ms":mean(batch,"timeout_wait_total_ms"),
            "mean_last_first_grant_ms":mean_nonempty(
                batch,"last_first_grant_arrival_ms"),
            "mean_owner_protocol_finish_ms":mean(
                batch,"owner_protocol_finish_ms"),
            "valid_cost_samples":len(valid),
            "mean_valid_allocation_cost":(
                mean(valid,"actual_cost_if_valid") if valid else ""),
        })
    return summary


def save_p2o_evidence(*,root,rows,config,source_sha):
    """Append-only complete evidence plus source SHA and local audit digest."""
    summary=summarize_p2o_rows(rows)
    with (root/"summary_p2o.csv").open("x",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=SUMMARY_FIELDS,extrasaction="raise")
        w.writeheader()
        w.writerows(summary)
    sources=[
        root/"per_seed_p2o.csv",root/"summary_p2o.csv",
        root/"audit_p2o.jsonl",root/"run_config_p2o.json",
    ]
    manifest={
        "study":STUDY,"source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),"loss_groups":len(summary),
        "config":config,
        "sha256":{f.name:sha256_file(f) for f in sources},
        "notice":"Only P2O causal task-owner timing executed. EXECUTING is 20B per physical "
                 "broadcast; it is advisory only and never authority to "
                 "execute. Three drops are independent in the Bernoulli "
                 "model, not a real radio guarantee. Existing Cost/Vote "
                 "and GRANT owner safety contracts are kept.",
    }
    (root/"manifest_p2o.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8",
    )


def run_p2o(args):
    """Single-method experiment runner: 40 cases for default 10 Seeds."""
    losses=validate_p2o_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2o","state","P2O_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only output directory",actual=str(root))
    source_sha=read_source_sha()
    root.mkdir(parents=True)
    config={
        "study":STUDY,"source_sha":source_sha,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "robots":args.robots,"tasks":args.tasks,
        "votes":args.votes,"temperature":args.temperature,
        "loss_percent":losses,"max_attempts":args.max_attempts,
        "max_rounds":args.max_rounds,
        "audit_seeds":args.audit_seeds,
        "announcement_repetitions":args.announcement_repetitions,
        "retry_timeout_ms":args.retry_timeout_ms,
        "timing_mode":"causal",
        "only_method":"task_owner_with_causal_parallel_radio_timing",
        "execution_announcement":"P2OX 20B; after physically received GRANT; "
                                 "3 independent lossy physical broadcasts",
        "receiver_knowledge":"only actually delivered authenticated-in-model "
                             "EXECUTING; not a global reservation oracle",
        "online_effect":"only locally skip known executing tasks when "
                        "choosing next request, task owner remains authority",
        "causal_timing":"All contenders release concurrently at one round "
                        "start, actual sender events serialized by the existing "
                        "shared Wi-Fi proxy; ACK generated on physical receipt; "
                        "retry on explicit sender-local timeout; GRANT triggers "
                        "EXECUTING at FIRST physical delivery",
        "startup":"model-reliable sender-paid TASK",
        "original_phases":"one lossy Cost and one 1016B P2KV Vote per robot",
        "radio":"Rady Wi-Fi6 hypothetical 144 Mbps serialized proxy; "
                "CPU time not included",
        "no_old_method":"P2M source used once as a native Cost/Vote owner, "
                        "no separate historical algorithm arms",
    }
    (root/"run_config_p2o.json").write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8",
    )
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows=[]
    with (root/"per_seed_p2o.csv").open("x",newline="",encoding="utf-8") as raw, \
         (root/"audit_p2o.jsonl").open("x",encoding="utf-8") as audit_file:
        writer=csv.DictWriter(raw,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,args.robots,args.tasks)
                row,audit=run_one_p2m_case(
                    scene=scene,profile=profile,loss=loss/100,
                    votes=args.votes,temperature=args.temperature,
                    max_attempts=args.max_attempts,max_rounds=args.max_rounds,
                    source_sha=source_sha,
                    capture_audit=seed<args.first_seed+args.audit_seeds,
                    execution_announce_repetitions=args.announcement_repetitions,
                    timing_mode="causal",
                    retry_timeout_ms=args.retry_timeout_ms,
                )
                if set(row)!=set(FIELDS):
                    fail("run_p2o","contract","P2O_MISSING_NATIVE_METRIC",
                         expected=sorted(FIELDS),actual=sorted(row))
                writer.writerow(row)
                raw.flush()
                rows.append(row)
                if audit is not None:
                    audit_file.write(json.dumps(
                        audit,ensure_ascii=False,separators=(",",":"))+"\n")
                print(
                    f"P2O loss={loss}% seed={seed} vote=1000 "
                    f"unique={row['unique_task_completion_percent']:.1f}% "
                    f"missing={row['unassigned_task_count']} "
                    f"duplicate={row['duplicate_task_count']} "
                    f"announced={row['announced_execution_count']} "
                    f"copies={row['execution_announce_sends']} "
                    f"avoided={row['announcement_avoided_requests']} "
                    f"rounds={row['rounds_executed']} "
                    f"CLAIM_ms={row['request_window_total_ms']:.1f} "
                    f"DECISION_ms={row['decision_window_total_ms']:.1f} "
                    f"sender_bytes={row['sender_bytes']}",flush=True,
                )
    save_p2o_evidence(root=root,rows=rows,config=config,source_sha=source_sha)
    print(
        f"P2O_COMPLETE cases={len(rows)} "
        f"groups={len(summarize_p2o_rows(rows))} root={root}",
        flush=True,
    )


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50,0.90")
    parser.add_argument("--votes",type=int,default=1000)
    parser.add_argument("--seeds",type=int,default=10)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=100)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--max-attempts",type=int,default=24)
    parser.add_argument("--max-rounds",type=int,default=101)
    parser.add_argument("--announcement-repetitions",type=int,default=3)
    parser.add_argument("--retry-timeout-ms",type=float,default=100.0)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2o(parse_args(argv))


if __name__=="__main__":
    main()
