"""P2V: P2S visible-row Hungarian voting + P2R physical owner cost-first arbitration.

No new owner state machine, no oracle execution repair, no old P2S rerun.
Primary metric: only full safe assignments vs exact full-information Hungarian.
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
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, read_source_sha, sha256_file,
)
from experiments.run_p2r_intent_conflict_commit import (
    FIELDS, SUMMARY_FIELDS, run_one_p2r_case, summarize_p2r_rows,
)
from experiments.run_p2s_adaptive_local_matching import (
    validate_p2s_axes, validate_p2s_native_row,
)

OWNER="experiments.run_p2v_cost_first_owner"
STUDY="P2V_P2S_ADAPTIVE_MATCHING_P2R_COST_FIRST_OWNER"
BALLOT_POLICY="adaptive_local_matching"
OWNER_POLICY="cost_first"
V_FIELDS=FIELDS+(
    "owner_decision_policy","hungarian_optimal_cost",
    "optimality_gap_percent_if_valid",
)
V_SUMMARY_FIELDS=SUMMARY_FIELDS+(
    "owner_decision_policy",
    "valid_optimality_gap_samples",
    "mean_valid_optimality_gap_percent",
)


def fail(function,category,code,*,expected=None,actual=None,details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2v_axes(args):
    """Same original 1000-ticket P2S/P2R axes, a named new owner policy."""
    return validate_p2s_axes(args)


def evaluate_p2v_cost_evidence(*, row, scene, loss):
    """Offline oracle comparison only AFTER truly executed owner-authorized pairs."""
    validate_p2s_native_row(row,scene,loss)
    if row["policy"] != BALLOT_POLICY:
        fail("evaluate_p2v_cost_evidence","contract",
             "P2V_WRONG_BALLOT_POLICY",
             expected=BALLOT_POLICY,actual=row["policy"])
    if row["p2r_intent_bytes"] != 36*row["p2r_intent_sends"]:
        fail("evaluate_p2v_cost_evidence","contract",
             "P2V_COST_INTENT_BYTES_MISMATCH",
             expected=36*row["p2r_intent_sends"],
             actual=row["p2r_intent_bytes"])
    optimum=solve_hungarian_assignment(scene.cost_matrix)
    row=dict(row)
    row["owner_decision_policy"]=OWNER_POLICY
    row["hungarian_optimal_cost"]=optimum.total_cost
    row["optimality_gap_percent_if_valid"]=(
        100*(float(row["actual_cost_if_valid"])/optimum.total_cost-1)
        if row["full_valid_allocation"] else ""
    )
    if set(row)!=set(V_FIELDS):
        fail("evaluate_p2v_cost_evidence","contract",
             "P2V_EVIDENCE_SCHEMA_MISMATCH",
             expected=sorted(V_FIELDS),actual=sorted(row))
    return row


def summarize_p2v_rows(rows):
    """Never average partial allocations into a falsely cheap cost."""
    base=summarize_p2r_rows(rows)
    for summary in base:
        same_loss=[r for r in rows if r["loss_percent"]==summary["loss_percent"]]
        valid=[r for r in same_loss if r["full_valid_allocation"]]
        summary["owner_decision_policy"]=OWNER_POLICY
        summary["valid_optimality_gap_samples"]=len(valid)
        summary["mean_valid_optimality_gap_percent"]=(
            sum(float(r["optimality_gap_percent_if_valid"]) for r in valid)
            /len(valid) if valid else ""
        )
    return base


def save_p2v_evidence(root,rows,audits,config):
    """Append-only new-method evidence, not a rewrite of prior P2S/P2R CSV."""
    with (root/"per_seed_p2v.csv").open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=V_FIELDS,extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    with (root/"summary_p2v.csv").open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=V_SUMMARY_FIELDS,extrasaction="raise")
        writer.writeheader()
        writer.writerows(summarize_p2v_rows(rows))
    with (root/"audit_p2v.jsonl").open("x",encoding="utf-8") as f:
        for record in audits:
            f.write(json.dumps(record,ensure_ascii=False,
                               separators=(",",":"))+"\n")
    (root/"run_config_p2v.json").write_text(
        json.dumps(config,indent=2,ensure_ascii=False),encoding="utf-8",
    )
    files=[root/name for name in (
        "per_seed_p2v.csv","summary_p2v.csv","audit_p2v.jsonl","run_config_p2v.json",
    )]
    manifest={
        "study":STUDY,"source_sha":config["source_sha"],
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "cases":len(rows),
        "sha256":{path.name:sha256_file(path) for path in files},
        "disclaimer":"P2S original Cost/Vote + P2R original Task Owner safety; "
                     "only cost-first on genuinely received P2VI. "
                     "Hungarian oracle is offline only; CPU planning excluded.",
    }
    (root/"manifest_p2v.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8",
    )


def run_p2v(args):
    losses=validate_p2v_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2v","state","P2V_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only result folder",actual=str(root))
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    config={
        "study":STUDY,"source_sha":source_sha,
        "ballot_policy":BALLOT_POLICY,"owner_decision_policy":OWNER_POLICY,
        "robots":args.robots,"tasks":args.tasks,
        "seeds":args.seeds,"first_seed":args.first_seed,
        "loss_percent":losses,"votes_per_voter":1000,
        "k":args.k,"epsilon":args.epsilon,"temperature":args.temperature,
        "max_rounds":args.max_rounds,
        "intent_repetitions":args.intent_repetitions,
        "decision_repetitions":args.decision_repetitions,
        "announcement_repetitions":args.announcement_repetitions,
        "physical_intent":"P2VI 36-byte sender's own Cost + P2S own Vote support",
        "preserved_safety":"unchanged P2R Task Owner CHALLENGE/COMMIT/DENY/P2NX",
        "comparison":"per-seed full Hungarian optimum, only full-safe cases",
        "time":"Rady+hypothetical 144Mbps medium; CPU solve excluded",
        "audit_seeds":args.audit_seeds,
    }
    rows=[]
    audits=[]
    for loss in losses:
        for seed in range(args.first_seed,args.first_seed+args.seeds):
            scene=generate_e0_scenario(seed,args.robots,args.tasks)
            original,audit=run_one_p2r_case(
                scene=scene,profile=profile,loss=loss/100,
                source_sha=source_sha,args=args,
                capture_audit=seed<args.first_seed+args.audit_seeds,
                local_policy=BALLOT_POLICY,
                owner_decision_policy=OWNER_POLICY,
            )
            row=evaluate_p2v_cost_evidence(row=original,scene=scene,loss=loss)
            rows.append(row)
            if audit is not None:
                audit["owner_decision_policy"]=OWNER_POLICY
                audits.append(audit)
            print(
                f"P2V loss={loss}% seed={seed} "
                f"executed={row['executed_count']}/{args.tasks} "
                f"full={row['full_valid_allocation']} "
                f"gap_opt={row['optimality_gap_percent_if_valid']} "
                f"bytes={row['sender_bytes']} "
                f"stop_s={row['native_stop_ms']/1000:.3f}",
                flush=True,
            )
    root.mkdir(parents=True)
    save_p2v_evidence(root,rows,audits,config)
    print(f"P2V_COMPLETE cases={len(rows)} root={root}",flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--losses",default="0.00,0.30,0.50")
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
    parser.add_argument("--decision-repetitions",type=int,default=3)
    parser.add_argument("--announcement-repetitions",type=int,default=3)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2v(parse_args(argv))


if __name__=="__main__":
    main()
