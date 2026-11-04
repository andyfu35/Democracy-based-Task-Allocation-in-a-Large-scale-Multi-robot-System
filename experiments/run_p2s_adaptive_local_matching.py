"""P2S: same original P2R Cost/Vote/INTENT/COMMIT wire, new visible-only ballot policy.

Run from repository root:
python -m experiments.run_p2s_adaptive_local_matching --losses 0.00,0.30,0.90 --seeds 2 --output-root results/p2s_smoke
python -m experiments.run_p2s_adaptive_local_matching --losses 0.00,0.30,0.50,0.90 --seeds 100 --output-root results/p2s_formal

No P2R historical results are rerun or overwritten.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p1_matched_five import DEFAULT_RADY, read_source_sha, sha256_file
from experiments.run_p2k_consensus_free import validate_p2k_config
from experiments.run_p2r_intent_conflict_commit import (
    FIELDS, SUMMARY_FIELDS, run_one_p2r_case, summarize_p2r_rows,
)
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile

OWNER = "experiments.run_p2s_adaptive_local_matching"
STUDY = "P2S_ADAPTIVE_LOCAL_MATCHING_VOTE_WITH_NATIVE_P2R_COMMIT"
POLICY = "adaptive_local_matching"


def fail(function, category, code, *, expected=None, actual=None, details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual, details=details,
    ))


def validate_p2s_axes(args):
    """Freeze one fair same-wire P2S arm; no implicit baseline rerun."""
    losses, votes = validate_p2k_config(args)
    if (votes != (1000,) or args.k != 1 or args.epsilon != 0.0
            or not 1 <= args.max_rounds <= 255
            or any(not 1 <= x <= 5 for x in (
                args.intent_repetitions, args.decision_repetitions,
                args.announcement_repetitions,
            ))):
        fail("validate_p2s_axes", "data", "P2S_INVALID_STUDY_AXES",
             expected="B1000, k1, epsilon0, rounds1..255, repeats1..5",
             actual=vars(args))
    return losses


def validate_p2s_native_row(row, scene, loss):
    """First failing owner: final uniqueness, no oracle-backed repair or fake cost."""
    tasks=scene.num_tasks
    executed=json.loads(row["executed_pairs_json"])
    if (len({r for r, _ in executed}) != len(executed)
            or len({t for _, t in executed}) != len(executed)
            or any(not 0 <= r < scene.num_robots or not 0 <= t < tasks
                   for r, t in executed)):
        fail("validate_p2s_native_row","safety","P2S_DUPLICATE_EXECUTION",
             expected="unique real P2RC-authorized robot/task edges",
             actual=executed)
    if row["policy"] != POLICY:
        fail("validate_p2s_native_row","contract","P2S_POLICY_EVIDENCE_MISMATCH",
             expected=POLICY,actual=row["policy"])
    if loss == 0:
        # 0%-loss complete shared-cost matching is a mandatory contract.
        from democracy_mrta.optimizer import solve_hungarian_assignment
        optimum=solve_hungarian_assignment(scene.cost_matrix)
        if (len(executed) != tasks or
                set(tuple(pair) for pair in executed) != set(optimum.assigned_pairs)):
            fail("validate_p2s_native_row","contract","P2S_ZERO_LOSS_OPTIMAL_PARITY",
                 expected=optimum.assigned_pairs,actual=executed)


def summarize_p2s(rows):
    return summarize_p2r_rows(rows)


def save_p2s(root, rows, audits, config):
    """Only derived evidence; each actual sender SEND is audited by P2R owner."""
    with (root/"per_seed_p2s.csv").open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    with (root/"summary_p2s.csv").open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=SUMMARY_FIELDS,extrasaction="raise")
        writer.writeheader()
        writer.writerows(summarize_p2s(rows))
    with (root/"audit_p2s.jsonl").open("x",encoding="utf-8") as f:
        for audit in audits:
            f.write(json.dumps(audit,ensure_ascii=False,separators=(",",":"))+"\n")
    (root/"run_config_p2s.json").write_text(
        json.dumps(config,indent=2,ensure_ascii=False),encoding="utf-8",
    )
    files=[root/name for name in (
        "per_seed_p2s.csv","summary_p2s.csv","audit_p2s.jsonl","run_config_p2s.json",
    )]
    manifest={
        "study":STUDY, "source_sha":config["source_sha"],
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version, "platform":platform.platform(),
        "cases":len(rows),"sha256":{p.name:sha256_file(p) for p in files},
        "disclaimer":"Native P2R owner executes physically modeled lossy Cost/Vote/INTENT/COMMIT; "
                     "CPU planning time not included; oracle only used for audit.",
    }
    (root/"manifest_p2s.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8",
    )


def run_p2s(args):
    losses=validate_p2s_axes(args)
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2s","state","P2S_OUTPUT_ALREADY_EXISTS",
             expected="fresh append-only result folder",actual=str(root))
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    config={
        "study":STUDY,"policy":POLICY,"source_sha":source_sha,
        "robots":args.robots,"tasks":args.tasks,"votes_per_voter":1000,
        "seeds":args.seeds,"first_seed":args.first_seed,"loss_percent":losses,
        "k":args.k,"epsilon":args.epsilon,"temperature":args.temperature,
        "max_rounds":args.max_rounds,
        "intent_repetitions":args.intent_repetitions,
        "decision_repetitions":args.decision_repetitions,
        "announcement_repetitions":args.announcement_repetitions,
        "local_policy":"max-cardinality minimum-cost received-row matching; "
                       "per-task cheapest-visible backup weighted by missing-row fraction",
        "transport":"one physically lossy Cost and P2KV Vote broadcast per robot; "
                    "unchanged P2R physical INTENT/CHALLENGE/COMMIT/DENY/P2NX",
        "reference":"offline full-info global greedy, only full native costs compared",
        "time":"Rady-sampled application delay + hypothetical 144Mbps shared medium; CPU excluded",
        "audit_seeds":args.audit_seeds,
    }
    rows=[]
    audits=[]
    for loss in losses:
        for seed in range(args.first_seed,args.first_seed+args.seeds):
            scene=generate_e0_scenario(seed,args.robots,args.tasks)
            row,audit=run_one_p2r_case(
                scene=scene,profile=profile,loss=loss/100,source_sha=source_sha,
                args=args,capture_audit=seed<args.first_seed+args.audit_seeds,
                local_policy=POLICY,
            )
            validate_p2s_native_row(row,scene,loss)
            if set(row)!=set(FIELDS):
                fail("run_p2s","contract","P2S_EVIDENCE_SCHEMA_MISMATCH",
                     expected=FIELDS,actual=tuple(row))
            rows.append(row)
            if audit is not None:
                audit["local_policy"]=POLICY
                audits.append(audit)
            print(f"P2S loss={loss}% seed={seed} "
                  f"executed={row['executed_count']}/{args.tasks} "
                  f"native_full={row['full_valid_allocation']} "
                  f"sender_bytes={row['sender_bytes']} "
                  f"stop_s={row['native_stop_ms']/1000:.3f}",flush=True)
    root.mkdir(parents=True)
    save_p2s(root,rows,audits,config)
    print(f"P2S_COMPLETE cases={len(rows)} root={root}",flush=True)


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
    parser.add_argument("--decision-repetitions",type=int,default=3)
    parser.add_argument("--announcement-repetitions",type=int,default=3)
    parser.add_argument("--audit-seeds",type=int,default=1)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2s(parse_args(argv))


if __name__=="__main__":
    main()
